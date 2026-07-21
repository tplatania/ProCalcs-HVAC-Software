// Node test-runner tests for Day-27 seeded password auth.
// Run via: npm run test:auth

import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import bcrypt from "bcryptjs";
import { seedUsers, verifyCredentials, passwordAuthEnabled, _resetSeedCache } from "./seedUsers.js";

const HASH = bcrypt.hashSync("correct horse", 10);

function seed(users: unknown): void {
  process.env.SEED_USERS_JSON = JSON.stringify(users);
  _resetSeedCache();
}

beforeEach(() => {
  delete process.env.SEED_USERS_JSON;
  _resetSeedCache();
});

test("no seeds → password auth disabled", () => {
  assert.equal(passwordAuthEnabled(), false);
  assert.deepEqual(seedUsers(), []);
});

test("malformed JSON disables password auth instead of crashing", () => {
  process.env.SEED_USERS_JSON = "{not json";
  _resetSeedCache();
  assert.equal(passwordAuthEnabled(), false);
});

test("valid credentials verify; email is case/space-insensitive", async () => {
  seed([{ email: "Richard@Reliableheating.Team", name: "Richard",
          role: "user", password_hash: HASH }]);
  const u = await verifyCredentials("  richard@reliableheating.team ", "correct horse");
  assert.ok(u);
  assert.equal(u!.email, "richard@reliableheating.team");
  assert.equal(u!.role, "user");
});

test("wrong password and unknown user both return null", async () => {
  seed([{ email: "a@b.c", name: "A", role: "admin", password_hash: HASH }]);
  assert.equal(await verifyCredentials("a@b.c", "wrong"), null);
  assert.equal(await verifyCredentials("ghost@b.c", "correct horse"), null);
});

test("entries missing a hash are dropped, others survive", () => {
  seed([
    { email: "ok@x.y", name: "OK", role: "user", password_hash: HASH },
    { email: "broken@x.y", name: "Broken", role: "user" },
  ]);
  assert.equal(seedUsers().length, 1);
  assert.equal(seedUsers()[0].email, "ok@x.y");
});
