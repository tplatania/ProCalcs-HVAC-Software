# Confidence & Materiality Review Layer (branch: feature/confidence-review)

Research-grounded feature (see the deep-research proposal): professional
takeoff tools in 2026 don't just flag uncertainty — they **grade** it by
confidence and dollar weight, auto-trust high-confidence items, and route
**low-confidence OR high-dollar** items to human review ("the human owns
the final number"). ProCalcs already flagged (verify badges) but the
flags were binary and unquantified. This layer makes them graduated and
materiality-aware.

## What it does

- **Confidence per flag** — the engine now emits `verify_confidence`
  (low/medium/high) at each flag site: heat strips = medium (the count
  is in the file, only intent is uncertain), empirical-only equipment =
  low (may be a phantom selection), grille lumping = low (the true split
  isn't recoverable). Carried through the wrightsoft pricing pass.
- **Materiality per flag** — each flagged line gets `verify_materiality`
  (its dollar weight).
- **BOM-level `review_summary`** — flagged_count, by_confidence, flagged
  dollar value, a high-dollar threshold (max $500 or 5% of the BOM), and
  `priority_lines` = low-confidence OR high-dollar, sorted riskiest-first.
  Computed in `services/review_confidence.py`, attached on the
  from-wrightsoft and regenerate paths, and stored in the run.
- **UI** — a "Review readiness" card (which lines to check first) and a
  confidence tier + dollar weight on the existing verify badge.

## Safety

Additive: the flags, prices, and BOM contents are unchanged; this only
adds grading metadata + a summary. Defaults-safe, no generation change.
Pull-when-needed branch, independent of the other feature branches.

## Notes / possible follow-ups

- Confidence levels are per-flag-class (engine-assigned). If a new flag
  class is added, give it a `verify_confidence`.
- The high-dollar threshold is heuristic (max $500 / 5%); could become a
  per-contractor setting.
- Composes naturally with `feature/reviewer-workspace` — the readiness
  card + the mark-reviewed control together make a full review loop.
