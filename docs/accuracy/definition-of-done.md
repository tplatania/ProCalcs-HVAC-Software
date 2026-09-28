# BOM Accuracy Definition of Done

**Status:** Not complete. This document supplements, and does not replace, the BOM Module v1 product Definition of Done.

## Outcome

Accuracy is handed off when the team can independently compare BOM drafts with Richard's takeoffs, measure items and quantities, prove every price from Reliable's dated cost sheet, expose every unsupported gap, govern rule changes, and repeat the evaluation as pilot usage compounds.

## Initial certification gates

| Gate | Pass condition | Sign-off | Evidence |
|---|---|---|---|
| BA1 Corpus | Richard freezes eight Reliable conventional projects, including Melko and NE 132nd, plus two deliberately incomplete built `.rup` files. Expected takeoffs and checksums are immutable | Richard | Completed corpus manifest and protected source set |
| BA2 Item accuracy | Across the eight supported projects, precision is at least 0.95. Recall is reported, not gated. There are zero S1/S2 defects and zero silent omissions | Richard | Eight signed evaluation records and aggregate report |
| BA3 Quantity accuracy | Quantity accuracy on matched lines is at least 0.95, with every mismatch identified by item and rule | Richard | Aggregate quantity report and disagreement closures |
| BA4 Incomplete safety | Each deliberately incomplete file stops clearly or exposes every missing/uncertain requirement in the gap summary or required checklist | Richard + Dana | Two signed incomplete-file evaluations |
| BA5 Pricing integrity | Every priced line maps to Reliable's versioned cost sheet; extensions and totals reconcile exactly. Missing costs remain unpriced, and no fallback, estimate, markup, labor, tax, AI, `.xls`, or Wrightsoft catalog value supplies a price | Richard + Gerald | Price provenance fixture and one reconciled real BOM |
| BA6 Reviewer control | Corrections survive regenerate, record the reviewer, and match PDF/XLS exports exactly | Dana | Signed browser workflow |
| BA7 Regression | Every parser, deterministic rule, price-list mapping, gap-check, or export change passes the full frozen corpus before release | Gerald | Repeatable evaluation command and stored report |
| BA8 Handoff | Owners can locate the corpus, run or request evaluation, interpret precision/recall/quantity measures, resolve or block disagreements, and identify the released rule and price-list versions | Catherine | Signed handoff record |

## Metric definitions

- **Precision:** correct generated item lines divided by all generated item lines.
- **Recall:** expected item lines found divided by all expected item lines. Report it even though v1 does not gate on it.
- **Quantity accuracy:** matched lines with an accepted quantity divided by all matched lines.
- **Silent omission:** an expected item absent from the BOM and absent from the visible gap/checklist output.
- **S1/S2 defect:** a critical or major defect under the pilot severity rubric; the record must state the impact.

The corpus manifest must freeze matching rules, unit normalization, duplicate handling, and accepted quantity tolerance before scoring begins. Do not change scoring rules after seeing results without creating a new corpus version.

## Required controls

1. Every line records its source rule and relevant `.rup` evidence; every price records cost-sheet version and row/part mapping.
2. Unsupported, incomplete, unbuilt, Rheia, or ambiguous input stops or produces an explicit gap—never a clean-looking complete BOM.
3. Reviewer corrections and chat suggestions remain run-specific until a rule proposal is approved.
4. A proposed rule change identifies its authority, supported job types, expected corpus impact, risk, and rollback.
5. Richard approves domain-rule changes. Catherine approves release-policy changes.
6. The full frozen corpus must pass before an approved change becomes releasable.

## Continuing certification

Review accuracy monthly or every 25 Reliable pilot BOMs, whichever occurs first. Report:

- supported, blocked, and incomplete jobs;
- precision, recall, and quantity accuracy;
- S1/S2 defects and silent omissions;
- repeated gap and correction categories;
- priced, unpriced, and stale-price-list lines;
- changes approved, rejected, or rolled back;
- known limitations added or closed.

Re-certify the frozen corpus whenever parsing, deterministic rules, unit normalization, gap detection, contractor price mapping, reviewer persistence, or export behavior changes.

## Stop and escalation rules

- Stop the affected pilot workflow on an S1/S2 defect, silent omission, cross-customer access, price without Reliable provenance, or export mismatch.
- Roll back any change that regresses a passing corpus result without Richard's accepted policy change.
- Escalate takeoff and rule disagreements to Richard; release and scope disagreements to Catherine.
- Record every unresolved issue with an owner and resolve-or-block date.

## Completion declaration

Accuracy handoff is complete only when BA1–BA8 contain evidence links and all named signers have approved the same pinned frontend, backend, schema, rules-ledger, and price-list versions. Catherine remains the final release authorizer.
