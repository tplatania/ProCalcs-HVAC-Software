// Express entry point for procalcs-designer.
//
// Responsibilities:
//   1. Mount /api/client-profiles, /api/dashboard, /api/bom, /api/pdf-cleanup
//   2. Serve the built Vite SPA bundle from ../dist as static files
//   3. Fall through any non-/api GET to index.html for wouter's client routing
//   4. Expose /api/healthz for Cloud Run health checks
//
// In dev, skip the static serve — Vite's own dev server runs on :5173 and
// proxies /api to this Express on :8081 (see vite.config.ts).

import express from "express";
import cookieParser from "cookie-parser";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { config } from "./config.js";

import clientProfilesRouter from "./routes/clientProfiles.js";
import dashboardRouter from "./routes/dashboard.js";
import bomRouter from "./routes/bom.js";
import bomRunsRouter from "./routes/bomRuns.js";
import skuCatalogRouter from "./routes/skuCatalog.js";
import contractorOverridesRouter from "./routes/contractorOverrides.js";
import rupDuctTotalsRouter from "./routes/rupDuctTotals.js";
import pdfCleanupRouter from "./routes/pdfCleanup.js";
import billingRouter from "./routes/billing.js";
import observerRouter from "./routes/observer.js";
import catalogRouter from "./routes/catalog.js";
import bomChatRouter from "./routes/bomChat.js";
import authRouter from "./auth/routes.js";
import { requireAuth } from "./auth/middleware.js";
import { authConfig } from "./auth/config.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();

// Cookie parser — needed by the auth middleware and /api/auth/me.
// Must run before both so the parsed cookies are on req.cookies.
app.use(cookieParser());

// JSON body parser — skipped for /api/pdf-cleanup, /api/bom/parse-rup,
// and /api/billing/webhook so multipart / raw-binary uploads pass through
// to the backend untouched. Stripe signs the EXACT bytes it sends; if
// express.json() parses + re-serializes them, signature verification
// would fail upstream.
app.use((req, res, next) => {
  if (req.path.startsWith("/api/pdf-cleanup")) return next();
  if (req.path === "/api/bom/parse-rup") return next();
  if (req.path === "/api/bom/rup-inspect") return next();
  // Wrightsoft BOM upload — multipart (file + client_id + job_id fields).
  // Must skip JSON parsing so the form fields actually reach Flask.
  if (req.path === "/api/bom/from-wrightsoft") return next();
  // Wrightsoft BOM v2 (bundle path) — multipart (file + equipment_bundle
  // + client_id + job_id). Same bypass reason as /from-wrightsoft.
  if (req.path === "/api/bom/from-wrightsoft-bundle") return next();
  // Observer bundle uploads — multipart .tar.gz per HANDOFF_OBSERVER_AGENT.md.
  // We consume the raw stream ourselves; JSON parsing would break it.
  if (req.path === "/api/observer/upload") return next();
  // Sample-BOM XLS upload (Phase 7) — must skip JSON parsing so the
  // multipart body streams through to the BOM service unchanged.
  if (req.path.startsWith("/api/bom-runs/") && req.path.endsWith("/compare")) {
    return next();
  }
  if (req.path === "/api/billing/webhook") return next();
  express.json({ limit: "10mb" })(req, res, next);
});

// Health — unauthenticated so platform probes and Tom's shell scripts
// can poll without a cookie.
app.get("/api/healthz", (_req, res) => {
  res.json({
    success: true,
    service: "procalcs-designer",
    status: "healthy",
    authEnabled: authConfig.enabled,
    upstream: {
      bom: config.flaskBomBaseUrl,
      cleaner: config.flaskCleanerBaseUrl,
    },
  });
});

// Auth routes — login / callback / logout / me. Unauthenticated by
// design (the whole point is to establish auth).
app.use("/api/auth", authRouter);

// Stripe webhook — must be unauthenticated (Stripe is the caller, not
// a logged-in user). Mounted before requireAuth-protected routes so
// it doesn't fall through. Signature is verified upstream in
// procalcs-bom against STRIPE_WEBHOOK_SECRET.
app.use("/api/billing/webhook", billingRouter);

// Observer agent — machine-to-machine, bearer token auth (owned inside
// the router). Mounted before requireAuth-protected routes so the
// agent doesn't need a browser cookie.
app.use("/api/observer", observerRouter);

// Protected API routes — every request past this line has req.user
// set by requireAuth, or was 401'd before reaching the router.
app.use("/api/client-profiles", requireAuth, clientProfilesRouter);
app.use("/api/dashboard", requireAuth, dashboardRouter);
app.use("/api/bom", requireAuth, bomRouter);
app.use("/api/bom-runs", requireAuth, bomRunsRouter);
app.use("/api/sku-catalog", requireAuth, skuCatalogRouter);
app.use("/api/contractor-overrides", requireAuth, contractorOverridesRouter);
app.use("/api/rup-duct-totals", requireAuth, rupDuctTotalsRouter);
app.use("/api/catalog", requireAuth, catalogRouter);
app.use("/api/bom-chat", requireAuth, bomChatRouter);
app.use("/api/pdf-cleanup", requireAuth, pdfCleanupRouter);
app.use("/api/billing", requireAuth, billingRouter);

// Unmatched /api/* → JSON 404 (do NOT fall through to the SPA shell)
app.use("/api", (_req, res) => {
  res.status(404).json({ error: "API route not found" });
});

// Static SPA bundle (skipped in dev when STATIC_DIR doesn't exist)
const staticDirAbs = path.resolve(__dirname, config.staticDir);
if (existsSync(staticDirAbs)) {
  app.use(express.static(staticDirAbs));
  // SPA fallback — any non-/api GET returns index.html so wouter can route
  // client-side. Express 5 no longer accepts "*" strings; regex is required.
  app.get(/^(?!\/api(?:\/|$)).*$/, (_req, res) => {
    res.sendFile(path.join(staticDirAbs, "index.html"));
  });
} else {
  // eslint-disable-next-line no-console
  console.warn(
    `[procalcs-designer] Static dir ${staticDirAbs} not found — running API-only (dev mode).`
  );
}

app.listen(config.port, () => {
  // eslint-disable-next-line no-console
  console.log(
    `[procalcs-designer] listening on :${config.port} → bom=${config.flaskBomBaseUrl} cleaner=${config.flaskCleanerBaseUrl}`
  );
});
