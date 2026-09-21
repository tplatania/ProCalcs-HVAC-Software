// /api/feedback/* — proxy to procalcs-hvac-bom /api/v1/feedback/*.
//
// In-app feedback / ask threads (testers + team, with screenshots).
// Same shape as bomRuns.ts: forward the {success,data,error} envelope
// verbatim with the shared-secret + actor headers so the BOM service
// attributes each thread/message to the signed-in user (author is set
// upstream from X-Procalcs-User-Email, never the request body).
//
// Two multipart routes (create thread, append message) rebuild the
// upload as FormData and stream it upstream — mirrors the extractRup
// forward in bomChatAttachments.ts. Attachment GET pipes bytes back
// with the upstream content-type.

import { Router, type Request, type Response } from "express";
import multer from "multer";
import { config } from "../config.js";
import { buildUpstreamHeaders } from "../upstreamHeaders.js";

const router = Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 8 * 1024 * 1024, files: 5 },
});

const UPSTREAM_TIMEOUT_MS = 30_000;
const BASE = () => `${config.flaskBomBaseUrl}/api/v1/feedback`;

function describeUpstreamError(err: unknown): string {
  if (err && typeof err === "object" && "name" in err) {
    const name = String((err as { name: unknown }).name);
    if (name === "AbortError" || name === "TimeoutError")
      return `upstream timed out (${UPSTREAM_TIMEOUT_MS / 1000}s)`;
    if (name === "TypeError")
      return `upstream unreachable — ${(err as { message?: string }).message ?? "network error"}`;
  }
  return err instanceof Error ? err.message : String(err);
}

function sendUpstreamError(res: Response, err: unknown, op: string): void {
  const detail = describeUpstreamError(err);
  console.error(`[feedback] ${op} failed:`, detail);
  res.status(502).json({ success: false, data: null, error: `${op} failed: ${detail}` });
}

/** Forward a JSON request and echo the envelope + status verbatim. */
async function proxyJson(
  req: Request, res: Response, path: string, op: string,
  init?: RequestInit,
): Promise<void> {
  try {
    const upstream = await fetch(`${BASE()}${path}`, {
      headers: {
        "Content-Type": "application/json",
        ...buildUpstreamHeaders(req),
        ...(init?.headers || {}),
      },
      ...init,
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const raw = await upstream.text();
    res.status(upstream.status).type("application/json").send(raw);
  } catch (err) {
    sendUpstreamError(res, err, op);
  }
}

/** Forward a multipart submission (text fields + files) upstream. */
async function proxyMultipart(
  req: Request, res: Response, path: string, op: string,
): Promise<void> {
  try {
    const form = new FormData();
    for (const [k, v] of Object.entries(req.body ?? {})) {
      if (v !== undefined && v !== null) form.append(k, String(v));
    }
    const files = (req.files as Express.Multer.File[] | undefined) ?? [];
    for (const f of files) {
      form.append("attachments",
        new Blob([new Uint8Array(f.buffer)], { type: f.mimetype }),
        f.originalname);
    }
    const upstream = await fetch(`${BASE()}${path}`, {
      method: "POST",
      headers: buildUpstreamHeaders(req), // let fetch set multipart boundary
      body: form,
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const raw = await upstream.text();
    res.status(upstream.status).type("application/json").send(raw);
  } catch (err) {
    sendUpstreamError(res, err, op);
  }
}

// ─── List ────────────────────────────────────────────────────────────
router.get("/threads", async (req, res) => {
  const qs = new URLSearchParams();
  for (const k of ["status", "kind", "mine"]) {
    const v = req.query[k];
    if (v !== undefined && v !== "") qs.set(k, String(v));
  }
  await proxyJson(req, res, qs.toString() ? `/threads?${qs}` : "/threads",
                  "List feedback");
});

// ─── Detail ──────────────────────────────────────────────────────────
router.get("/threads/:id", async (req, res) => {
  await proxyJson(req, res, `/threads/${encodeURIComponent(req.params.id)}`,
                  "Get thread");
});

// ─── Create (multipart) ──────────────────────────────────────────────
router.post("/threads", upload.array("attachments", 5), async (req, res) => {
  await proxyMultipart(req, res, "/threads", "Create thread");
});

// ─── Append message (multipart) ──────────────────────────────────────
router.post("/threads/:id/messages", upload.array("attachments", 5),
            async (req, res) => {
  await proxyMultipart(req, res,
    `/threads/${encodeURIComponent(req.params.id)}/messages`, "Add message");
});

// ─── Resolve ─────────────────────────────────────────────────────────
router.post("/threads/:id/resolve", async (req, res) => {
  await proxyJson(req, res,
    `/threads/${encodeURIComponent(req.params.id)}/resolve`, "Resolve thread",
    { method: "POST", body: JSON.stringify(req.body ?? {}) });
});

// ─── Attachment bytes (pipe upstream content-type) ───────────────────
router.get("/attachments/:id", async (req, res) => {
  try {
    const upstream = await fetch(
      `${BASE()}/attachments/${encodeURIComponent(req.params.id)}`,
      { headers: buildUpstreamHeaders(req),
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS) });
    if (!upstream.ok) {
      const raw = await upstream.text();
      res.status(upstream.status).type("application/json").send(raw);
      return;
    }
    const ct = upstream.headers.get("content-type") ?? "application/octet-stream";
    const cd = upstream.headers.get("content-disposition");
    const buf = Buffer.from(await upstream.arrayBuffer());
    res.status(200).type(ct);
    if (cd) res.setHeader("Content-Disposition", cd);
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.send(buf);
  } catch (err) {
    sendUpstreamError(res, err, "Get attachment");
  }
});

export default router;
