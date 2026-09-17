// requireAuth middleware — protects /api/* routes downstream of it.
//
// When AUTH_ENABLED !== "true" this is a pass-through that stubs a
// dev user onto the request. That mode is only for local dev and is
// never set on the live Cloud Run service.

import type { Request, Response, NextFunction } from "express";
import { authConfig } from "./config.js";
import { verifyToken, TokenError, type SessionPayload } from "./token.js";

declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace Express {
    interface Request {
      user?: SessionPayload;
    }
  }
}

export function requireAuth(req: Request, res: Response, next: NextFunction): void {
  if (!authConfig.enabled) {
    req.user = {
      email: "dev@procalcs.net",
      name: "Dev User",
      picture: "",
      hd: "procalcs.net",
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + 3600,
    };
    return next();
  }

  const raw = (req as any).cookies?.[authConfig.cookieName] as string | undefined;
  if (!raw) {
    res.status(401).json({ error: "Not authenticated" });
    return;
  }

  try {
    const payload = verifyToken(raw, authConfig.sessionSigningKey);
    // Re-check the domain on every request. The email was already
    // verified-by-Google at callback time; here we just confirm the
    // cookie's email still matches the configured allowed domain (in
    // case ALLOWED_DOMAIN changed server-side, old cookies get
    // invalidated on the next request).
    const lower = payload.email.toLowerCase();
    if (!authConfig.allowedDomains.some((d) => lower.endsWith("@" + d))) {
      res.status(403).json({
        error: `Restricted to: ${authConfig.allowedDomains.map((d) => "@" + d).join(", ")}`,
      });
      return;
    }
    req.user = payload;
    next();
  } catch (err) {
    if (err instanceof TokenError) {
      res.clearCookie(authConfig.cookieName, { path: "/" });
      res.status(401).json({ error: "Session invalid", detail: err.message });
      return;
    }
    res.status(500).json({ error: "Unexpected auth error" });
  }
}
