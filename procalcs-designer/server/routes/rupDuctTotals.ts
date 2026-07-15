// /api/rup-duct-totals/* — proxy to procalcs-hvac-bom
// /api/v1/rup-duct-totals/*.
//
// Backs the Day-14 Phase 4 known-duct-LF cache. The SPA POSTs on
// Continue from the BOM Engine page; the GET path isn't called by
// the SPA directly because /parse-rup bundles cached totals into
// the response, but it's exposed for parity + ad-hoc debugging.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";

const router = Router();

interface FlaskEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

function authHeaders(req: Request): Record<string, string> {
  const headers: Record<string, string> = { "X-Client-Id": config.clientId };
  if (config.serviceSharedSecret) {
    headers["X-Procalcs-Service-Token"] = config.serviceSharedSecret;
  }
  const actor =
    (req as unknown as { user?: { email?: string } }).user?.email;
  if (actor) headers["X-Actor-Email"] = actor;
  return headers;
}

async function callFlask<T>(
  req: Request,
  path: string,
  init?: RequestInit
): Promise<{ status: number; envelope: FlaskEnvelope<T> | null; raw: string }> {
  const url = `${config.flaskBomBaseUrl}/api/v1/rup-duct-totals${path}`;
  const upstream = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(req),
      ...(init?.headers || {}),
    },
    ...init,
  });
  const raw = await upstream.text();
  let envelope: FlaskEnvelope<T> | null = null;
  if (raw) {
    try {
      envelope = JSON.parse(raw) as FlaskEnvelope<T>;
    } catch {
      envelope = null;
    }
  }
  return { status: upstream.status, envelope, raw };
}

// GET /:rup_hash — fetch cached totals
router.get("/:rup_hash", async (req: Request, res: Response) => {
  try {
    const h = encodeURIComponent(String(req.params.rup_hash));
    const { status, envelope, raw } = await callFlask(req, `/${h}`);
    res.status(status).type("application/json")
       .send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({
      success: false, data: null,
      error: err?.message ?? "Lookup failed",
    });
  }
});

// POST / — upsert
router.post("/", async (req: Request, res: Response) => {
  try {
    const { status, envelope, raw } = await callFlask(req, "", {
      method: "POST",
      body: JSON.stringify(req.body ?? {}),
    });
    res.status(status).type("application/json")
       .send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({
      success: false, data: null,
      error: err?.message ?? "Save failed",
    });
  }
});

export default router;
