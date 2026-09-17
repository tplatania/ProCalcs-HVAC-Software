// Tests for role-based authorization. Run:
//   npx tsx --test server/auth/authorize.test.ts

import { describe, it, before, beforeEach } from "node:test";
import assert from "node:assert/strict";
import bcrypt from "bcryptjs";

// Seed a known role map BEFORE importing the modules that read it.
process.env.SEED_USERS_JSON = JSON.stringify([
  { email: "boss@procalcs.net", name: "Boss", role: "super_admin", password_hash: bcrypt.hashSync("x", 4) },
  { email: "admin@procalcs.net", name: "Admin", role: "admin", password_hash: bcrypt.hashSync("x", 4) },
  { email: "crew@reliableheating.team", name: "Crew", role: "user", password_hash: bcrypt.hashSync("x", 4) },
]);

let roleForEmail: any, requireRole: any, requireRoleForWrites: any;
before(async () => {
  const mod = await import("./authorize.ts");
  roleForEmail = mod.roleForEmail;
  requireRole = mod.requireRole;
  requireRoleForWrites = mod.requireRoleForWrites;
});

function fakeReqRes(email: string | undefined, method = "POST") {
  let statusCode = 0; let body: any = null; let nexted = false;
  const req: any = { user: email ? { email } : undefined, method,
                     originalUrl: "/api/x", path: "/api/x", headers: {}, socket: {} };
  const res: any = {
    status(c: number) { statusCode = c; return this; },
    json(b: any) { body = b; return this; },
  };
  const next = () => { nexted = true; };
  return { req, res, next, get: () => ({ statusCode, body, nexted }) };
}

describe("roleForEmail", () => {
  it("resolves seeded roles", () => {
    assert.equal(roleForEmail("boss@procalcs.net"), "super_admin");
    assert.equal(roleForEmail("admin@procalcs.net"), "admin");
    assert.equal(roleForEmail("crew@reliableheating.team"), "user");
  });
  it("unknown / OAuth email → least privilege", () => {
    assert.equal(roleForEmail("stranger@procalcs.net"), "user");
    assert.equal(roleForEmail(undefined), "user");
  });
  it("is case-insensitive", () => {
    assert.equal(roleForEmail("BOSS@Procalcs.net"), "super_admin");
  });
});

describe("requireRole (audit-only default — AUTHZ_ENFORCE unset)", () => {
  it("allows a sufficient role", () => {
    const t = fakeReqRes("admin@procalcs.net");
    requireRole("admin")(t.req, t.res, t.next);
    assert.equal(t.get().nexted, true);
  });
  it("audit-only: insufficient role is LOGGED but allowed", () => {
    const t = fakeReqRes("crew@reliableheating.team");
    requireRole("admin")(t.req, t.res, t.next);
    assert.equal(t.get().nexted, true);       // allowed through
    assert.equal(t.get().statusCode, 0);      // not 403
  });
});

describe("requireRoleForWrites", () => {
  it("lets GET through for any role", () => {
    const t = fakeReqRes("crew@reliableheating.team", "GET");
    requireRoleForWrites("admin")(t.req, t.res, t.next);
    assert.equal(t.get().nexted, true);
  });
});
