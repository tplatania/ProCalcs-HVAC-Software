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
