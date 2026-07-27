// /api/bom-runs/* — proxy to procalcs-hvac-bom /api/v1/bom-runs/*.
//
// Shape mirrors skuCatalog.ts: forward the {success, data, error}
// envelope verbatim, attach the shared-secret + actor headers so the
// BOM service can attribute reviews. requireAuth wrapping is applied
// at index.ts mount time, so by the time a request reaches this
// router req.user is set when an OAuth session exists.

import { Router, type Request, type Response } from "express";
import { config } from "../config.js";
import { buildUpstreamHeaders } from "../upstreamHeaders.js";

const router = Router();

// Upstream timeout. Bounds the worst-case BFF hang when procalcs-bom
// is degraded — without this, slow Cloud Run cold starts can block
// the request for ~90s (Node fetch default) and Richard's UI just
// spins with no signal.
const UPSTREAM_TIMEOUT_MS = 30_000;

interface FlaskEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta?: Record<string, unknown>;
}

/** Classify a fetch-layer exception so the client gets an actionable
 *  message instead of a generic 502. */
function describeUpstreamError(err: unknown): string {
  if (err && typeof err === "object" && "name" in err) {
    const name = String((err as { name: unknown }).name);
    if (name === "AbortError" || name === "TimeoutError") {
      return `upstream timed out (${UPSTREAM_TIMEOUT_MS / 1000}s)`;
    }
    if (name === "TypeError") {
      // Node fetch wraps network failures (DNS, ECONNREFUSED, TLS) as TypeError.
      const msg = (err as { message?: string }).message ?? "network error";
      return `upstream unreachable — ${msg}`;
    }
  }
  const msg = err instanceof Error ? err.message : String(err);
  return msg;
}

async function callFlask<T>(
  req: Request,
  path: string,
  init?: RequestInit
): Promise<{ status: number; envelope: FlaskEnvelope<T> | null; raw: string }> {
  const url = `${config.flaskBomBaseUrl}/api/v1/bom-runs${path}`;
  const upstream = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...buildUpstreamHeaders(req),
      ...(init?.headers || {}),
    },
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
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

function send(
  res: Response,
  result: { status: number; envelope: FlaskEnvelope<unknown> | null; raw: string },
) {
  // Upstream content-type is preserved as JSON when the envelope parsed,
  // or echoed as-is when it didn't. This means upstream 4xx errors with
  // a non-JSON body (e.g., a load-balancer text response) flow through
  // with their actual status code, not a wrapped 502.
  res
    .status(result.status)
    .type("application/json")
    .send(result.envelope ? JSON.stringify(result.envelope) : result.raw);
}

/** Unified catch-block handler: logs server-side with operation context
 *  and returns a 502 with a useful client message. Per-route callers
 *  pass their operation label so Richard's UI sees e.g.
 *  "Review failed: upstream timed out (30s)" instead of generic
 *  "Review failed" with no signal as to cause. */
function sendUpstreamError(
  res: Response,
  err: unknown,
  operation: string,
): void {
  const detail = describeUpstreamError(err);
  console.error(`[bomRuns] ${operation} failed:`, detail, err);
  res.status(502).json({
    success: false,
    data: null,
    error: `${operation} failed: ${detail}`,
  });
}

// ─── List ──────────────────────────────────────────────────────────────────
router.get("/", async (req: Request, res: Response) => {
  try {
    const qs = new URLSearchParams();
    for (const k of ["client_id", "reviewer_status", "q", "limit", "offset"]) {
      const v = req.query[k];
      if (v !== undefined && v !== "") qs.set(k, String(v));
    }
    const path = qs.toString() ? `/?${qs.toString()}` : "/";
    send(res, await callFlask(req, path));
  } catch (err) {
    sendUpstreamError(res, err, "List bom-runs");
  }
});

// ─── Tag list (Phase 9) — must precede /:id so "tags" doesn't get
//     swallowed as a run id by Express's order-of-registration matching.
router.get("/tags", async (req: Request, res: Response) => {
  try {
    send(res, await callFlask(req, `/tags`));
  } catch (err) {
    sendUpstreamError(res, err, "List tags");
  }
});

// ─── Missing-SKU backlog (Day-2) — same precedence rule as /tags.
router.get("/missing-sku-backlog", async (req: Request, res: Response) => {
  try {
    const qs = new URLSearchParams();
    if (req.query.client_id) qs.set("client_id", String(req.query.client_id));
    const path = qs.toString() ? `/missing-sku-backlog?${qs.toString()}` : `/missing-sku-backlog`;
    send(res, await callFlask(req, path));
  } catch (err) {
    sendUpstreamError(res, err, "Backlog fetch");
  }
});

// ─── Per-run comparisons audit list (Day-2).
router.get("/:id/comparisons", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    send(res, await callFlask(req, `/${id}/comparisons`));
  } catch (err) {
    sendUpstreamError(res, err, `Comparisons fetch for ${req.params.id}`);
  }
});

// ─── Detail ────────────────────────────────────────────────────────────────
router.get("/:id", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    send(res, await callFlask(req, `/${id}`));
  } catch (err) {
    sendUpstreamError(res, err, `Get bom-run ${req.params.id}`);
  }
});

// ─── Review ────────────────────────────────────────────────────────────────
router.post("/:id/review", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    send(
      res,
      await callFlask(req, `/${id}/review`, {
        method: "POST",
        body: JSON.stringify(req.body ?? {}),
      }),
    );
  } catch (err) {
    sendUpstreamError(res, err, `Review ${req.params.id}`);
  }
});

// ─── Day-28 — delete a run (BREAD Delete) ────────────────────────────

router.delete("/:id", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    send(res, await callFlask(req, `/${id}`, { method: "DELETE" }));
  } catch (err) {
    sendUpstreamError(res, err, `Delete run ${req.params.id}`);
  }
});

// ─── Day-27 — persisted chat history (save/resume) ───────────────────

router.get("/:id/chat", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    send(res, await callFlask(req, `/${id}/chat`, { method: "GET" }));
  } catch (err) {
    sendUpstreamError(res, err, `Chat history ${req.params.id}`);
  }
});

// ─── Day-25 — run-scoped surgical patches (chat corrections) ──────────

router.post("/:id/patches", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    send(
      res,
      await callFlask(req, `/${id}/patches`, {
        method: "POST",
        body: JSON.stringify(req.body ?? {}),
      }),
    );
  } catch (err) {
    sendUpstreamError(res, err, `Patch run ${req.params.id}`);
  }
});

// ─── Compare with sample BOM (Phase 7) ────────────────────────────────
//
// Two intake shapes from the SPA:
//   - multipart/form-data with a 'file' field (Tom's .xls / .xlsx)
//   - application/json with {sample_lines: [...]} (pre-parsed)
//
// For multipart we have to stream the raw request body to the BOM
// service rather than re-serialize it — re-encoding would break
// boundaries and lose the file. JSON path falls through to the
// normal callFlask helper.
router.post("/:id/compare", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    const ct = (req.headers["content-type"] || "").toLowerCase();
    const isMultipart = ct.includes("multipart/form-data");

    if (isMultipart) {
      const upstreamUrl = `${config.flaskBomBaseUrl}/api/v1/bom-runs/${id}/compare`;
      const headers: Record<string, string> = { ...buildUpstreamHeaders(req) };
      // Preserve the boundary string from the original request.
      headers["Content-Type"] = Array.isArray(req.headers["content-type"])
        ? (req.headers["content-type"] as string[])[0]
        : (req.headers["content-type"] as string);
      const upstream = await fetch(upstreamUrl, {
        method: "POST",
        headers,
        body: req as any,
        // @ts-ignore — undici-specific, lets us stream the request body
        duplex: "half",
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      });
      const text = await upstream.text();
      res.status(upstream.status).type("application/json").send(text || "{}");
      return;
    }

    send(
      res,
      await callFlask(req, `/${id}/compare`, {
        method: "POST",
        body: JSON.stringify(req.body ?? {}),
      }),
    );
  } catch (err) {
    sendUpstreamError(res, err, `Compare ${req.params.id}`);
  }
});

// ─── Tag mutation + suite execution (Phase 9) ─────────────────────────

router.post("/:id/tags", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    send(
      res,
      await callFlask(req, `/${id}/tags`, {
        method: "POST",
        body: JSON.stringify(req.body ?? {}),
      }),
    );
  } catch (err) {
    sendUpstreamError(res, err, `Tag update for ${req.params.id}`);
  }
});

router.post("/regression-suites/:tag/run", async (req: Request, res: Response) => {
  try {
    const tag = encodeURIComponent(String(req.params.tag));
    send(
      res,
      await callFlask(req, `/regression-suites/${tag}/run`, {
        method: "POST",
        body: JSON.stringify(req.body ?? {}),
      }),
    );
  } catch (err) {
    sendUpstreamError(res, err, `Suite run for ${req.params.tag}`);
  }
});

// ─── Regenerate ────────────────────────────────────────────────────────────
router.post("/:id/regenerate", async (req: Request, res: Response) => {
  try {
    const id = encodeURIComponent(String(req.params.id));
    send(
      res,
      await callFlask(req, `/${id}/regenerate`, {
        method: "POST",
        body: JSON.stringify(req.body ?? {}),
      }),
    );
  } catch (err) {
    sendUpstreamError(res, err, `Regenerate ${req.params.id}`);
  }
});

export default router;
