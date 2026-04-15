// Four Google OAuth endpoints mounted under /api/auth:
//   GET  /login     → 302 to Google consent
//   GET  /callback  → exchange code, verify ID token, set cookie, 302 to /
//   POST /logout    → clear cookie, 204
//   GET  /me        → {email, name, picture} or 401
//
// The flow is stateless: no server-side session store. All user data
// lives in the signed cookie (see token.ts). The `state` parameter in
// the OAuth redirect is itself a short-lived signed token, which
// protects against CSRF on the callback without needing a separate
// session to hold it.

import { Router, type Request, type Response } from "express";
import { createRemoteJWKSet, jwtVerify } from "jose";
import { randomBytes, createHmac, timingSafeEqual } from "node:crypto";
import {
  authConfig,
  isEmailAllowed,
  GOOGLE_AUTH_URL,
  GOOGLE_TOKEN_URL,
  GOOGLE_JWKS_URL,
} from "./config.js";
import { signToken, verifyToken, TokenError } from "./token.js";

const router = Router();

// Lazy-built JWKS set — `jose` handles caching + rotation internally.
const googleJwks = createRemoteJWKSet(new URL(GOOGLE_JWKS_URL));

// ─── helpers ────────────────────────────────────────────────────────

// Short-lived signed `state` token carrying the post-login redirect
// target. Signed with the same SESSION_SIGNING_KEY so we don't need
// a separate secret. 10 minute TTL — OAuth round-trips are seconds.
const STATE_TTL_SECONDS = 10 * 60;

function signState(target: string): string {
  const body = Buffer.from(
    JSON.stringify({ t: target, exp: Math.floor(Date.now() / 1000) + STATE_TTL_SECONDS })
  ).toString("base64url");
  const sig = createHmac("sha256", authConfig.sessionSigningKey)
    .update(body)
    .digest("base64url");
  return `${body}.${sig}`;
}

function verifyState(state: string): string | null {
  const parts = state.split(".");
  if (parts.length !== 2) return null;
  const [body, sig] = parts;
  const expected = createHmac("sha256", authConfig.sessionSigningKey)
    .update(body)
    .digest();
  const provided = Buffer.from(sig, "base64url");
  if (
    expected.length !== provided.length ||
    !timingSafeEqual(expected, provided)
  ) {
    return null;
  }
  try {
    const parsed = JSON.parse(Buffer.from(body, "base64url").toString("utf8")) as {
      t: string;
      exp: number;
    };
    if (parsed.exp < Math.floor(Date.now() / 1000)) return null;
    return parsed.t;
  } catch {
    return null;
  }
}

function setSessionCookie(res: Response, token: string): void {
  res.cookie(authConfig.cookieName, token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: authConfig.sessionTtlSeconds * 1000,
    path: "/",
  });
}

function clearSessionCookie(res: Response): void {
  res.clearCookie(authConfig.cookieName, { path: "/" });
}

// ─── routes ─────────────────────────────────────────────────────────

// GET /api/auth/login?return_to=/some-path
//   Redirects to Google's consent screen. The `return_to` is encoded
//   into the `state` parameter so we can bounce the user back to the
//   page they were trying to reach.
router.get("/login", (req: Request, res: Response) => {
  if (!authConfig.enabled) {
    return res.status(503).json({ error: "Auth not configured on this deploy" });
  }
  const returnTo = typeof req.query.return_to === "string" ? req.query.return_to : "/";
  const state = signState(returnTo);
  const nonce = randomBytes(16).toString("base64url");

  // Note: we deliberately don't pass `hd=<domain>` here. The `hd`
  // hint only narrows the account picker for Google Workspace users;
  // for non-Workspace domains it's silently ignored and showing it
  // would imply an expectation we don't actually enforce that way.
  const params = new URLSearchParams({
    client_id: authConfig.googleClientId,
    redirect_uri: authConfig.redirectUri,
    response_type: "code",
    scope: "openid email profile",
    access_type: "online",
    prompt: "select_account",
    state,
    nonce,
  });
  res.redirect(`${GOOGLE_AUTH_URL}?${params.toString()}`);
});

// GET /api/auth/callback
//   Google redirects here with ?code=...&state=...
//   Exchange the code for tokens, verify the ID token signature + hd
//   claim, set the session cookie, and bounce the user to the page
//   they were originally trying to reach.
router.get("/callback", async (req: Request, res: Response) => {
  if (!authConfig.enabled) {
    return res.status(503).json({ error: "Auth not configured on this deploy" });
  }

  const code = typeof req.query.code === "string" ? req.query.code : "";
  const state = typeof req.query.state === "string" ? req.query.state : "";
  if (!code) {
    return res.status(400).json({ error: "Missing authorization code" });
  }

  const returnTo = verifyState(state);
  if (returnTo === null) {
    return res.status(400).json({ error: "Invalid or expired state parameter" });
  }

  // Exchange the authorization code for tokens.
  let tokenResponse: {
    id_token?: string;
    access_token?: string;
    error?: string;
    error_description?: string;
  };
  try {
    const res2 = await fetch(GOOGLE_TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: authConfig.googleClientId,
        client_secret: authConfig.googleClientSecret,
        redirect_uri: authConfig.redirectUri,
        grant_type: "authorization_code",
      }),
    });
    tokenResponse = (await res2.json()) as typeof tokenResponse;
    if (!res2.ok) {
      return res.status(502).json({
        error: "Google token exchange failed",
        detail: tokenResponse.error_description || tokenResponse.error,
      });
    }
  } catch (err: any) {
    return res
      .status(502)
      .json({ error: "Google token exchange network error", detail: err?.message });
  }

  const idToken = tokenResponse.id_token;
  if (!idToken) {
    return res.status(502).json({ error: "Google did not return an id_token" });
  }

  // Verify the ID token's RS256 signature against Google's JWKS.
  let claims: {
    email?: string;
    name?: string;
    picture?: string;
    hd?: string;
    email_verified?: boolean;
  };
  try {
    const { payload } = await jwtVerify(idToken, googleJwks, {
      issuer: ["https://accounts.google.com", "accounts.google.com"],
      audience: authConfig.googleClientId,
    });
    claims = payload as typeof claims;
  } catch (err: any) {
    return res.status(401).json({ error: "Invalid ID token", detail: err?.message });
  }

  // Domain restriction. Our OAuth consent screen is External (the
  // org isn't on Google Workspace), so the Workspace-only `hd` claim
  // is absent for most users and can't be the gate. Instead we
  // require a verified email ending in @<allowedDomain>. Google sets
  // email_verified=true only after the user has proven ownership of
  // the mailbox, which is the real gate.
  if (!claims.email) {
    return res.status(502).json({ error: "Google claims missing email" });
  }
  if (!isEmailAllowed(claims.email, claims.email_verified)) {
    return res.status(403).json({
      error: `Access restricted to verified @${authConfig.allowedDomain} accounts`,
      detail: `got email=${claims.email}, verified=${claims.email_verified ?? false}`,
    });
  }

  const sessionToken = signToken(
    {
      email:   claims.email,
      name:    claims.name ?? claims.email,
      picture: claims.picture ?? "",
      hd:      claims.hd ?? "",  // Empty for non-Workspace accounts; retained for observability.
    },
    authConfig.sessionSigningKey,
    authConfig.sessionTtlSeconds
  );
  setSessionCookie(res, sessionToken);

  // Only allow bouncing to same-origin paths — otherwise we could be
  // used as an open redirect.
  const safeReturn = returnTo.startsWith("/") ? returnTo : "/";
  res.redirect(safeReturn);
});

// POST /api/auth/logout
router.post("/logout", (_req: Request, res: Response) => {
  clearSessionCookie(res);
  res.status(204).send();
});

// GET /api/auth/me
router.get("/me", (req: Request, res: Response) => {
  if (!authConfig.enabled) {
    // Dev mode — return a synthetic user so the SPA keeps working.
    return res.json({
      email: "dev@procalcs.net",
      name: "Dev User",
      picture: "",
      hd: "procalcs.net",
      authEnabled: false,
    });
  }
  const cookieName = authConfig.cookieName;
  const raw = (req as any).cookies?.[cookieName] as string | undefined;
  if (!raw) {
    return res.status(401).json({ error: "Not authenticated" });
  }
  try {
    const payload = verifyToken(raw, authConfig.sessionSigningKey);
    return res.json({
      email:   payload.email,
      name:    payload.name,
      picture: payload.picture,
      hd:      payload.hd,
      authEnabled: true,
    });
  } catch (err) {
    if (err instanceof TokenError) {
      clearSessionCookie(res);
      return res.status(401).json({ error: "Session invalid", detail: err.message });
    }
    return res.status(500).json({ error: "Unexpected auth error" });
  }
});

export default router;
