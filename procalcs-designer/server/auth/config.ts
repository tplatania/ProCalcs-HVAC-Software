// Auth config — env vars pulled at container startup. Secrets come
// from GCP Secret Manager via Cloud Run --update-secrets flags; the
// non-secret ones come from --update-env-vars.
//
// Missing secrets are an intentional fatal error at startup rather
// than a runtime surprise — we'd rather fail fast than silently
// allow unsigned cookies or a wildcard domain allow-list.

function requireEnv(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(
      `[auth] Missing required env var ${name}. ` +
        `Set it via Cloud Run --update-secrets (for secrets) or ` +
        `--update-env-vars (for non-secrets) before deploying.`
    );
  }
  return v;
}

function optionalEnv(name: string, fallback: string): string {
  return process.env[name] ?? fallback;
}

// Auth is only required when it's actually being used. The adapter
// boots without auth when AUTH_ENABLED !== "true" (dev convenience) —
// in that mode requireAuth becomes a pass-through that sets a
// synthetic dev user so downstream code keeps working.
export const authEnabled = process.env.AUTH_ENABLED === "true";

export const authConfig = authEnabled
  ? {
      enabled: true as const,
      googleClientId:     requireEnv("GOOGLE_OAUTH_CLIENT_ID"),
      googleClientSecret: requireEnv("GOOGLE_OAUTH_CLIENT_SECRET"),
      redirectUri:        requireEnv("OAUTH_REDIRECT_URI"),
      sessionSigningKey:  requireEnv("SESSION_SIGNING_KEY"),
      allowedDomain:      optionalEnv("ALLOWED_DOMAIN", "procalcs.net"),
      cookieName:         optionalEnv("COOKIE_NAME", "procalcs_session"),
      sessionTtlSeconds:  Number(optionalEnv("SESSION_TTL_SECONDS", String(30 * 24 * 60 * 60))), // 30 days
    }
  : {
      enabled: false as const,
      googleClientId:     "",
      googleClientSecret: "",
      redirectUri:        "",
      sessionSigningKey:  "dev-only-do-not-ship",
      allowedDomain:      "procalcs.net",
      cookieName:         "procalcs_session",
      sessionTtlSeconds:  30 * 24 * 60 * 60,
    };

export type AuthConfig = typeof authConfig;

// Google endpoints — hardcoded since they're stable and public.
export const GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth";
export const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
export const GOOGLE_JWKS_URL  = "https://www.googleapis.com/oauth2/v3/certs";
