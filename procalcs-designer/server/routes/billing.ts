// /api/billing/* — proxy to procalcs-hvac-bom /api/v1/billing/*.
//
// Two branches:
//   - /webhook → no requireAuth upstream; Stripe-signed body forwarded
//                verbatim. The Stripe-Signature header MUST survive the
//                proxy intact (express.json() parses + re-serializes,
//                which would invalidate the signature). We bypass the
//                JSON middleware for this path in server/index.ts and
//                stream the raw body through.
//   - everything else (config, me, checkout, portal) → JSON in/out,
//                requireAuth attaches req.user, buildUpstreamHeaders
//                forwards the OAuth email so procalcs-bom JIT-creates
//                the User row.
//
// The Flask {success, data, error} envelope is forwarded verbatim so
// the SPA hooks can unwrap .data themselves.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";
import { buildUpstreamHeaders } from "../upstreamHeaders.js";

const router = Router();

router.all("/*splat", async (req: Request, res: Response) => {
  const upstreamUrl = `${config.flaskBomBaseUrl}/api/v1/billing${req.path}`;

  // ─── Webhook branch — raw body passthrough ───────────────────────────
  // Stripe signs the EXACT bytes it sends. If we re-serialize via
  // express.json() the signature will fail to verify. We must stream
  // the raw bytes through and forward the Stripe-Signature header.
  if (req.path === "/webhook") {
    try {
      const headers: Record<string, string> = {
        "Content-Type": req.headers["content-type"] ?? "application/json",
      };
      // Forward the Stripe signature header — case-insensitive lookup
      // because Express normalizes to lowercase on req.headers.
      const sig = req.headers["stripe-signature"];
      if (sig) {
        headers["Stripe-Signature"] = Array.isArray(sig) ? sig[0] : sig;
      }
      // Add shared-secret + client-id; do NOT add user identity (Stripe
      // is the caller, not a designer).
      Object.assign(headers, buildUpstreamHeaders());

      const upstream = await fetch(upstreamUrl, {
        method: req.method,
        headers,
        body: req.method === "GET" || req.method === "HEAD" ? undefined : (req as any),
        // @ts-ignore — undici-specific, needed to stream request bodies
        duplex: "half",
      });

      const text = await upstream.text();
      res.status(upstream.status);
      res.setHeader(
        "Content-Type",
        upstream.headers.get("content-type") ?? "application/json"
      );
      res.send(text);
    } catch (err: any) {
      res.status(502).json({ error: err?.message ?? "billing webhook upstream failed" });
    }
    return;
  }

  // ─── JSON branch — config, me, checkout, portal ──────────────────────
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
    res.status(502).json({ error: err?.message ?? "billing upstream failed" });
  }
});

export default router;
