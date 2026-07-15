// /api/client-profiles CRUD — adapts between the SPA's flat camelCase shape
// and the Flask/Firestore nested snake_case shape.
// Talks to:  ${FLASK_BOM_BASE_URL}/api/v1/profiles/

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";
import {
  flattenProfile,
  unflattenProfile,
  type PythonClientProfile,
} from "../adapters.js";

const router = Router();

interface FlaskEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

async function callFlask<T>(
  path: string,
  init?: RequestInit
): Promise<FlaskEnvelope<T>> {
  const authHeaders: Record<string, string> = { "X-Client-Id": config.clientId };
  if (config.serviceSharedSecret) {
    authHeaders["X-Procalcs-Service-Token"] = config.serviceSharedSecret;
  }
  const res = await fetch(`${config.flaskBomBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      ...(init?.headers || {}),
    },
    ...init,
  });
  const body = (await res.json().catch(() => ({}))) as FlaskEnvelope<T>;
  if (!res.ok || !body.success) {
    throw {
      status: res.status,
      message: body?.error || `Flask ${res.status}`,
    };
  }
  return body;
}

// GET /api/client-profiles → list
router.get("/", async (_req: Request, res: Response) => {
  try {
    const envelope = await callFlask<PythonClientProfile[]>(
      "/api/v1/profiles/"
    );
    const flat = (envelope.data ?? []).map(flattenProfile);
    res.json(flat);
  } catch (err: any) {
    res.status(err.status ?? 500).json({ error: err.message ?? "List failed" });
  }
});

// GET /api/client-profiles/:id
router.get("/:id", async (req: Request, res: Response) => {
  try {
    const envelope = await callFlask<PythonClientProfile>(
      `/api/v1/profiles/${encodeURIComponent(String(req.params.id))}`
    );
    if (!envelope.data) {
      return res.status(404).json({ error: "Profile not found" });
    }
    res.json(flattenProfile(envelope.data));
  } catch (err: any) {
    res.status(err.status ?? 500).json({ error: err.message ?? "Get failed" });
  }
});

// POST /api/client-profiles — create
router.post("/", async (req: Request, res: Response) => {
  try {
    const pythonBody = unflattenProfile(req.body);
    const envelope = await callFlask<PythonClientProfile>(
      "/api/v1/profiles/",
      {
        method: "POST",
        body: JSON.stringify(pythonBody),
      }
    );
    res.status(201).json(flattenProfile(envelope.data!));
  } catch (err: any) {
    res.status(err.status ?? 500).json({ error: err.message ?? "Create failed" });
  }
});

// PUT /api/client-profiles/:id — update
router.put("/:id", async (req: Request, res: Response) => {
  try {
    // Fetch existing first so we preserve fields the SPA doesn't touch
    let existing: PythonClientProfile | undefined;
    try {
      const current = await callFlask<PythonClientProfile>(
        `/api/v1/profiles/${encodeURIComponent(String(req.params.id))}`
      );
      existing = current.data ?? undefined;
    } catch {
      /* not fatal — proceed without merge */
    }
    const pythonBody = unflattenProfile(
      { ...req.body, id: String(req.params.id) },
      existing
    );
    const envelope = await callFlask<PythonClientProfile>(
      `/api/v1/profiles/${encodeURIComponent(String(req.params.id))}`,
      {
        method: "PUT",
        body: JSON.stringify(pythonBody),
      }
    );
    res.json(flattenProfile(envelope.data!));
  } catch (err: any) {
    res.status(err.status ?? 500).json({ error: err.message ?? "Update failed" });
  }
});

// ───── Day-17: Consumables rules + supplier consumable costs ──────
//
// Dedicated GET/PUT for the install-consumables config (mastic, tape,
// flex tape, screws). Lifts a small slice out of the full profile so
// the editor UI doesn't have to round-trip every unrelated field.
// All keys are snake_case to match the upstream Python shape directly.

// Day-17 — dynamic list of consumable items. Each item is per-job
// auto-quantified from one of: joints | flex_runs | fittings | duct_lf
// | per_job. The Express layer just round-trips the array — upstream
// Python (_read_consumables_rules) handles defaults + legacy migration.

interface ConsumableItem {
  key: string;
  name: string;
  description?: string;
  basis: "joints" | "flex_runs" | "fittings" | "duct_lf" | "per_job";
  per_container: number;
  qty_per_job?: number;
  container: string;
  unit_price: number;
  enabled: boolean;
}
interface ConsumablesConfig {
  items: ConsumableItem[];
}

// GET /api/client-profiles/:id/consumables
router.get("/:id/consumables", async (req: Request, res: Response) => {
  try {
    const upstream = await callFlask<PythonClientProfile>(
      `/api/v1/profiles/${encodeURIComponent(String(req.params.id))}`
    );
    const p: any = upstream.data ?? {};
    const rules = p.consumables_rules ?? {};
    // Python from_dict ensures items[] is always present — but we
    // double-belt against an upstream that hasn't been upgraded yet.
    const items: ConsumableItem[] = Array.isArray(rules.items) ? rules.items.map((it: any) => ({
      key:           String(it.key ?? ""),
      name:          String(it.name ?? ""),
      description:   String(it.description ?? ""),
      basis:         (it.basis ?? "joints") as ConsumableItem["basis"],
      per_container: Number(it.per_container ?? 0),
      qty_per_job:   Number(it.qty_per_job ?? 0),
      container:     String(it.container ?? "ea"),
      unit_price:    Number(it.unit_price ?? 0),
      enabled:       it.enabled !== false,
    })) : [];
    res.json({ items } as ConsumablesConfig);
  } catch (err: any) {
    res.status(err.status ?? 500).json({ error: err.message ?? "Fetch failed" });
  }
});

// PUT /api/client-profiles/:id/consumables
router.put("/:id/consumables", async (req: Request, res: Response) => {
  try {
    const id = String(req.params.id);
    // Fetch existing so we don't clobber unrelated fields.
    const current = await callFlask<PythonClientProfile>(
      `/api/v1/profiles/${encodeURIComponent(id)}`
    );
    const existing: any = current.data ?? {};
    const body = req.body as ConsumablesConfig;

    // Surgical merge — only the consumable rules. Supplier untouched.
    const merged: any = {
      ...existing,
      consumables_rules: { items: body.items },
    };
    await callFlask<PythonClientProfile>(
      `/api/v1/profiles/${encodeURIComponent(id)}`,
      { method: "PUT", body: JSON.stringify(merged) }
    );
    res.json({ success: true });
  } catch (err: any) {
    res.status(err.status ?? 500).json({ error: err.message ?? "Update failed" });
  }
});

// DELETE /api/client-profiles/:id
router.delete("/:id", async (req: Request, res: Response) => {
  try {
    await callFlask(
      `/api/v1/profiles/${encodeURIComponent(String(req.params.id))}`,
      { method: "DELETE" }
    );
    res.status(204).send();
  } catch (err: any) {
    res.status(err.status ?? 500).json({ error: err.message ?? "Delete failed" });
  }
});

export default router;
