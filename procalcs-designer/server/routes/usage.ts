// /api/usage/* — read-side proxy to procalcs-bom /api/v1/usage-events.
//
// Day-25. Two views:
//   GET /api/usage/summary?days=30   — adoption (who's using it, how)
//   GET /api/usage/impact?client_id= — learning loop (corrections ×
//                                      auto-re-applications on later
//                                      BOMs). Feeds the transparency
//                                      panel in the Review Assistant.
//
// Write-side events post upstream directly via usageLog.ts — this
// router is read-only. Envelope forwarded verbatim like bomRuns.ts.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";
import { buildUpstreamHeaders } from "../upstreamHeaders.js";

const router = Router();
const UPSTREAM_TIMEOUT_MS = 15_000;

async function forward(req: Request, res: Response, path: string) {
  const qs = new URLSearchParams(
    req.query as Record<string, string>).toString();
  const url = `${config.flaskBomBaseUrl}/api/v1/usage-events${path}` +
    (qs ? `?${qs}` : "");
  try {
    const upstream = await fetch(url, {
      headers: buildUpstreamHeaders(req),
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
    const body = await upstream.json().catch(() => null);
    res.status(upstream.status).json(
      body ?? { success: false, data: null, error: "bad upstream response" });
  } catch (err) {
    res.status(502).json({
      success: false, data: null,
      error: err instanceof Error ? err.message : String(err),
    });
  }
}

router.get("/summary", (req, res) => forward(req, res, "/summary"));
router.get("/impact",  (req, res) => forward(req, res, "/impact"));

export default router;
