# Standard-BOM accessories — draft rules for Richard's review

**Status:** proposal only. Nothing here is wired into the BOM yet. Each
rule ships **only** after Richard confirms the per-system quantity — one
at a time, the way he reviews.

**Origin:** Richard, NE 132nd Terrace test (2026-09-24), comment #5 —
"Missing for a typical/standard BOM": filters, refrigerant pipes,
condensate pipes, thermostat, balancing dampers, support straps/clamps
(+ equipment cost, once quantities are locked). None of these are in the
`.rup` — Wrightsoft doesn't carry them — so they come from standard
per-system rules plus the mechanical schedule (M-sheets).

**Principle:** these are *standard inclusions*, not values read from the
file. Every line is provenance-tagged `standard_rule`, reviewer-
adjustable, and reversible (inline delete / chat). We never guess a
count the file could have given us.

---

## Proposed rules (each needs Richard's yes / adjust)

| # | Item | Proposed quantity rule | Drives off | Open question for Richard |
|---|------|------------------------|-----------|---------------------------|
| A | **Air filter** | 1 per air handler | equipment count | Filter size — from AH return, or a per-contractor default (e.g. 16×25×1)? MERV? |
| B | **Thermostat** | 1 per system (per condenser↔AH pair) | equipment count | 1 per system always, or 1 per zone when zoned? Model/tier a per-contractor default? |
| C | **Refrigerant line set** | 1 per condenser (liquid + suction) | condenser count | Length — fixed default (e.g. 25 ft), or from the M-sheet / a job field? Line sizes per tonnage? |
| D | **Condensate drain (PVC)** | 1 run per air handler | AH count | Default length + fitting kit? Primary + secondary/float switch included? |
| E | **Balancing dampers** | 1 per supply branch | branch/take-off count | Count source: one per supply take-off (from the file's take-off lines), or one per register? |
| F | **Support straps / clamps** | per flex run + per N ft of trunk | duct-cut piece count + trunk LF | Straps per flex run (1? 2 per run over X ft?) and clamps per ft of rigid trunk? |

**Counts we already have (from the fixed duct-cut work):**
- Flex runs / pieces per size — now correct per-piece (drives F straps).
- Take-off count per size — from the file's own take-off lines (drives E, pending the #2/#3 take-off reconciliation).
- Equipment count (AH / condenser) — from the equipment extract (drives A/B/C/D).

## What each rule does NOT do
- Does not invent a filter/thermostat *model* — size/model is a
  per-contractor default Richard sets once, not guessed per job.
- Does not set refrigerant/condensate *lengths* from thin air — those
  come from a default or the M-sheet, flagged for verify until then.
- Does not auto-apply to the pilot until confirmed.

## Sequencing
1. Confirm the **quantity rules** above with Richard (this doc).
2. Wire confirmed rules into `contractor-rules/reliable/rules.yaml`
   (provenance `standard_rule`), emitted into a **new "Standard
   accessories" section** so they're visually separable from Wrightsoft
   passthrough and easy to review/remove.
3. Surface each as a confidence-review line (medium confidence — "standard
   inclusion, verify for this job") until the count source is exact.
4. **Equipment cost** layers in last, once Richard accepts the quantities
   (his condition).

## M-sheet tie-in
Where a mechanical schedule PDF is provided, Phase 1 of
`docs/m-sheet-analysis-spec.md` reconciles the equipment schedule against
the BOM and can supply the real filter sizes, refrigerant lengths, and
accessory callouts — replacing the defaults above with job-specific
values. This doc is the deterministic-rules fallback for when no M-sheet
is available.
