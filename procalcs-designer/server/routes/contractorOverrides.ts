// /api/contractor-overrides/* — proxy to procalcs-hvac-bom
// /api/v1/contractor-overrides/*.
//
// Backs the Day-13 inline-edit drawer on the Wrightsoft BOM page +
// the manual-corrections ledger surface. Same pattern as skuCatalog.ts:
// envelope unwrapping, shared-secret auth, actor-email forwarded so
// the backend audit trail captures who saved each correction.

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
  const url = `${config.flaskBomBaseUrl}/api/v1/contractor-overrides${path}`;
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

// GET / — list overrides for a contractor (?client_id=…)
router.get("/", async (req: Request, res: Response) => {
  try {
    const qs = new URLSearchParams();
    if (req.query.client_id) qs.set("client_id", String(req.query.client_id));
    const path = qs.toString() ? `?${qs.toString()}` : "";
    const { status, envelope, raw } = await callFlask(req, path);
    res.status(status).type("application/json")
       .send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({
      success: false, data: null,
      error: err?.message ?? "List overrides failed",
    });
  }
});

// POST / — upsert one (client_id, supplier, sku) override
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
      error: err?.message ?? "Save override failed",
    });
  }
});

// POST /import — bulk CSV/XLSX upload (Day-16).
// Streams the raw multipart body upstream so Flask's werkzeug handles
// the file boundary the same way it does for /api/bom/from-wrightsoft.
router.post("/import", async (req: Request, res: Response) => {
  try {
    const url = `${config.flaskBomBaseUrl}/api/v1/contractor-overrides/import`;
    const upstream = await fetch(url, {
      method: "POST",
      headers: {
        // DO NOT set Content-Type — fetch derives the multipart boundary
        // from the body. We pass the original content-type header through.
        ...(req.headers["content-type"]
          ? { "Content-Type": req.headers["content-type"] as string }
          : {}),
        ...authHeaders(req),
      },
      body: req as any,
      // Node fetch needs duplex:'half' when streaming a request body;
      // typed via cast because RequestInit doesn't declare it.
      duplex: "half",
    } as RequestInit);
    const raw = await upstream.text();
    res.status(upstream.status).type("application/json").send(raw);
  } catch (err: any) {
    res.status(502).json({
      success: false, data: null,
      error: err?.message ?? "Import overrides failed",
    });
  }
});

// DELETE /:id
router.delete("/:id", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    const { status, envelope, raw } = await callFlask(req, `/${id}`, {
      method: "DELETE",
    });
    res.status(status).type("application/json")
       .send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({
      success: false, data: null,
      error: err?.message ?? "Delete override failed",
    });
  }
});

export default router;
