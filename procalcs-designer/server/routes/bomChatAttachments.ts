// /api/bom-chat/attachments — attachment intake for the BOM Review
// Assistant (Day-24).
//
// Architecture: two-phase, stateless chat.
//   1. The client uploads files HERE first. Extraction happens ONCE
//      at upload; the response carries {id, name, kind, summary,
//      extracted?, image_b64?} which the client holds in chat state.
//   2. Chat turns send those extractions along with messages — no
//      server-side session state, so any instance serves any turn.
//
// Durability: raw bytes are copied to a GCS bucket with a 7-day
// lifecycle rule (audit / re-use), best-effort — a GCS hiccup never
// blocks the chat. Extraction:
//   .rup                → proxied to the Flask BOM backend /parse-rup
//                         (reuse the real parser, don't re-implement)
//   .xls/.xlsx/.csv     → SheetJS → CSV text per sheet
//   .pdf                → text layer (pdf-parse)
//   .docx               → mammoth → plain text
//   .txt/.md/.json      → as-is
//   .png/.jpg/.webp/.gif→ passed through as base64 for Claude vision
// Limits: 20 MB/file (rup ceiling), 5 files/request, 30k chars of
// extraction per file enters chat context.

import { Router, type Request, type Response } from "express";
import multer from "multer";
import crypto from "node:crypto";
import { config } from "../config.js";
import { buildUpstreamHeaders } from "../upstreamHeaders.js";
import { logUsage } from "../usageLog.js";

const router = Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 20 * 1024 * 1024, files: 5 },
});

const EXTRACT_CAP = 30_000;
const IMAGE_EXTS = new Set(["png", "jpg", "jpeg", "webp", "gif"]);
const IMAGE_MIME: Record<string, string> = {
  png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg",
  webp: "image/webp", gif: "image/gif",
};

function ext(name: string): string {
  return (name.split(".").pop() || "").toLowerCase();
}

async function gcsPut(id: string, name: string, buf: Buffer): Promise<void> {
  const bucket = process.env.CHAT_UPLOADS_BUCKET;
  if (!bucket) return;
  try {
    const { Storage } = await import("@google-cloud/storage");
    await new Storage().bucket(bucket)
      .file(`${id}/${name}`)
      .save(buf, { resumable: false });
  } catch (err) {
    console.warn("[chat-attachments] GCS store skipped:",
                 err instanceof Error ? err.message : err);
  }
}

async function extractRup(req: Request, name: string, buf: Buffer) {
  const form = new FormData();
  form.append("file", new Blob([new Uint8Array(buf)]), name);
  const upstream = await fetch(`${config.flaskBomBaseUrl}/api/v1/bom/parse-rup`, {
    method: "POST",
    headers: buildUpstreamHeaders(req),
    body: form,
  });
  const body = await upstream.json().catch(() => null) as {
    success?: boolean; data?: Record<string, unknown>; error?: string;
  } | null;
  if (!body?.success || !body.data) {
    return { summary: "Wrightsoft design file (could not parse)",
             extracted: body?.error ?? "parse failed" };
  }
  const d = body.data;
  const equipment = (d.equipment as unknown[] | undefined) ?? [];
  const rooms = (d.rooms as unknown[] | undefined) ?? [];
  const summary =
    `Wrightsoft design file: ${(d.project as { name?: string } | undefined)?.name ?? name} — ` +
    `${equipment.length} equipment units, ${rooms.length} rooms.`;
  // Structured design data, trimmed of the bulky narrative context.
  const { raw_rup_context, ...core } = d as Record<string, unknown>;
  const extracted = JSON.stringify(core).slice(0, EXTRACT_CAP);
  return { summary, extracted };
}

async function extractSpreadsheet(name: string, buf: Buffer) {
  const XLSX = await import("xlsx");
  const wb = XLSX.read(buf, { type: "buffer" });
  const parts: string[] = [];
  for (const sheet of wb.SheetNames.slice(0, 5)) {
    parts.push(`--- sheet: ${sheet} ---\n` +
               XLSX.utils.sheet_to_csv(wb.Sheets[sheet]));
  }
  const text = parts.join("\n");
  return {
    summary: `Spreadsheet: ${wb.SheetNames.length} sheet(s).`,
    extracted: text.slice(0, EXTRACT_CAP),
  };
}

async function extractPdf(buf: Buffer) {
  const { default: pdfParse } = await import("pdf-parse");
  const parsed = await pdfParse(buf);
  return {
    summary: `PDF, ${parsed.numpages} page(s).`,
    extracted: (parsed.text || "").trim().slice(0, EXTRACT_CAP),
  };
}

async function extractDocx(buf: Buffer) {
  const mammoth = await import("mammoth");
  const out = await mammoth.extractRawText({ buffer: buf });
  return {
    summary: "Word document.",
    extracted: (out.value || "").trim().slice(0, EXTRACT_CAP),
  };
}

router.post("/", upload.array("files", 5),
            async (req: Request, res: Response) => {
  const files = (req.files as Express.Multer.File[] | undefined) ?? [];
  if (!files.length) {
    res.status(400).json({ success: false, data: null,
                           error: "no files attached (field name: files)" });
    return;
  }
  const results = [];
  for (const f of files) {
    const id = crypto.randomUUID();
    const e = ext(f.originalname);
    const base = { id, name: f.originalname, size: f.size, kind: e };
    void gcsPut(id, f.originalname, f.buffer); // fire-and-forget audit copy
    try {
      if (e === "rup") {
        results.push({ ...base, kind: "rup",
                       ...(await extractRup(req, f.originalname, f.buffer)) });
      } else if (["xls", "xlsx", "csv"].includes(e)) {
        results.push({ ...base, kind: "spreadsheet",
                       ...(await extractSpreadsheet(f.originalname, f.buffer)) });
      } else if (e === "pdf") {
        results.push({ ...base, kind: "pdf", ...(await extractPdf(f.buffer)) });
      } else if (e === "docx") {
        results.push({ ...base, kind: "docx", ...(await extractDocx(f.buffer)) });
      } else if (["txt", "md", "json", "yaml", "yml"].includes(e)) {
        results.push({ ...base, kind: "text",
                       summary: `Text file (${f.size} bytes).`,
                       extracted: f.buffer.toString("utf-8").slice(0, EXTRACT_CAP) });
      } else if (IMAGE_EXTS.has(e)) {
        if (f.size > 5 * 1024 * 1024) {
          results.push({ ...base, kind: "unsupported",
                         summary: "Image exceeds the 5 MB vision limit." });
        } else {
          results.push({ ...base, kind: "image",
                         summary: `Image (${IMAGE_MIME[e]}).`,
                         media_type: IMAGE_MIME[e],
                         image_b64: f.buffer.toString("base64") });
        }
      } else {
        results.push({ ...base, kind: "unsupported",
                       summary: `Unsupported type .${e} — accepted: rup, xls/xlsx/csv, pdf, docx, txt/md/json, png/jpg/webp/gif.` });
      }
    } catch (err) {
      results.push({ ...base, kind: "error",
                     summary: `Could not read this file: ${err instanceof Error ? err.message : err}` });
    }
  }
  res.json({ success: true, data: { attachments: results }, error: null });
  logUsage(req, "attachment_uploaded", {
    files: results.length,
    kinds: results.map((r) => r.kind),
  });
});

export default router;
