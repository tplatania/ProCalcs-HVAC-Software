// Signed-JWT cookie sign/verify using Node's built-in crypto. HS256
// with the SESSION_SIGNING_KEY from Secret Manager. No JWT library
// dependency for our own cookie — the format is simple enough that
// the direct implementation is ~40 lines and avoids pulling in a
// generic JWT library just for one algorithm.
//
// For Google's RS256 ID token verification we DO use the `jose`
// library (see routes.ts) — that involves JWKS fetching + rotation +
// RSA key material, which is not worth rewriting.

import { createHmac, timingSafeEqual } from "node:crypto";

export interface SessionPayload {
  email:   string;
  name:    string;
  picture: string;
  hd:      string;   // Google hosted-domain claim, e.g. "procalcs.net"
  iat:     number;   // issued at (epoch seconds)
  exp:     number;   // expires at (epoch seconds)
}

// ─── base64url helpers ──────────────────────────────────────────────

function base64UrlEncode(input: Buffer | string): string {
  const buf = typeof input === "string" ? Buffer.from(input, "utf8") : input;
  return buf
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function base64UrlDecode(input: string): Buffer {
  const pad = input.length % 4 === 0 ? "" : "=".repeat(4 - (input.length % 4));
  return Buffer.from(input.replace(/-/g, "+").replace(/_/g, "/") + pad, "base64");
}

// ─── sign / verify ──────────────────────────────────────────────────

const HEADER_B64 = base64UrlEncode(JSON.stringify({ alg: "HS256", typ: "JWT" }));

export function signToken(
  payload: Omit<SessionPayload, "iat" | "exp">,
  signingKey: string,
  ttlSeconds: number
): string {
  const now = Math.floor(Date.now() / 1000);
  const full: SessionPayload = { ...payload, iat: now, exp: now + ttlSeconds };
  const body   = base64UrlEncode(JSON.stringify(full));
  const signed = `${HEADER_B64}.${body}`;
  const sig    = base64UrlEncode(createHmac("sha256", signingKey).update(signed).digest());
  return `${signed}.${sig}`;
}

export class TokenError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "TokenError";
  }
}

export function verifyToken(token: string, signingKey: string): SessionPayload {
  const parts = token.split(".");
  if (parts.length !== 3) {
    throw new TokenError("malformed token");
  }
  const [headerB64, bodyB64, sigB64] = parts;

  // Signature check first — constant-time comparison.
  const expectedSig = createHmac("sha256", signingKey)
    .update(`${headerB64}.${bodyB64}`)
    .digest();
  const providedSig = base64UrlDecode(sigB64);
  if (
    expectedSig.length !== providedSig.length ||
    !timingSafeEqual(expectedSig, providedSig)
  ) {
    throw new TokenError("invalid signature");
  }

  // Header sanity.
  let header: { alg?: string; typ?: string };
  try {
    header = JSON.parse(base64UrlDecode(headerB64).toString("utf8"));
  } catch {
    throw new TokenError("invalid header");
  }
  if (header.alg !== "HS256") {
    throw new TokenError(`unexpected alg ${header.alg}`);
  }

  // Body parse + expiry.
  let payload: SessionPayload;
  try {
    payload = JSON.parse(base64UrlDecode(bodyB64).toString("utf8"));
  } catch {
    throw new TokenError("invalid payload");
  }
  const now = Math.floor(Date.now() / 1000);
  if (typeof payload.exp !== "number" || payload.exp < now) {
    throw new TokenError("expired");
  }

  return payload;
}
