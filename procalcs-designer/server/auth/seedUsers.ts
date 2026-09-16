// Seeded password accounts — Day-27.
//
// Staging ran with AUTH_ENABLED=false, which stubbed EVERY visitor as
// dev@procalcs.net (runs 353/354 were untraceable humans). Password
// auth with pre-seeded accounts closes that hole without the
// onboarding back-and-forth a Google-OAuth allow-list would need for
// Richard's team.
//
// Seeds come from the SEED_USERS_JSON env (Secret Manager secret
// `designer-seed-users`), an array of:
//   { email, name, role, password_hash }   // bcrypt hash, never plaintext
//
// Rules:
//   - Plaintext passwords NEVER live in the repo, env, or logs.
//   - role is metadata surfaced via /api/auth/me (super_admin | admin |
//     user). No route enforcement yet — provenance and audit first.
//   - Account emails are identifiers, not mailboxes — nothing is sent
//     to them. Internal admin accounts should also be listed in the
//     BOM service's TEST_ACTOR_EMAILS so staff activity never counts
//     as contractor learning input.

import bcrypt from "bcryptjs";

export interface SeedUser {
  email: string;
  name: string;
  role: "super_admin" | "admin" | "user";
  password_hash: string;
}

let cache: SeedUser[] | null = null;

export function seedUsers(): SeedUser[] {
  if (cache) return cache;
  const raw = process.env.SEED_USERS_JSON;
  if (!raw) return (cache = []);
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) throw new Error("not an array");
    cache = parsed.filter(
      (u): u is SeedUser =>
        typeof u?.email === "string" &&
        typeof u?.password_hash === "string" &&
        typeof u?.name === "string",
    ).map((u) => ({ ...u, email: u.email.toLowerCase().trim() }));
  } catch (err) {
    console.error("[auth] SEED_USERS_JSON is malformed — password auth disabled:",
      err instanceof Error ? err.message : err);
    cache = [];
  }
  return cache;
}

export function passwordAuthEnabled(): boolean {
  return seedUsers().length > 0;
}

/** Constant-work credential check: unknown emails still burn a bcrypt
 * compare against a dummy hash so response timing doesn't leak which
 * accounts exist. Returns the matched user or null. */
const DUMMY_HASH = bcrypt.hashSync("dummy-timing-equalizer", 10);

export async function verifyCredentials(
  email: string,
  password: string,
): Promise<SeedUser | null> {
  const user = seedUsers().find((u) => u.email === email.toLowerCase().trim());
  const ok = await bcrypt.compare(password, user?.password_hash ?? DUMMY_HASH);
  return ok && user ? user : null;
}

/** Test-only: reset the module cache between env mutations. */
export function _resetSeedCache(): void {
  cache = null;
}
