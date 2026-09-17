// Per-actor rate limiting for cost/abuse-prone endpoints (security
// hardening). The chat assistant costs real Anthropic money and uploads
// can be heavy; without a limit a compromised account or a runaway
// client (cf. the regenerate storm) could rack up cost or degrade the
// service.
//
// Dependency-free fixed-window limiter keyed by the authenticated email.
// NOTE: counts are per-instance (in-memory). At pilot scale that's a
// sufficient guard; a distributed limiter (Redis) is only worth it at
// higher scale. Ceilings are generous (well above real reviewer pace)
// and env-tunable, so legitimate use is never affected; every trip is
// logged as a security event.

import type { Request, Response, NextFunction } from "express";
import { logSecurityEvent } from "./auth/authorize.js";

interface Bucket { count: number; resetAt: number; }

export function rateLimit(opts: {
  name: string;
  windowMs: number;
  max: number;
}) {
  const buckets = new Map<string, Bucket>();

  // Opportunistic sweep so the map can't grow unbounded.
  function sweep(now: number) {
    if (buckets.size < 5000) return;
    for (const [k, b] of buckets) if (b.resetAt <= now) buckets.delete(k);
  }

  return (req: Request, res: Response, next: NextFunction) => {
    const key = (req as any).user?.email?.toLowerCase()
      ?? req.headers["x-forwarded-for"]?.toString()
      ?? req.socket?.remoteAddress
      ?? "anon";
    const now = Date.now();
    sweep(now);

    let b = buckets.get(key);
    if (!b || b.resetAt <= now) {
      b = { count: 0, resetAt: now + opts.windowMs };
      buckets.set(key, b);
    }
    b.count += 1;

    if (b.count > opts.max) {
      const retryAfter = Math.ceil((b.resetAt - now) / 1000);
      logSecurityEvent("rate_limited", req, {
        limiter: opts.name, max: opts.max,
        window_ms: opts.windowMs, count: b.count,
      });
      res.setHeader("Retry-After", String(retryAfter));
      res.status(429).json({
        error: "Too many requests — please slow down.",
        retry_after_seconds: retryAfter,
      });
      return;
    }
    next();
  };
}

const envInt = (name: string, dflt: number) => {
  const v = Number(process.env[name]);
  return Number.isFinite(v) && v > 0 ? v : dflt;
};

// Generous per-minute ceilings — a human reviewer sends a handful of
// chats/uploads a minute; these only bite on runaway/abusive traffic.
export const chatRateLimit = rateLimit({
  name: "chat",
  windowMs: 60_000,
  max: envInt("CHAT_RATE_MAX_PER_MIN", 30),
});

export const uploadRateLimit = rateLimit({
  name: "upload",
  windowMs: 60_000,
  max: envInt("UPLOAD_RATE_MAX_PER_MIN", 20),
});
