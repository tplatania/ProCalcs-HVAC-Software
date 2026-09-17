#!/usr/bin/env python3
"""
check-secrets.py — pre-commit guardrail enforcing the repo's hard rules
mechanically (they were documented but relied on vigilance):

  NEVER commit: .mdb files, the Zoho corpus, crm.mdb / customer PII,
  service tokens, API keys, or private keys.

Scans the STAGED changes (git diff --cached). Exits non-zero with a
clear message if anything forbidden is staged, so the commit is blocked.
Override a false positive with:  SKIP_SECRET_CHECK=1 git commit ...

No third-party dependencies — runs anywhere Python 3 does.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

# ── Forbidden file paths (by name/path fragment) ──────────────────────
_FORBIDDEN_PATH = [
    (re.compile(r"\.mdb$", re.I), "Access database (.mdb) — never commit"),
    (re.compile(r"crm\.mdb", re.I), "crm.mdb (customer PII) — never commit"),
    (re.compile(r"RUPs-from-zoho", re.I), "Zoho corpus — never commit"),
    (re.compile(r"/envs/|(^|/)\.env(\.|$)", re.I), "env/secret file — never commit"),
    (re.compile(r"\.pem$|\.p12$|\.pfx$|id_rsa", re.I), "key material — never commit"),
]

# ── Forbidden content patterns (scanned in added lines) ───────────────
_FORBIDDEN_CONTENT = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key block"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{35}"), "Google API key"),
    (re.compile(r"sk-ant-[0-9A-Za-z_\-]{20,}"), "Anthropic API key"),
    # Generic: SECRET/TOKEN/API_KEY/PASSWORD = <20+ high-entropy chars>
    (re.compile(r"(?i)(secret|token|api[_-]?key|password|passwd)"
                r"\s*[:=]\s*['\"]?[A-Za-z0-9+/_\-]{20,}"),
     "hard-coded secret/token assignment"),
]

# Files where a secret-shaped match is expected/benign (this checker,
# and lockfiles full of base64 hashes).
_CONTENT_SKIP = re.compile(
    r"check-secrets\.py$|package-lock\.json$|pnpm-lock\.yaml$|yarn\.lock$|\.test\.")


def _staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f.strip()]


def _added_lines(path: str) -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--", path],
        capture_output=True, text=True).stdout
    return [ln[1:] for ln in out.splitlines()
            if ln.startswith("+") and not ln.startswith("+++")]


def main() -> int:
    if os.environ.get("SKIP_SECRET_CHECK") == "1":
        print("check-secrets: skipped (SKIP_SECRET_CHECK=1)")
        return 0

    violations: list[str] = []
    for path in _staged_files():
        for rx, why in _FORBIDDEN_PATH:
            if rx.search(path):
                violations.append(f"  {path} — {why}")
        if _CONTENT_SKIP.search(path):
            continue
        for line in _added_lines(path):
            for rx, why in _FORBIDDEN_CONTENT:
                if rx.search(line):
                    snippet = line.strip()[:60]
                    violations.append(f"  {path}: {why} → “{snippet}…”")
                    break

    if violations:
        print("\n✋ Commit blocked — forbidden content staged:\n")
        print("\n".join(dict.fromkeys(violations)))  # de-dup, keep order
        print("\nRemove it (git restore --staged <file>) or, if this is a "
              "false positive, re-run with SKIP_SECRET_CHECK=1.\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
