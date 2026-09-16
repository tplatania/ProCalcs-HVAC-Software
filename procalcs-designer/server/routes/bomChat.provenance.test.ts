// Anti-fabrication / provenance contract tests for the chat agent
// (BETA gate C2). Run with: npx tsx --test server/routes/bomChat.provenance.test.ts
//
// We can't run the live model in CI, so instead we LOCK the guarantees
// that keep the agent honest: the system prompt must keep its
// no-fabrication policies, and the tools must keep the fields that stop
// the agent inventing lines. If someone edits these out, a test fails
// and the removal is a deliberate, reviewed act — not an accident.

import { describe, it, before } from "node:test";
import assert from "node:assert/strict";

// The chat route imports the Anthropic SDK + a lazy sqlite driver; both
// are import-safe (no network / no server start at module load).
let SYSTEM_PROMPT: string;
let TOOLS: any[];
before(async () => {
  const mod = await import("./bomChat.ts");
  SYSTEM_PROMPT = mod.SYSTEM_PROMPT;
  TOOLS = mod.TOOLS as any[];
});

describe("chat agent — anti-fabrication policy is present", () => {
  const mustContain: Array<[string, RegExp]> = [
    ["never invent a duct/equipment model", /never invent a model yourself/i],
    ["never estimate an auto-sized grille split", /never estimate a size split/i],
    ["auto-sized true sizes are not in the file", /TRUE sizes.*are NOT in the file/i],
    ["must not invent per-size flex piece counts", /NOT invent how many pieces are a specific size/i],
    ["identify parts via catalog before guessing", /Identify parts via the catalog tools before guessing/i],
    ["drawing run names are not BOM rows", /NOT rows in the BOM report/i],
    ["heat strips have no standing rule", /there is NO standing rule/i],
    ["don't fabricate standing-rule auto-apply", /never claim it will auto-apply to future BOMs/i],
  ];
  for (const [name, re] of mustContain) {
    it(name, () => {
      assert.match(SYSTEM_PROMPT, re,
        `system prompt lost its "${name}" guarantee`);
    });
  }
});

describe("chat agent — tools can't add a line without identifying it", () => {
  it("propose_add_line requires sku + description + quantity", () => {
    const add = TOOLS.find((t) => t.name === "propose_add_line");
    assert.ok(add, "propose_add_line tool missing");
    const req: string[] = add.input_schema.required ?? [];
    for (const field of ["sku", "description", "quantity", "reason"]) {
      assert.ok(req.includes(field),
        `propose_add_line must require "${field}" so the agent can't add a nameless/uncosted line`);
    }
  });

  it("propose_line_update requires an sku + a reason", () => {
    const upd = TOOLS.find((t) => t.name === "propose_line_update");
    assert.ok(upd, "propose_line_update tool missing");
    const req: string[] = upd.input_schema.required ?? [];
    assert.ok(req.includes("sku"), "update must target a real sku");
    assert.ok(req.includes("reason"), "update must carry a justification");
  });

  it("every proposal tool is a proposal (human applies) — no auto-mutate tool exists", () => {
    // The design invariant: the agent proposes; nothing mutates without
    // a human click. Any tool that reads/writes the BOM is a propose_*.
    const mutating = TOOLS.filter((t) =>
      /line|regenerate|apply|remove|add|update/i.test(t.name));
    for (const t of mutating) {
      assert.ok(t.name.startsWith("propose_"),
        `tool "${t.name}" mutates but is not a propose_* (human-in-the-loop) tool`);
    }
  });
});
