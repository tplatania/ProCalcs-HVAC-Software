// Unit tests for server/auth/token.ts — run with:
//   npx tsx --test server/auth/token.test.ts
// or via the npm test:auth script.

import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { signToken, verifyToken, TokenError } from "./token.js";

const KEY = "test-signing-key-do-not-use-in-prod";

describe("token — sign/verify", () => {
  it("round-trips a payload", () => {
    const token = signToken(
      { email: "a@procalcs.net", name: "A User", picture: "", hd: "procalcs.net" },
      KEY,
      3600
    );
    const payload = verifyToken(token, KEY);
    assert.equal(payload.email, "a@procalcs.net");
    assert.equal(payload.hd, "procalcs.net");
    assert.ok(payload.iat <= Math.floor(Date.now() / 1000));
    assert.ok(payload.exp > payload.iat);
  });

  it("rejects a token signed with a different key", () => {
    const token = signToken(
      { email: "a@procalcs.net", name: "A", picture: "", hd: "procalcs.net" },
      KEY,
      3600
    );
    assert.throws(() => verifyToken(token, "wrong-key"), (err) => {
      assert.ok(err instanceof TokenError);
      assert.match((err as Error).message, /invalid signature/);
      return true;
    });
  });

  it("rejects a tampered payload", () => {
    const token = signToken(
      { email: "a@procalcs.net", name: "A", picture: "", hd: "procalcs.net" },
      KEY,
      3600
    );
    // Flip a single character in the body section.
    const [h, b, s] = token.split(".");
    const tampered =
      b[0] === "a" ? `${h}.b${b.slice(1)}.${s}` : `${h}.a${b.slice(1)}.${s}`;
    assert.throws(() => verifyToken(tampered, KEY), TokenError);
  });

  it("rejects a malformed token", () => {
    assert.throws(() => verifyToken("not.a.valid.token", KEY), TokenError);
    assert.throws(() => verifyToken("onlytwoparts.here", KEY), TokenError);
    assert.throws(() => verifyToken("", KEY), TokenError);
  });

  it("rejects an expired token", () => {
    // TTL of -1 second → already expired on creation.
    const token = signToken(
      { email: "a@procalcs.net", name: "A", picture: "", hd: "procalcs.net" },
      KEY,
      -1
    );
    assert.throws(() => verifyToken(token, KEY), (err) => {
      assert.ok(err instanceof TokenError);
      assert.match((err as Error).message, /expired/);
      return true;
    });
  });
});
