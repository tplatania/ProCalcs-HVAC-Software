# BOM Module: V1 Definition of Done

**Status:** Pass 1 and Pass 2 complete. All scope decisions made by Catherine 2026-09-26 (Catherine is the decision-maker and release authorizer). Remaining items are evidence and actions, not decisions. Verdict dated 2026-09-26.
**Inputs:**
- Gerald's DoD draft (2026-09-25)
- `tplatania/ProCalcs-HVAC-Software`, branch `dev/gerald-designer` @ `c48821d` (2026-09-24). `main` is stale at April.
- a local test run I did on that branch
- beta brief and evidence index
- workshop prompt

The Designer Dashboard repo (`ProCalcs_Design_Process`) was not accessible, so the Dashboard QC entry point is **Unknown** and is out of v1.

## 1. V1 promise and buyer

**Buyer:** Reliable Heating and Cooling (pilot).

Reliable gets a BOM draft built from a Wrightsoft design that a reviewer has completed. The draft covers conventional residential jobs. Quantities and prices come from fixed rules, and every uncertain or missing item is visibly flagged. The draft is not treated as final until a named reviewer finishes it. We do **not** promise a complete, automatic BOM.

## 2. Supported path and limits

**Mode:** limited external pilot with Reliable only.

In scope:
1. **Input:** a `.rup` file that was **built** in Wrightsoft, for a conventional (non-Rheia) residential job. A Wrightsoft `.xls` is optional corroboration only. Anything else stops with a clear message.
2. **Generate:** deterministic pilot path only. The AI generation path cannot be selected.
3. **Review:** every line shows its source and a confidence flag, and a gap summary lists what the file could not confirm. The reviewer can delete lines, correct quantity or price, and apply chat suggestions. Changes survive regenerate and record who made them.
4. **Pricing:** materials only, from Reliable's own cost sheet loaded as a dated, versioned price list, with no markup. Wrightsoft catalog, `.xls` and estimated fallback prices are off. A line with no Reliable price shows as unpriced. A "without pricing" export is also available, and every export shows the price-list date.
5. **Output:** PDF and XLS that match the reviewed run exactly.

Excluded from v1:
- Rheia jobs
- the AI generation path
- M-sheet upload and reconciliation (groundwork only, `c48821d`)
- `.xls`-only input
- scanned-sheet OCR
- guessed grille, register or flex sizes
- automatic rule learning
- the Dashboard QC integration
- any contractor other than Reliable
- billing
- labor lines and sales tax (Reliable adds its own)

## 3. Definition of Done (launch gates)

| # | Pass condition (yes/no) | Sign-off | Evidence |
|---|---|---|---|
| B1 | **Accuracy:** Richard compares 8 frozen Reliable projects (including Melko and NE 132nd) plus 2 deliberately incomplete files line by line with his own takeoff. Result: zero S1/S2 defects, zero **silent** omissions (each gap is flagged or on the checklist), and precision ≥ 0.95 and quantity accuracy ≥ 0.95 on matched lines. Recall is reported, not gated | Richard | Signed comparison per project, run IDs |
| B2 | **Money math:** every price traces to a line on Reliable's cost sheet, and every extension and total reconciles exactly. No fallback, estimate, AI or extraction step sets or changes a price. Unpriced lines can't be exported as priced | Richard; Gerald (tests) | Fixtures + one reconciled real BOM using Reliable's sheet |
| B3 | **Safe stops:** Given an unbuilt, Rheia, unsupported or incomplete source, When it's uploaded, Then the user gets a clear stop or a visible gap, never a clean-looking list | Dana | One blocked demo BOM |
| B4 | **Reviewer workflow:** on one pinned frontend/backend pair, a reviewer completes sign in → upload → review flags → correct → regenerate → export, and the exports match the run | Dana | Signed browser UAT |
| B5 | **Access:** fail-closed service auth is merged and deployed, and the shared secret is rotated. Reviewer identity is set server-side. A Reliable login sees only Reliable runs | Gerald | Negative access tests, deploy record |
| B6 | **Durability:** a production database separate from staging, migrations tested, backups on, and one restore done | Gerald | Migration + restore logs |
| B7 | **Release control:** one manifest pins the backend, SPA, schema, rules-ledger version and revisions. Backend CI exists and is green. Rollback to the prior pair has been rehearsed | Gerald | Manifest, CI URL, rollback log |
| B8 | **Support:** Catherine and Dana own wrong-BOM handling, with a 1 business day response (Catherine, 2026-09-26). Known-limitations text goes to every pilot reviewer. Source files and BOMs are kept 12 months or deleted on customer request | Catherine | Written note; retention setting in prod |

## 4. Current evidence

| Gate | Status | Evidence |
|---|---|---|
| B1 | **Needs proof** | Baseline only (n=1,076, mostly Rheia): recall 0.696, precision 0.885, quantity accuracy 0.944. About 30% of lines are missed. *Code/test only.* No frozen corpus or thresholds yet. The Melko fresh upload is still pending. NE 132nd duct cuts are verified by Richard (`bc7cce7`). |
| B2 | **Blocked** (priced output only) | **0 real contractor prices loaded**: Reliable's cost sheet has not been received. The code currently fills missing prices from Wrightsoft's hosted catalog (with its margin rules), the `.xls` price column, and a hardcoded estimated equipment-cost table, and its own comments say it can't always tell when an estimate was used (`services/bom_from_wrightsoft.py`, `28bd62e`). **Conflict:** Gerald's Gate 3 lists "markup", but policy since 9/3 is no markup (`b59480e`). |
| B3 | Needs proof | An unbuilt-file banner and verify flags exist. Dana's `.xls`-only heat-strip thread is open. |
| B4 | Needs proof | Implemented in staging (backend `…-00151-5m4`, SPA `…-00102-26r`, per Gerald). The release commits are not mapped to those revisions. There is no signed UAT. |
| B5 | **Blocked** | Fail-closed auth `62bbb47` is **still not merged** as of `c48821d`. Roles exist but "No route enforcement yet" (`procalcs-designer/server/auth/seedUsers.ts`). Any signed-in user can list every client's runs (`bom_runs_routes.py`). **Gap in Gerald's draft:** his security gate does not cover client isolation. |
| B6 | Needs proof | Staging uses shared Cloud SQL. No production database, backup or restore yet. |
| B7 | Needs proof | CI covers the Designer app only. There is **no BOM backend CI**. My run: 660 passed, 1 failed, 21 skipped. The skipped tests are the real-file accuracy tests; their fixtures sit only on Gerald's machine. Gerald's run, in a different environment: 676 passed, 3 failed, 3 skipped. |
| B8 | Needs proof | Owners (Catherine + Dana) and 12-month retention decided by Catherine 2026-09-26. The support note and retention setting are not written yet. |

## 5. Top three gaps or decisions

1. **Get Reliable's cost sheet.** Owner: Catherine to request, via Ashley or Tom. Fields: part number, description, unit (each, foot, box), unit cost, supplier and effective date, plus who sends updates when prices change. Then Gerald loads it and turns off the fallback prices, and Richard checks the part-number mapping. Blocks priced output only; the pilot can start with unpriced parts lists.
2. **Richard's rulings.** Owner: Richard. Freeze the 10 files for B1 and rule on grille defaults and the extra 7-inch takeoff. Blocks B1.
3. **Security fix.** Owner: Gerald. Merge and deploy fail-closed auth, rotate the shared secret, and add client isolation so a Reliable login sees only Reliable runs. Blocks B5, and Reliable logins.

**Decision log**

| Decision | Who | Date | Status |
|---|---|---|---|
| Reliable users may log in, only after B5 client isolation passes | Catherine | 2026-09-26 | Decided |
| Support: Catherine and Dana, 1 business day response | Catherine | 2026-09-26 | Decided |
| Retention: 12 months, or deletion on customer request | Catherine | 2026-09-26 | Decided |
| Prices come directly from each contractor | Tom | Recorded in `data-sources.md` row 15 | Decided |
| No markup on contractor BOMs | Team policy | 2026-09-03 (`b59480e`) | Decided |
| Materials only; labor and tax out of v1 | Catherine | 2026-09-26 | Decided |
| Input: built `.rup` required, `.xls` optional, M-sheet out | Catherine | 2026-09-26 | Decided |
| Richard is accuracy authority; 8 projects + 2 incomplete files; precision and quantity accuracy ≥ 0.95; every gap flagged | Catherine | 2026-09-26 | Decided |
| Release authorizer is Catherine (Gerald's draft names Tom; align it) | Catherine | 2026-09-26 | Decided |
| Merge and deploy fail-closed auth; rotate shared secret; client isolation | Gerald | — | Action, not a decision |
| Request Reliable's cost sheet | Catherine | — | Action, not a decision |

Moved to v1.1: M-sheet reconciliation, `.xls`-only input, AI path, fittings from `FITNG`, labor and tax lines, cold-start fix (the ~29s cold start is accepted for the pilot), the learning loop, additional contractors, Dashboard integration.

## 6. Launch verdict and allowed claim

**Verdict (2026-09-26): Not ready.** It becomes *Ready for a limited external pilot (Reliable)* once B5 is unblocked and B1, B4, B6 and B7 are met with sign-offs. Priced BOMs additionally need B2, which waits on Reliable's cost sheet.

**May say (to Reliable only):** "We're piloting a BOM draft built from your Wrightsoft file. Every item it can't confirm is flagged, and a reviewer completes it before you use it."
**Must not say:** automatic, one-click or complete BOM; "priced with your costs" until the cost sheet is loaded; "learns from your corrections"; Rheia or M-sheet support; availability to other contractors; any date.
