# BOM Module strategy — reproduce → residual → extend

*2026-07-15. Supersedes the observer-agent-first plan (2026-07-13) and
the autonomous-assembler framing before that.*

## Goal (corrected 2026-07-14)

Automate BOM creation for **standard projects** — the projects that get
no BOM today. The company currently produces BOMs only for Rheia
projects (Rheia's system requires a parts manifest). Standard projects
have `.rup` design files but no parts list; the BOM module fills that
gap. We are not replacing Richard's Rheia workflow — we're creating an
output that doesn't exist.

## The two truths we must hold simultaneously

- **Tom: "everything is in WS."** True for *inputs*: duct geometry,
  register CFMs, equipment selections are all decodable from the
  `.rup` (our structural parsers already do it).
- **Richard: "no single rule for all."** True for the *transformation*:
  design → parts list is conditional on community, plan, system type.
  So rules are stored as scoped, provenance-tagged entries in
  `contractor-rules/reliable/rules.yaml`, never as one global default.

## Why we kept regressing ("fix one, break another")

We validated against a single file (79th Ct — an edge case twice over:
Trane-equipped AND an outlier in priced total). Any rule tweak could
silently break other projects. The fix is a **regression corpus**:
~900 Rheia `.rup`+BOM pairs where Richard already did the
transformation. Every engine change is scored against all pairs at
once; regressions surface as a diff count, not a surprise.

## Three phases

### Phase 1 — Reproduce (prove the machine)
Generate BOMs from `.rup` alone; score line-by-line against Richard's
actual BOMs across all matched pairs. Output: a reproduction-accuracy
number and a per-line diff corpus. Zero Richard time required.

### Phase 2 — Isolate the residual (measure the "Richard knowledge")
Whatever the engine can't reproduce IS the situational knowledge —
now enumerated with real examples instead of hypothetical interviews.
Expected concentration: heat-strip sizing, brand-alternate triggers,
boot/register type selection.

### Phase 3 — Extend to standard projects (the product)
The geometry→quantity logic transfers; the parts catalog swaps
(standard flex/ductboard SKUs instead of Rheia part numbers). Needs
from Richard: ONE worked example of what a standard-project BOM should
contain — a bounded ask.

## Richard engagement model: reviewer, not author

Never ask for rules in the abstract (they're situational and can't be
recalled in one sitting; he also has no written record — confirmed
2026-07-13). Always show a concrete draft: "here's the generated BOM
for Lot X, 3 lines flagged low-confidence." Each correction persists
to the rules ledger with provenance. The QA UI is a draft-review
surface, not a questionnaire. The Windows observer agent is shelved —
too intrusive on Richard's workflow (2026-07-14 decision).

## Data foundation

- Corpus: `~/Procalcs/RUPs-from-zoho/` — 12 communities (Canopy
  excluded by instruction), ~4,300+ files, sync completing 2026-07-15.
- Analysis pipeline: `scripts/corpus-analysis/` (4 stages, incremental).
- Selection-bias rule: BOM `.xls` exists ⇒ Rheia project. `.rup`
  without BOM ⇒ (mostly) standard project — the target population.
- Catalog data: Wrightsoft `.mdb` databases (RPRUWSF parts catalog,
  arigama2/xeqp2 equipment) — being API-fied read-only; binaries never
  committed. `crm.mdb` is privacy-sensitive: excluded, never ingested.

## Phase 1 pilot — measured (2026-07-15, 20 pairs, engine frozen)

`scripts/corpus-analysis/repro_harness.py`, stratified across 10
communities. **Recall 0.41 median / precision 1.00 / qty accuracy
1.00 on matched lines.** The residual is one thing, not many:

- **88%** — the Rheia duct-system section (~18 SKUs). Byte-probe
  proved these SKUs appear NOWHERE in the .rup — Wrightsoft's Rheia
  plugin derives them from drawing geometry at export time. We must
  derive them ourselves. Two rules already extracted and validated
  exact on 14/14 pairs: **boots = registers − 1, diffusers =
  registers − 1**. The 3-in duct footage requires the home-run
  drawing-geometry decode (trunk segments proven NOT predictive).
- **10%** — Broan ERV (19/20) + dehumidifier (9/20): absent from the
  .rup, added by Richard → one contextual QA card.
- **2%** — genuine one-off tail (5 instances in 268).

Known parser gaps: BALDUCT empty on Creekside / Park View /
Pennyroyal file era; equipment lines duplicated across parallel
investments.
