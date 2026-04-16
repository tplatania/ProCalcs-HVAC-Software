// Server runtime config.
// Flask backend URLs default to the live Cloud Run services so the container
// works with zero env vars in production. Overridable for local dev.

export const config = {
  port: Number(process.env.PORT ?? 8080),
  flaskBomBaseUrl:
    process.env.FLASK_BOM_BASE_URL ??
    "https://procalcs-hvac-bom-w7vvclyqya-ue.a.run.app",
  flaskCleanerBaseUrl:
    process.env.FLASK_CLEANER_BASE_URL ??
    "https://procalcs-hvac-cleaner-w7vvclyqya-ue.a.run.app",
  // Shared secret required by the BOM service (and any future shared
  // services). Sent as X-Procalcs-Service-Token on every proxied request.
  // Empty string = no auth (back-compat for deploys that haven't set it).
  serviceSharedSecret: process.env.SERVICE_SHARED_SECRET ?? "",
  // Identifies this BFF in BOM service logs (X-Client-Id header).
  clientId: process.env.SERVICE_CLIENT_ID ?? "designer-desktop",
  // Path to the built Vite bundle, relative to the server file location.
  // In production (node dist-server/index.js) this resolves to ../dist.
  // In dev (tsx server/index.ts) the Express server does NOT serve static
  // files — Vite dev server handles that on :5173 and proxies /api to us.
  staticDir: process.env.STATIC_DIR ?? "../dist",
} as const;
