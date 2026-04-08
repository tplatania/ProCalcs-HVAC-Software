// /api/pdf-cleanup/* — transparent proxy to procalcs-hvac-cleaner
// /api/v1/tools/pdf-to-cad/*. Supports file uploads by streaming the raw body
// through. The Flask side returns {job_id, stats, download_url} for uploads
// and streams binary for /download/<job_id>.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";

const router = Router();

router.all("/*splat", async (req: Request, res: Response) => {
  try {
    // Forward the raw body (and content-type) unchanged so multipart uploads
    // from the SPA's FormData work without Express parsing them.
    const headers: Record<string, string> = {};
    const ct = req.headers["content-type"];
    if (ct) headers["Content-Type"] = Array.isArray(ct) ? ct[0] : ct;

    const upstream = await fetch(
      `${config.flaskCleanerBaseUrl}/api/v1/tools/pdf-to-cad${req.path}`,
      {
        method: req.method,
        headers,
        body:
          req.method === "GET" || req.method === "HEAD" ? undefined : (req as any),
        // @ts-ignore — undici-specific, needed to stream request bodies
        duplex: "half",
      }
    );
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
    res.status(502).json({ error: err?.message ?? "Cleaner upstream failed" });
  }
});

export default router;
