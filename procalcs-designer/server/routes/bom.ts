// /api/bom/* — transparent proxy to procalcs-hvac-bom /api/v1/bom/*.
// No shape translation needed; the BOM generate endpoint already returns JSON
// the SPA can render directly. The Flask envelope ({success, data, error}) is
// forwarded verbatim — page components can unwrap .data themselves.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";

const router = Router();

router.all("/*splat", async (req: Request, res: Response) => {
  try {
    const upstream = await fetch(
      `${config.flaskBomBaseUrl}/api/v1/bom${req.path}`,
      {
        method: req.method,
        headers: {
          "Content-Type": "application/json",
        },
        body:
          req.method === "GET" || req.method === "HEAD"
            ? undefined
            : JSON.stringify(req.body ?? {}),
      }
    );
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
