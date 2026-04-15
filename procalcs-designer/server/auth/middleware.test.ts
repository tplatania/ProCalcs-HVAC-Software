// Unit tests for server/auth/middleware.ts — run with:
//   npx tsx --test server/auth/middleware.test.ts
//
// These tests enable AUTH via env vars before importing the module,
// so the middleware runs in its real path (not the dev pass-through).

import { describe, it, before } from "node:test";
import assert from "node:assert/strict";

// Seed auth config BEFORE importing middleware / token — the module
// captures authConfig at import time.
process.env.AUTH_ENABLED = "true";
process.env.GOOGLE_OAUTH_CLIENT_ID     = "test-client-id";
process.env.GOOGLE_OAUTH_CLIENT_SECRET = "test-client-secret";
process.env.OAUTH_REDIRECT_URI         = "http://localhost/api/auth/callback";
process.env.SESSION_SIGNING_KEY        = "test-signing-key";
process.env.ALLOWED_DOMAIN             = "procalcs.net";

const { requireAuth } = await import("./middleware.js");
const { signToken }   = await import("./token.js");

// Minimal mocks for Express req/res shapes that the middleware uses.
function makeReq(cookies: Record<string, string> = {}) {
  return { cookies } as any;
}

function makeRes() {
  const res: any = {
    statusCode: 200,
    headers: {} as Record<string, string>,
    body:    undefined as unknown,
    cleared: false,
    status(code: number) {
      this.statusCode = code;
      return this;
    },
    json(payload: unknown) {
      this.body = payload;
      return this;
    },
    clearCookie(_name: string, _opts?: unknown) {
      this.cleared = true;
      return this;
    },
  };
  return res;
}

describe("middleware — requireAuth", () => {
  it("returns 401 when no cookie is present", () => {
    const req = makeReq({});
    const res = makeRes();
    let nextCalled = false;
    requireAuth(req, res, () => { nextCalled = true; });
    assert.equal(res.statusCode, 401);
    assert.equal(nextCalled, false);
  });

  it("passes a valid procalcs.net cookie through and sets req.user", () => {
    const token = signToken(
      { email: "g@procalcs.net", name: "Gerald", picture: "", hd: "procalcs.net" },
      "test-signing-key",
      3600
    );
    const req = makeReq({ procalcs_session: token });
    const res = makeRes();
    let nextCalled = false;
    requireAuth(req, res, () => { nextCalled = true; });
    assert.equal(nextCalled, true);
    assert.equal(req.user?.email, "g@procalcs.net");
    assert.equal(req.user?.hd, "procalcs.net");
  });

  it("returns 403 for a valid token with the wrong domain", () => {
    const token = signToken(
      { email: "x@gmail.com", name: "Outsider", picture: "", hd: "gmail.com" },
      "test-signing-key",
      3600
    );
    const req = makeReq({ procalcs_session: token });
    const res = makeRes();
    let nextCalled = false;
    requireAuth(req, res, () => { nextCalled = true; });
    assert.equal(res.statusCode, 403);
    assert.equal(nextCalled, false);
  });

  it("clears the cookie and returns 401 for a tampered token", () => {
    const token = signToken(
      { email: "g@procalcs.net", name: "Gerald", picture: "", hd: "procalcs.net" },
      "test-signing-key",
      3600
    );
    const tampered = token.slice(0, -4) + "AAAA";
    const req = makeReq({ procalcs_session: tampered });
    const res = makeRes();
    let nextCalled = false;
    requireAuth(req, res, () => { nextCalled = true; });
    assert.equal(res.statusCode, 401);
    assert.equal(res.cleared, true);
    assert.equal(nextCalled, false);
  });

  it("returns 401 for an expired token", () => {
    const token = signToken(
      { email: "g@procalcs.net", name: "Gerald", picture: "", hd: "procalcs.net" },
      "test-signing-key",
      -1
    );
    const req = makeReq({ procalcs_session: token });
    const res = makeRes();
    let nextCalled = false;
    requireAuth(req, res, () => { nextCalled = true; });
    assert.equal(res.statusCode, 401);
    assert.equal(nextCalled, false);
  });
});
