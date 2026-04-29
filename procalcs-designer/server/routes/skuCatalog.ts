// /api/sku-catalog/* — proxy to procalcs-hvac-bom /api/v1/sku-catalog/*.
//
// Pattern mirrors clientProfiles.ts: small JSON envelope wrapper +
// requireAuth (mounted at index.ts) + shared-secret + actor headers
// forwarded to the BOM service.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";

const router = Router();

interface FlaskEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta?: Record<string, unknown>;
}

function authHeaders(req: Request): Record<string, string> {
  const headers: Record<string, string> = { "X-Client-Id": config.clientId };
  if (config.serviceSharedSecret) {
    headers["X-Procalcs-Service-Token"] = config.serviceSharedSecret;
  }
  // Best-effort actor attribution for the audit trail. requireAuth puts
  // the user on req.user, so prefer that when we can see it.
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
  const url = `${config.flaskBomBaseUrl}/api/v1/sku-catalog${path}`;
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

// ─── List ──────────────────────────────────────────────────────────────────
router.get("/", async (req: Request, res: Response) => {
  try {
    const qs = new URLSearchParams();
    if (req.query.section) qs.set("section", String(req.query.section));
    if (req.query.supplier) qs.set("supplier", String(req.query.supplier));
    if (req.query.include_disabled !== undefined) {
      qs.set("include_disabled", String(req.query.include_disabled));
    }
    const path = qs.toString() ? `/?${qs.toString()}` : "/";
    const { status, envelope, raw } = await callFlask(req, path);
    res.status(status).type("application/json").send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({ success: false, data: null, error: err?.message ?? "List failed" });
  }
});

// ─── Meta (form enums) ─────────────────────────────────────────────────────
router.get("/_meta", async (req: Request, res: Response) => {
  try {
    const { status, envelope, raw } = await callFlask(req, "/_meta");
    res.status(status).type("application/json").send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({ success: false, data: null, error: err?.message ?? "Meta failed" });
  }
});

// ─── Get one ───────────────────────────────────────────────────────────────
router.get("/:sku", async (req: Request, res: Response) => {
  try {
    const sku = encodeURIComponent(String(req.params.sku));
    const { status, envelope, raw } = await callFlask(req, `/${sku}`);
    res.status(status).type("application/json").send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({ success: false, data: null, error: err?.message ?? "Get failed" });
  }
});

// ─── Create ────────────────────────────────────────────────────────────────
router.post("/", async (req: Request, res: Response) => {
  try {
    const { status, envelope, raw } = await callFlask(req, "/", {
      method: "POST",
      body: JSON.stringify(req.body ?? {}),
    });
    res.status(status).type("application/json").send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({ success: false, data: null, error: err?.message ?? "Create failed" });
  }
});

// ─── Update ────────────────────────────────────────────────────────────────
router.put("/:sku", async (req: Request, res: Response) => {
  try {
    const sku = encodeURIComponent(String(req.params.sku));
    const { status, envelope, raw } = await callFlask(req, `/${sku}`, {
      method: "PUT",
      body: JSON.stringify(req.body ?? {}),
    });
    res.status(status).type("application/json").send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({ success: false, data: null, error: err?.message ?? "Update failed" });
  }
});

// ─── Disable / Enable ──────────────────────────────────────────────────────
router.post("/:sku/disable", async (req: Request, res: Response) => {
  try {
    const sku = encodeURIComponent(String(req.params.sku));
    const { status, envelope, raw } = await callFlask(req, `/${sku}/disable`, { method: "POST" });
    res.status(status).type("application/json").send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({ success: false, data: null, error: err?.message ?? "Disable failed" });
  }
});

router.post("/:sku/enable", async (req: Request, res: Response) => {
  try {
    const sku = encodeURIComponent(String(req.params.sku));
    const { status, envelope, raw } = await callFlask(req, `/${sku}/enable`, { method: "POST" });
    res.status(status).type("application/json").send(envelope ? JSON.stringify(envelope) : raw);
  } catch (err: any) {
    res.status(502).json({ success: false, data: null, error: err?.message ?? "Enable failed" });
  }
});

// ─── Delete ────────────────────────────────────────────────────────────────
router.delete("/:sku", async (req: Request, res: Response) => {
  try {
    const sku = encodeURIComponent(String(req.params.sku));
    const upstreamUrl = `${config.flaskBomBaseUrl}/api/v1/sku-catalog/${sku}`;
    const upstream = await fetch(upstreamUrl, {
      method: "DELETE",
      headers: authHeaders(req),
    });
    if (upstream.status === 204) {
      res.status(204).end();
      return;
    }
    const text = await upstream.text();
    res.status(upstream.status).type("application/json").send(text || "{}");
  } catch (err: any) {
    res.status(502).json({ success: false, data: null, error: err?.message ?? "Delete failed" });
  }
});

export default router;
