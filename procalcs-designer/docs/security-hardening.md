# Security hardening (branch: feature/security-hardening)

Closes the real gaps found in the codebase (not security theater — the
session cookies, dedicated runtime service account, Secret Manager, and
generic error responses were already correct). Everything is
**safe-by-default**: nothing locks anyone out on merge; the enforcing
switches are flipped deliberately.

## What's in it

**1 · Role-based route authorization** (`server/auth/authorize.ts`)
The app authenticated but never authorized — any logged-in account
(contractor crew included) could hit every endpoint. `requireRole` /
`requireRoleForWrites` gate routes by role (user < admin < super_admin,
resolved by email against the seeded accounts; OAuth/unknown → least
privilege). Applied to client-profiles + sku-catalog **writes**.
**Audit-only until `AUTHZ_ENFORCE=true`** — default mode logs would-be
denials (`security.authz_denied`) but allows, so you confirm the role
map from logs before enforcing.

**2 · Per-actor rate limiting** (`server/rateLimit.ts`)
No limits existed on the chat assistant (real Anthropic cost) or
uploads. Fixed-window limiter keyed by email, generous ceilings (chat
30/min, upload 20/min; env-tunable) so real use is never affected —
only runaway/abuse trips it, and every trip logs `security.rate_limited`.

**3 · Secret-leak guardrail** (`scripts/security/`, `scripts/git-hooks/`)
The "never commit .mdb / corpus / tokens / PII" rules relied on
vigilance. A pre-commit hook + CI check (`npm run security:check`) now
blocks them mechanically. Install per clone:
`git config core.hooksPath scripts/git-hooks`. Applies to the BOM
backend repo too.

**4 · Fail-closed service auth + audit log** (backend `app.py`)
The backend's shared-secret gate failed **open** on an empty secret.
Now it **denies by default** (503); dev opts out with
`ALLOW_INSECURE_NO_AUTH=1`. Auth failures emit structured `[security.*]`
audit lines.

## How to turn it on (in order)

1. Merge — nothing changes (authz audit-only, generous limits, fail-
   closed only bites a *misconfigured* deploy).
2. Watch `security.authz_denied` logs for a week; confirm no legitimate
   user is hitting an admin-write they should have. Adjust the role map
   or the seeded roles if needed.
3. Set `AUTHZ_ENFORCE=true` to start enforcing roles.
4. Install the pre-commit hook in every clone; add `security:check` to CI.

## Immediate ops action (not a code change)

Rotate the staging `SERVICE_SHARED_SECRET` — it has passed through
command output in cleartext over recent sessions. Low-effort, good
hygiene, do it regardless.

## Envs introduced

`AUTHZ_ENFORCE` (default off), `CHAT_RATE_MAX_PER_MIN` (30),
`UPLOAD_RATE_MAX_PER_MIN` (20), `ALLOW_INSECURE_NO_AUTH` (dev only).
