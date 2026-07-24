// /api/bom-chat — the BOM draft-review chat agent.
//
// Richard (or any reviewer) chats about a generated BOM draft. The
// agent sees the draft as context and has two kinds of tools:
//
//   server-executed  catalog_search / catalog_get_part — read-only
//                    lookups against the local Wrightsoft catalog
//                    SQLite (same DB the /api/catalog routes serve).
//   client-executed  propose_line_update / propose_add_line — the
//                    agent proposes; the UI renders an Apply button.
//                    Nothing mutates until the human clicks. Applied
//                    edits persist through the existing
//                    contractor-overrides path, so each answer is
//                    learned once.
//
// Requires ANTHROPIC_API_KEY (Cloud Run: secret env). Missing key →
// 503, server still boots.

import { Router, type Request, type Response } from "express";
import Anthropic from "@anthropic-ai/sdk";
import { logUsage, persistChatTurns } from "../usageLog.js";

const router = Router();

const CATALOG_PATH =
  process.env.CATALOG_SQLITE_PATH ??
  `${process.env.HOME}/Procalcs/Catalogs/catalog.sqlite`;

type SqliteDb = {
  prepare: (sql: string) => {
    all: (...params: unknown[]) => Record<string, unknown>[];
    get: (...params: unknown[]) => Record<string, unknown> | undefined;
  };
};

let db: SqliteDb | null = null;
async function getDb(): Promise<SqliteDb | null> {
  if (db) return db;
  try {
    const { default: Database } = await import("better-sqlite3");
    db = new Database(CATALOG_PATH, {
      readonly: true, fileMustExist: true,
    }) as unknown as SqliteDb;
  } catch {
    db = null;
  }
  return db;
}

const TOOLS: Anthropic.Tool[] = [
  {
    name: "catalog_search",
    description:
      "Search the Wrightsoft parts catalog (RPRUWSF — 38k parts incl. " +
      "the Rheia pack) by part number or description text. Use this to " +
      "identify unknown SKUs, find substitutes, or check whether a part " +
      "exists in the catalog. Prices of 0 mean Wrightsoft ships no " +
      "price — the contractor's own price is needed.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: { type: "string", description: "Part number fragment or description text" },
        source: {
          type: "string",
          description: "Optional 4-char manufacturer code filter (RHEA, GOOD, DAIK, BROA...)",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "catalog_get_part",
    description:
      "Exact lookup of one catalog part by manufacturer code + part number. " +
      "Returns full pricing fields (list/cost/margin/price) and category.",
    input_schema: {
      type: "object" as const,
      properties: {
        source: { type: "string", description: "4-char manufacturer code, e.g. RHEA" },
        part_no: { type: "string", description: "Exact part number, e.g. 10-00-190" },
      },
      required: ["source", "part_no"],
    },
  },
  {
    name: "propose_line_update",
    description:
      "Propose a change to an existing BOM line (price, quantity, or " +
      "description). The user sees the proposal with an Apply button — " +
      "it does NOT auto-apply. Use when the user tells you a price or " +
      "correct quantity, or when you found the right value in the catalog.",
    input_schema: {
      type: "object" as const,
      properties: {
        sku: { type: "string", description: "The generic_id / part number of the line" },
        unit_price: { type: "number", description: "New unit price in dollars" },
        quantity: { type: "number", description: "New quantity" },
        description: { type: "string", description: "Corrected description text" },
        reason: { type: "string", description: "One-line justification shown to the user" },
        rule_candidate: {
          type: "boolean",
          description: "true when the user phrased this as a standing rule " +
            "('always', 'every plan') — it gets queued for expert review",
        },
      },
      required: ["sku", "reason"],
    },
  },
  {
    name: "propose_add_line",
    description:
      "Propose adding a missing line to the BOM. The user sees the " +
      "proposal with an Apply button — it does NOT auto-apply.",
    input_schema: {
      type: "object" as const,
      properties: {
        sku: { type: "string" },
        description: { type: "string" },
        quantity: { type: "number" },
        unit_price: { type: "number" },
        source: { type: "string", description: "Manufacturer code if known" },
        reason: { type: "string", description: "One-line justification shown to the user" },
      },
      required: ["sku", "description", "quantity", "reason"],
    },
  },
  {
    name: "propose_remove_line",
    description:
      "Propose removing a line from this BOM (wrong part, duplicate, " +
      "not used on this plan). The user sees the proposal with an " +
      "Apply button — it does NOT auto-apply. Applies to THIS BOM " +
      "only; it does not create a standing rule.",
    input_schema: {
      type: "object" as const,
      properties: {
        sku: { type: "string", description: "The generic_id / part number of the line" },
        reason: { type: "string", description: "One-line justification shown to the user" },
        rule_candidate: {
          type: "boolean",
          description: "true when the user phrased this as a standing rule " +
            "('always', 'every plan', 'never') — it gets queued for expert review",
        },
      },
      required: ["sku", "reason"],
    },
  },
  {
    name: "propose_regenerate",
    description:
      "Propose regenerating the whole BOM from the stored design data. " +
      "Use AFTER corrections were applied so they fold into a fresh " +
      "run, or when the user asks for a clean re-run. The chat " +
      "conversation is preserved. The user sees an Apply button — it " +
      "does NOT auto-run.",
    input_schema: {
      type: "object" as const,
      properties: {
        reason: { type: "string", description: "One-line justification shown to the user" },
      },
      required: ["reason"],
    },
  },
];

async function runCatalogTool(
  name: string,
  input: Record<string, unknown>,
): Promise<string> {
  const d = await getDb();
  if (!d) return "Catalog database is not available in this environment.";
  if (name === "catalog_search") {
    const q = String(input.query ?? "").trim();
    const src = String(input.source ?? "").trim().toUpperCase();
    const where: string[] = [`("PN" LIKE ? OR "Description" LIKE ?)`];
    const params: unknown[] = [`%${q}%`, `%${q}%`];
    if (src) {
      where.push(`"PSrc" = ?`);
      params.push(src);
    }
    params.push(25);
    const rows = d
      .prepare(
        `SELECT PSrc, PN, Description, Category, Price, ListPrice
           FROM ActItem WHERE ${where.join(" AND ")} ORDER BY PSrc, PN LIMIT ?`,
      )
      .all(...params);
    return JSON.stringify(rows);
  }
  if (name === "catalog_get_part") {
    const row = d
      .prepare(
        `SELECT PSrc, PN, Description, Category, Units, PkgCount,
                ListPrice, Discount, Cost, Margin, Price, AltPN
           FROM ActItem WHERE "PSrc" = ? AND "PN" = ?`,
      )
      .get(String(input.source ?? "").toUpperCase(), String(input.part_no ?? ""));
    return row ? JSON.stringify(row) : "Part not found in catalog.";
  }
  return `Unknown tool: ${name}`;
}

const SYSTEM_PROMPT = `You are the BOM review assistant inside ProCalcs Designer Desktop.
The user is reviewing a Bill of Materials draft generated from a Wrightsoft .rup design file. Your job:
- Explain gaps: lines flagged "needs input" are SKUs Wrightsoft carries no price for (Rheia duct parts, Goodman/Daikin/Broan equipment). The contractor's own pricing must fill them.
- Identify parts via the catalog tools before guessing.
- When the user provides a price, quantity, or correction, immediately call propose_line_update (or propose_add_line for missing items, propose_remove_line for wrong/duplicate lines) so they can apply it with one click.
- Prices are remembered forever (contractor override — the same SKU never asks twice). Quantity, description, add and remove corrections fix THIS BOM only; if the user phrases one as a standing rule ("always", "every plan"), set rule_candidate=true so it reaches expert review — never claim it will auto-apply to future BOMs.
- After one or more corrections are applied, offer propose_regenerate so everything folds into a fresh consistent run. The chat survives regeneration.
- Keep answers short and concrete. This user is busy; one question at a time.
Domain notes: RHEA = Rheia (small-diameter duct system, rheiacomfort.com). BOMs historically exist only for Rheia projects; standard projects are the new territory. "RE" suffix files are revisions.`;

interface ChatAttachment {
  name: string;
  kind: string;
  summary?: string;
  extracted?: string;
  image_b64?: string;
  media_type?: string;
}

interface ChatBody {
  messages?: Anthropic.MessageParam[];
  bom_context?: unknown;
  attachments?: ChatAttachment[];
}

router.post("/", async (req: Request, res: Response) => {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    res.status(503).json({
      success: false, data: null,
      error: "chat agent not configured (ANTHROPIC_API_KEY missing)",
    });
    return;
  }
  const { messages = [], bom_context, attachments = [], client_id } =
    (req.body ?? {}) as ChatBody & { client_id?: string };
  if (!Array.isArray(messages) || messages.length === 0) {
    res.status(400).json({ success: false, data: null, error: "messages required" });
    return;
  }

  const client = new Anthropic({ apiKey });
  const system: Anthropic.TextBlockParam[] = [
    { type: "text", text: SYSTEM_PROMPT, cache_control: { type: "ephemeral" } },
  ];
  if (bom_context) {
    system.push({
      type: "text",
      text: `Current BOM draft (JSON):\n${JSON.stringify(bom_context).slice(0, 60_000)}`,
    });
  }
  // Day-24 — attachments: text extractions enter the system context
  // (extracted once at upload, capped per file); images ride as
  // vision blocks on the latest user turn below.
  for (const a of attachments.slice(0, 5)) {
    if (a.extracted) {
      system.push({
        type: "text",
        text: `Attached file "${a.name}" (${a.kind}) — ${a.summary ?? ""}\n` +
              `Contents:\n${String(a.extracted).slice(0, 30_000)}`,
      });
    }
  }

  const convo: Anthropic.MessageParam[] = [...messages];
  const imageAtts = attachments.filter((a) => a.image_b64 && a.media_type).slice(0, 4);
  if (imageAtts.length && convo.length) {
    const last = convo[convo.length - 1];
    if (last.role === "user" && typeof last.content === "string") {
      last.content = [
        ...imageAtts.map((a) => ({
          type: "image" as const,
          source: { type: "base64" as const,
                    media_type: a.media_type as "image/png" | "image/jpeg" | "image/webp" | "image/gif",
                    data: a.image_b64 as string },
        })),
        { type: "text" as const, text: last.content },
      ];
    }
  }
  const actions: Record<string, unknown>[] = [];

  try {
    for (let turn = 0; turn < 8; turn++) {
      const response = await client.messages.create({
        model: "claude-opus-4-8",
        max_tokens: 4096,
        system,
        tools: TOOLS,
        messages: convo,
      });

      const toolUses = response.content.filter(
        (b): b is Anthropic.ToolUseBlock => b.type === "tool_use",
      );
      if (response.stop_reason !== "tool_use" || toolUses.length === 0) {
        const reply = response.content
          .filter((b): b is Anthropic.TextBlock => b.type === "text")
          .map((b) => b.text)
          .join("\n");
        // Day-27 — await BEFORE responding. Cloud Run cpu-throttling
        // freezes the instance after res.json(), so a post-response
        // fire-and-forget POST never lands (dropped all of the crew's
        // real chats). Telemetry adds ~one fast round-trip to a call
        // that already took seconds.
        await logUsage(req, "chat_message", {
          snipes: attachments.filter((a) => a.kind === "snipe").length,
          attachments: attachments.filter((a) => a.kind !== "snipe").length,
          actions_proposed: actions.length,
          turns: messages.length,
        }, { client_id });
        // Day-27 — persist this exchange so the conversation survives
        // reload (Richard's save/resume). Only the NEW user turn + the
        // assistant reply are stored; the client sends full history but
        // earlier turns are already persisted. Attachments as metadata
        // only (name/kind), never bytes.
        const runId = Number((bom_context as any)?.run_id) || 0;
        if (runId) {
          const lastUser = [...messages].reverse()
            .find((m) => m.role === "user");
          const userText = typeof lastUser?.content === "string"
            ? lastUser.content
            : Array.isArray(lastUser?.content)
              ? (lastUser!.content as any[])
                  .filter((b) => b?.type === "text").map((b) => b.text).join("\n")
              : "";
          const attMeta = attachments.map((a) => ({ name: a.name, kind: a.kind }));
          await persistChatTurns(req, runId, [
            { role: "user", content: userText,
              attachments: attMeta.length ? attMeta : undefined },
            { role: "assistant", content: reply,
              actions: actions.length ? actions : undefined },
          ]);
        }
        res.json({ success: true, data: { reply, actions }, error: null });
        return;
      }

      convo.push({ role: "assistant", content: response.content });
      const results: Anthropic.ToolResultBlockParam[] = [];
      for (const tu of toolUses) {
        const input = tu.input as Record<string, unknown>;
        if (tu.name.startsWith("propose_")) {
          actions.push({ kind: tu.name, ...input });
          results.push({
            type: "tool_result", tool_use_id: tu.id,
            content: "Proposal recorded — shown to the user with an Apply button.",
          });
        } else {
          results.push({
            type: "tool_result", tool_use_id: tu.id,
            content: await runCatalogTool(tu.name, input),
          });
        }
      }
      convo.push({ role: "user", content: results });
    }
    res.json({
      success: true,
      data: { reply: "(stopped after 8 tool rounds — ask a narrower question)", actions },
      error: null,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    res.status(502).json({ success: false, data: null, error: `chat agent error: ${msg}` });
  }
});

export default router;
