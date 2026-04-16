// /api/dashboard/summary — computed server-side from the client-profiles list
// because the Flask backend doesn't expose a dashboard summary endpoint.
// The prior (deleted) api-server persisted its own aggregate in Postgres;
// we intentionally replaced that with on-the-fly computation.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";
import {
  flattenProfile,
  summarizeProfiles,
  type PythonClientProfile,
} from "../adapters.js";

const router = Router();

interface FlaskEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
}

router.get("/summary", async (_req: Request, res: Response) => {
  try {
    const authHeaders: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Client-Id": config.clientId,
    };
    if (config.serviceSharedSecret) {
      authHeaders["X-Procalcs-Service-Token"] = config.serviceSharedSecret;
    }
    const upstream = await fetch(
      `${config.flaskBomBaseUrl}/api/v1/profiles/`,
      { headers: authHeaders }
    );
    const body = (await upstream.json().catch(() => ({}))) as FlaskEnvelope<
      PythonClientProfile[]
    >;
    if (!upstream.ok || !body.success) {
      throw new Error(body?.error || `Flask ${upstream.status}`);
    }
    const flat = (body.data ?? []).map(flattenProfile);
    res.json(summarizeProfiles(flat));
  } catch (err: any) {
    res.status(500).json({ error: err?.message ?? "Summary failed" });
  }
});

export default router;
