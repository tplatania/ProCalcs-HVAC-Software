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

// Returns a promise that ALWAYS resolves (never rejects) so callers can
// safely `await logUsage(...)` before responding. Awaiting matters:
// Cloud Run runs with cpu-throttling on by default, so CPU is
// de-allocated the moment the response is flushed — a fire-and-forget
// POST issued after res.json() gets its callback frozen and never
// lands. Real (spaced-out) traffic hit this: the crew's 14 chats
// recorded 0 chat_message events until this was awaited. The internal
// 3s timeout bounds the worst case if the BOM service is degraded.
// Persist a chat exchange to the run's conversation (save/resume).
// Awaited by the caller before responding for the same CPU-throttle
// reason as logUsage. Always resolves — chat persistence must never
// break the reply.
export async function persistChatTurns(
  req: Request,
  runId: number,
  turns: Array<Record<string, unknown>>,
): Promise<void> {
  if (!runId || turns.length === 0) return;
  try {
    const url = `${config.flaskBomBaseUrl}/api/v1/bom-runs/${runId}/chat`;
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...buildUpstreamHeaders(req) },
      body: JSON.stringify({ turns }),
      signal: AbortSignal.timeout(3_000),
    });
    if (!res.ok) console.warn(`[chat-persist] run ${runId} → HTTP ${res.status}`);
  } catch (err) {
    console.warn(`[chat-persist] run ${runId} failed (non-fatal):`,
      err instanceof Error ? `${err.name}: ${err.message}` : err);
  }
}

export async function logUsage(
  req: Request,
  event: string,
  detail?: Record<string, unknown>,
  extra?: { client_id?: string; job_id?: string; run_id?: number },
): Promise<void> {
  try {
    const url = `${config.flaskBomBaseUrl}/api/v1/usage-events`;
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...buildUpstreamHeaders(req),
      },
      body: JSON.stringify({ event, detail, ...extra }),
      signal: AbortSignal.timeout(3_000),
    });
    if (!res.ok) console.warn(`[usage] ${event} → HTTP ${res.status}`);
  } catch (err) {
    // Telemetry must never break the user's flow — swallow everything.
    console.warn(`[usage] ${event} event failed (non-fatal):`,
      err instanceof Error ? `${err.name}: ${err.message}` : err);
  }
}
