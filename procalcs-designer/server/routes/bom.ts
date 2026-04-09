// /api/bom/* — proxy to procalcs-hvac-bom /api/v1/bom/*.
//
// Two branches:
//   - /parse-rup                  → stream the raw multipart body through
//                                    (mirrors server/routes/pdfCleanup.ts)
//   - everything else (/generate) → forward as JSON
//
// Both forward the Flask {success, data, error} envelope verbatim so the
// SPA hooks can unwrap .data themselves. The bypass for express.json() on
// /api/bom/parse-rup is wired in server/index.ts.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";

const router = Router();

router.all("/*splat", async (req: Request, res: Response) => {
  const upstreamUrl = `${config.flaskBomBaseUrl}/api/v1/bom${req.path}`;

  // ─── Multipart / raw-binary branch: /parse-rup ──────────────────────
  if (req.path === "/parse-rup") {
    try {
      const headers: Record<string, string> = {};
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

  // ─── JSON branch: everything else (e.g. /generate) ──────────────────
  try {
    const upstream = await fetch(upstreamUrl, {
      method: req.method,
      headers: { "Content-Type": "application/json" },
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
