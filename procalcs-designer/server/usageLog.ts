// Fire-and-forget usage telemetry → procalcs-bom /api/v1/usage-events.
//
// Day-25. Adoption + learning-loop monitoring: every meaningful
// interaction (chat message, attachment upload, …) posts one event.
// The BOM service derives provenance server-side from the forwarded
// user identity — test actors (Gerald/dev) are stored but excluded
// from metrics, so Gerald can exercise the whole surface without
// polluting the numbers.
//
// Telemetry must NEVER break the user's flow: no await at call sites,
// all failures swallowed with a warn.

import type { Request } from "express";
import { config } from "./config.js";
import { buildUpstreamHeaders } from "./upstreamHeaders.js";

export function logUsage(
  req: Request,
  event: string,
  detail?: Record<string, unknown>,
  extra?: { client_id?: string; job_id?: string; run_id?: number },
): void {
  try {
    const url = `${config.flaskBomBaseUrl}/api/v1/usage-events`;
    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...buildUpstreamHeaders(req),
      },
      body: JSON.stringify({ event, detail, ...extra }),
      signal: AbortSignal.timeout(5_000),
    }).then((res) => {
      if (!res.ok) console.warn(`[usage] ${event} → HTTP ${res.status}`);
    }).catch((err) => {
      console.warn(`[usage] ${event} event failed (non-fatal):`,
        err instanceof Error ? err.message : err);
    });
  } catch (err) {
    // Sync throws (bad config, header encoding) must not reach the
    // caller — a telemetry bug once double-sent a chat response here.
    console.warn(`[usage] ${event} sync failure (non-fatal):`,
      err instanceof Error ? `${err.name}: ${err.message}` : err);
  }
}
