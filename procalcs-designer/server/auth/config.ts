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

// Day-27 — seeded password accounts can carry non-procalcs identities
// (Richard's team). ALLOWED_DOMAINS is a comma-separated list; the
// legacy singular ALLOWED_DOMAIN still works as a fallback.
function allowedDomainsFromEnv(): string[] {
  const multi = process.env.ALLOWED_DOMAINS;
  const single = process.env.ALLOWED_DOMAIN;
  const raw = multi ?? single ?? "procalcs.net";
  return raw.split(",").map((d) => d.trim().toLowerCase()).filter(Boolean);
}

// When seeded password auth is active, Google OAuth becomes optional —
// a staging deploy can be password-only. requireEnv still guards the
// case where NEITHER method is configured.
const hasSeeds = !!process.env.SEED_USERS_JSON;
const googleEnv = (name: string): string =>
  hasSeeds ? optionalEnv(name, "") : requireEnv(name);

export const authConfig = authEnabled
  ? {
      enabled: true as const,
      googleClientId:     googleEnv("GOOGLE_OAUTH_CLIENT_ID"),
      googleClientSecret: googleEnv("GOOGLE_OAUTH_CLIENT_SECRET"),
      redirectUri:        googleEnv("OAUTH_REDIRECT_URI"),
      sessionSigningKey:  requireEnv("SESSION_SIGNING_KEY"),
      allowedDomains:     allowedDomainsFromEnv(),
      cookieName:         optionalEnv("COOKIE_NAME", "procalcs_session"),
      sessionTtlSeconds:  Number(optionalEnv("SESSION_TTL_SECONDS", String(30 * 24 * 60 * 60))), // 30 days
    }
  : {
      enabled: false as const,
      googleClientId:     "",
      googleClientSecret: "",
      redirectUri:        "",
      sessionSigningKey:  "dev-only-do-not-ship",
      allowedDomains:     ["procalcs.net"],
      cookieName:         "procalcs_session",
      sessionTtlSeconds:  30 * 24 * 60 * 60,
    };

export const googleOauthConfigured =
  !!(authConfig.googleClientId && authConfig.googleClientSecret && authConfig.redirectUri);

export type AuthConfig = typeof authConfig;

// Google endpoints — hardcoded since they're stable and public.
export const GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth";
export const GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token";
export const GOOGLE_JWKS_URL  = "https://www.googleapis.com/oauth2/v3/certs";

// Domain gate used by BOTH the callback (on fresh login) and the
// middleware (on every request). For Google Workspace orgs the `hd`
// claim would be the strongest check, but we're on an External
// consent screen with a non-Workspace domain — so we rely on the
// verified email suffix. Google requires ownership-proof before
// flipping `email_verified` to true, so this is equivalent security
// for our use case.
export function isEmailAllowed(email: string | undefined, emailVerified: boolean | undefined): boolean {
  if (!email || !emailVerified) return false;
  const lower = email.toLowerCase();
  return authConfig.allowedDomains.some((d) => lower.endsWith("@" + d));
}
