# Secret-leak guardrail

Enforces the repo hard rules mechanically (never commit .mdb, the Zoho
corpus, crm.mdb PII, service tokens, API keys, or private keys).

## Install (once per clone, both repos)

    git config core.hooksPath scripts/git-hooks

Now every `git commit` runs `check-secrets.py` against the staged
changes and blocks the commit on a violation. Override a false positive
with `SKIP_SECRET_CHECK=1 git commit ...`.

## CI

Run `npm run security:check` (or `python3 scripts/security/check-secrets.py`)
on staged changes in a pre-merge job.

Applies to the BOM backend repo too — copy `scripts/security/` +
`scripts/git-hooks/` there and set the same `core.hooksPath`.
