// /api/bom/* — proxy to procalcs-hvac-bom /api/v1/bom/*.
//
// Three branches:
//   - /parse-rup   → stream the raw multipart body through (binary in,
//                    JSON out) — mirrors server/routes/pdfCleanup.ts
//   - /render-pdf  → forward JSON body, stream the binary PDF response
//                    back to the client unchanged
//   - everything else (/generate) → plain JSON in, JSON out
//
// The JSON-body routes forward the Flask {success, data, error}
// envelope verbatim so the SPA hooks can unwrap .data themselves.
// The bypass for express.json() on /api/bom/parse-rup is wired in
// server/index.ts.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";
import { buildUpstreamHeaders } from "../upstreamHeaders.js";

const router = Router();

router.all("/*splat", async (req: Request, res: Response) => {
  const upstreamUrl = `${config.flaskBomBaseUrl}/api/v1/bom${req.path}`;

  // ─── Multipart / raw-binary branch: /parse-rup ──────────────────────
  if (req.path === "/parse-rup") {
    try {
      const headers: Record<string, string> = { ...buildUpstreamHeaders(req) };
      const ct = req.headers["content-type"];
      if (ct) headers["Content-Type"] = Array.isArray(ct) ? ct[0] : ct;

      const upstream = await fetch(upstreamUrl, {
        method: req.method,
        headers,
        body:
          req.method === "GET" || req.method === "HEAD" ? undefined : (req as any),
        // @ts-ignore — undici-specific, needed to stream request bodies
        duplex: "half",
      });

      res.status(upstream.status);
      upstream.headers.forEach((v, k) => {
        if (k.toLowerCase() === "content-length") return;
        res.setHeader(k, v);
      });
      if (upstream.body) {
        const reader = upstream.body.getReader();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          res.write(value);
        }
        res.end();
      } else {
        res.end();
      }
    } catch (err: any) {
      res.status(502).json({ error: err?.message ?? "parse-rup upstream failed" });
    }
    return;
  }

  // ─── JSON in, binary out: /render-pdf ───────────────────────────────
  if (req.path === "/render-pdf") {
    try {
      const upstream = await fetch(upstreamUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...buildUpstreamHeaders(req) },
        body: JSON.stringify(req.body ?? {}),
      });

      res.status(upstream.status);
      // Forward the PDF-relevant response headers (Content-Type,
      // Content-Disposition). Drop Content-Length since we're streaming.
      upstream.headers.forEach((v, k) => {
        if (k.toLowerCase() === "content-length") return;
        res.setHeader(k, v);
      });

      if (upstream.body) {
        const reader = upstream.body.getReader();
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          res.write(value);
        }
        res.end();
      } else {
        res.end();
      }
    } catch (err: any) {
      res.status(502).json({ error: err?.message ?? "render-pdf upstream failed" });
    }
    return;
  }

  // ─── JSON branch: everything else (e.g. /generate) ──────────────────
  try {
    const upstream = await fetch(upstreamUrl, {
      method: req.method,
      headers: { "Content-Type": "application/json", ...buildUpstreamHeaders(req) },
      body:
        req.method === "GET" || req.method === "HEAD"
          ? undefined
          : JSON.stringify(req.body ?? {}),
    });
    const text = await upstream.text();
    res.status(upstream.status);
    res.setHeader(
      "Content-Type",
      upstream.headers.get("content-type") ?? "application/json"
    );
    res.send(text);
  } catch (err: any) {
    res.status(502).json({ error: err?.message ?? "BOM upstream failed" });
  }
});

export default router;
