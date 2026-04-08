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
import path from "node:path";
import { fileURLToPath } from "node:url";
import { existsSync } from "node:fs";
import { config } from "./config.js";

import clientProfilesRouter from "./routes/clientProfiles.js";
import dashboardRouter from "./routes/dashboard.js";
import bomRouter from "./routes/bom.js";
import pdfCleanupRouter from "./routes/pdfCleanup.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const app = express();

// JSON body parser — skipped for /api/pdf-cleanup so multipart passes through.
app.use((req, res, next) => {
  if (req.path.startsWith("/api/pdf-cleanup")) return next();
  express.json({ limit: "10mb" })(req, res, next);
});

// Health
app.get("/api/healthz", (_req, res) => {
  res.json({
    success: true,
    service: "procalcs-designer",
    status: "healthy",
    upstream: {
      bom: config.flaskBomBaseUrl,
      cleaner: config.flaskCleanerBaseUrl,
    },
  });
});

// API routes
app.use("/api/client-profiles", clientProfilesRouter);
app.use("/api/dashboard", dashboardRouter);
app.use("/api/bom", bomRouter);
app.use("/api/pdf-cleanup", pdfCleanupRouter);

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
