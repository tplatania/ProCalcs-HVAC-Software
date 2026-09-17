// Role-based route authorization (security hardening).
//
// The app authenticates (requireAuth) but until now did NOT authorize:
// any logged-in account — including a contractor-crew `user` — could
// reach every endpoint. This adds a role gate.
//
// Roles rank user < admin < super_admin. The session token carries no
// role, so we resolve it by email against the seeded accounts at
// request time (an OAuth or unknown email → lowest privilege, `user`).
//
// SAFE-BY-DEFAULT: enforcement is OFF unless AUTHZ_ENFORCE=true. In the
// default (audit-only) mode a would-be denial is LOGGED but allowed, so
// merging this changes no behavior and can't lock anyone out. Watch the
// `security.authz` logs, confirm the role map, then flip AUTHZ_ENFORCE.

import type { Request, Response, NextFunction } from "express";
import { seedUsers } from "./seedUsers.js";

export type Role = "user" | "admin" | "super_admin";
const RANK: Record<Role, number> = { user: 0, admin: 1, super_admin: 2 };

const ENFORCE = process.env.AUTHZ_ENFORCE === "true";

export function roleForEmail(email: string | undefined): Role {
  if (!email) return "user";
  const u = seedUsers().find((s) => s.email === email.toLowerCase().trim());
  return (u?.role as Role) ?? "user"; // unknown / OAuth → least privilege
}

/** Structured security audit line — Cloud Run captures stdout. */
export function logSecurityEvent(
  event: string, req: Request, extra: Record<string, unknown> = {},
): void {
  const rec = {
    kind: "security",
    event,
    at: new Date().toISOString(),
    email: (req as any).user?.email ?? null,
    method: req.method,
    path: req.originalUrl?.split("?")[0] ?? req.path,
    ip: req.headers["x-forwarded-for"] ?? req.socket?.remoteAddress ?? null,
    enforce: ENFORCE,
    ...extra,
  };
  console.warn(`[security.${event}] ${JSON.stringify(rec)}`);
}

/** Require at least `minRole`. Audit-only unless AUTHZ_ENFORCE=true. */
export function requireRole(minRole: Role) {
  return (req: Request, res: Response, next: NextFunction) => {
    const email = (req as any).user?.email as string | undefined;
    const role = roleForEmail(email);
    if (RANK[role] >= RANK[minRole]) return next();

    logSecurityEvent("authz_denied", req, {
      required_role: minRole, actual_role: role,
      allowed_by_audit_mode: !ENFORCE,
    });
    if (!ENFORCE) return next(); // audit-only: log but allow
    res.status(403).json({ error: "Insufficient permissions." });
  };
}

/** Enforce `minRole` only on mutating methods (POST/PUT/PATCH/DELETE);
 *  GET/HEAD/OPTIONS pass through. For "reads open, writes restricted". */
export function requireRoleForWrites(minRole: Role) {
  const gate = requireRole(minRole);
  return (req: Request, res: Response, next: NextFunction) => {
    if (["GET", "HEAD", "OPTIONS"].includes(req.method)) return next();
    return gate(req, res, next);
  };
}
