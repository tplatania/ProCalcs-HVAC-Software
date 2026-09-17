// Tests for the rate limiter. Run: npx tsx --test server/rateLimit.test.ts
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { rateLimit } from "./rateLimit.ts";

function call(mw: any, email: string) {
  let statusCode = 0; let nexted = false;
  const req: any = { user: { email }, method: "POST", headers: {}, socket: {},
                     originalUrl: "/x", path: "/x" };
  const res: any = { setHeader() {}, status(c: number) { statusCode = c; return this; },
                     json() { return this; } };
  mw(req, res, () => { nexted = true; });
  return { statusCode, nexted };
}

describe("rateLimit", () => {
  it("allows up to max, then 429s", () => {
    const mw = rateLimit({ name: "t", windowMs: 60_000, max: 3 });
    assert.equal(call(mw, "a@x.com").nexted, true);   // 1
    assert.equal(call(mw, "a@x.com").nexted, true);   // 2
    assert.equal(call(mw, "a@x.com").nexted, true);   // 3
    const over = call(mw, "a@x.com");                 // 4 → over
    assert.equal(over.nexted, false);
    assert.equal(over.statusCode, 429);
  });

  it("limits are per-actor (separate emails don't share a bucket)", () => {
    const mw = rateLimit({ name: "t", windowMs: 60_000, max: 1 });
    assert.equal(call(mw, "a@x.com").nexted, true);
    assert.equal(call(mw, "b@x.com").nexted, true);   // different user, fresh
    assert.equal(call(mw, "a@x.com").statusCode, 429); // a is now over
  });

  it("window resets allow traffic again", () => {
    const mw = rateLimit({ name: "t", windowMs: 1, max: 1 });
    assert.equal(call(mw, "a@x.com").nexted, true);
    // window is 1ms; after a tick the bucket resets
    const done = new Promise<void>((resolve) => setTimeout(() => {
      assert.equal(call(mw, "a@x.com").nexted, true);
      resolve();
    }, 5));
    return done;
  });
});
