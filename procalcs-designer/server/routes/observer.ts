// /api/observer/* — Windows-agent observer bundle uploads.
//
// This is the endpoint the observer agent hits after Richard finishes a
// project in Wrightsoft. The agent uploads a .tar.gz bundle
// (`.rup` + optional `.xls` + `operations.jsonl` + `manifest.json`)
// per the handoff at
// ~/Procalcs/handoff-windows/HANDOFF_OBSERVER_AGENT.md §5.
//
// Status: STUB. Accepts the upload, validates the bearer token, echoes
// back a synthesized session_id + qa_url so the Windows session can
// smoke the wire before extraction is real. Persistence + tarball parse
// + extraction job come in the next iteration once the Windows agent
// produces its first bundle.
//
// Auth: bearer token (agent is a machine, not a browser session — no
// cookie). Wired outside the requireAuth middleware in
// server/index.ts, so this file owns its own token check.

import { Router, type Request, type Response } from "express";
import { randomUUID } from "node:crypto";

const router = Router();

// ─── Token store ──────────────────────────────────────────────────────
//
// One token per contractor profile. Populated from the environment at
// boot so we don't hardcode secrets. Format:
//   OBSERVER_TOKENS='reliable-heating-and-cooling:tok_abc123,acme:tok_def'
// Empty / missing env = observer disabled (returns 503 on all calls).

interface TokenEntry {
  profileId: string;
  token: string;
}

function loadTokens(): TokenEntry[] {
  const raw = process.env.OBSERVER_TOKENS || "";
  if (!raw) return [];
  return raw
    .split(",")
    .map(pair => pair.trim())
    .filter(Boolean)
    .map(pair => {
      const idx = pair.indexOf(":");
      if (idx < 0) return null;
      return {
        profileId: pair.slice(0, idx),
        token: pair.slice(idx + 1),
      };
    })
    .filter((t): t is TokenEntry => t !== null);
}

const tokens = loadTokens();

function verifyBearer(req: Request): TokenEntry | null {
  const auth = req.headers.authorization;
  if (!auth?.startsWith("Bearer ")) return null;
  const supplied = auth.slice("Bearer ".length).trim();
  if (!supplied) return null;
  const hit = tokens.find(t => t.token === supplied);
  return hit || null;
}

// ─── Config ───────────────────────────────────────────────────────────

// Max bundle size — 200 MB. Empirical estimate assumes a busy project
// with tens of thousands of COM-call events plus the .rup + .xls.
// Rejects larger bundles at request start rather than after streaming.
const MAX_BUNDLE_BYTES = 200 * 1024 * 1024;

// Base for the QA link handed back to the agent. Currently points at
// the SPA; will resolve to a valid page once /diagnostics/observer-qa
// lands. Reads from an env override so staging + prod resolve
// separately.
function qaUrlBase(): string {
  return (
    process.env.OBSERVER_QA_URL_BASE ||
    "https://procalcs-designer-desktop-staging-w7vvclyqya-ue.a.run.app"
  );
}

// ─── Routes ───────────────────────────────────────────────────────────

router.post("/upload", async (req: Request, res: Response) => {
  if (tokens.length === 0) {
    return res.status(503).json({
      success: false, data: null,
      error: "Observer endpoint not configured (OBSERVER_TOKENS env unset)",
    });
  }

  const entry = verifyBearer(req);
  if (!entry) {
    return res.status(401).json({
      success: false, data: null,
      error: "Invalid or missing Authorization: Bearer <token>",
    });
  }

  const contentType = req.headers["content-type"] || "";
  if (!contentType.startsWith("multipart/form-data")) {
    return res.status(400).json({
      success: false, data: null,
      error: "Expected multipart/form-data",
    });
  }

  const contentLength = Number(req.headers["content-length"] || 0);
  if (contentLength > MAX_BUNDLE_BYTES) {
    return res.status(413).json({
      success: false, data: null,
      error: `Bundle exceeds ${MAX_BUNDLE_BYTES} bytes (got ${contentLength})`,
    });
  }

  // ── Consume the body ────────────────────────────────────────────────
  // Stub behavior: we count bytes but don't persist yet. This is enough
  // for the Windows session to verify the wire end-to-end. Real
  // persistence (GCS + ObserverSession row + extraction-job trigger)
  // comes in the next iteration.
  let bytes = 0;
  await new Promise<void>((resolve, reject) => {
    req.on("data", (chunk: Buffer) => {
      bytes += chunk.length;
      if (bytes > MAX_BUNDLE_BYTES) {
        reject(new Error(`Bundle streamed past ${MAX_BUNDLE_BYTES} bytes`));
      }
    });
    req.on("end", () => resolve());
    req.on("error", reject);
  }).catch(err => {
    // eslint-disable-next-line no-console
    console.error("[observer] upload stream failed:", err);
    if (!res.headersSent) {
      res.status(413).json({
        success: false, data: null,
        error: String(err?.message ?? err),
      });
    }
  });

  if (res.headersSent) return;

  const sessionId = randomUUID();
  const jobId = randomUUID();

  // eslint-disable-next-line no-console
  console.log(
    `[observer] upload received: profile=${entry.profileId} bytes=${bytes} ` +
    `session=${sessionId} content-type='${contentType.slice(0, 60)}'`
  );

  return res.status(200).json({
    success: true,
    data: {
      session_id: sessionId,
      extraction_job_id: jobId,
      qa_url: `${qaUrlBase()}/diagnostics/observer-qa/${sessionId}`,
      bytes_received: bytes,
      // NOTE: this is a stub. Extraction hasn't run yet; the QA page
      // will show "waiting for extraction" until the job pipeline is
      // wired in a follow-up. Windows agent can safely surface this
      // URL to Richard — the page will exist and gracefully explain
      // the pending state.
      stub_notice:
        "Endpoint is currently a stub — upload accepted, extraction " +
        "pipeline not yet running. This will silently upgrade to real " +
        "extraction in the next iteration.",
    },
    error: null,
  });
});

// Health probe — the Windows agent can hit this at startup to confirm
// its token is valid before Richard commits to a real session.
router.get("/whoami", (req: Request, res: Response) => {
  const entry = verifyBearer(req);
  if (!entry) {
    return res.status(401).json({
      success: false, data: null,
      error: "Invalid or missing Authorization: Bearer <token>",
    });
  }
  res.json({
    success: true,
    data: { contractor_profile_id: entry.profileId },
    error: null,
  });
});

export default router;
