# From Corpus to Converged Engine — the 48-Hour Journey

*2026-07-14 → 2026-07-16. Covers everything after the full Zoho
archive landed locally (12 communities, ~8,000 files, 13 GB,
Canopy excluded by instruction).*

---

## Where we started

The engine could extract Wrightsoft's own priced lines from a `.rup`
and nothing more. Validated against a single file (79th Ct — later
proven a double outlier), every fix risked breaking something
unseen: the "fix one, break another" era. **Baseline: drafts carried
41% of an expert BOM's lines.**

## The strategy that changed it

Two decisions, both Gerald's:

1. **Reproduce → residual → extend.** Use the ~1,000 historical
   rup+BOM pairs as an answer key: teach the engine to reproduce
   Richard's finished BOMs from the design file alone, measure
   exactly what it can't, and spend expert time only on the measured
   residual.
2. **The compounding question loop.** Every corpus pass generates
   clarification questions; later passes close them with evidence or
   open new ones; the expert sees only what survives. Amendments
   added in-flight: evidence tiers for closure, a materiality bar
   (only questions that change BOM output), and a stopping rule
   (converged when a pass closes 0 and opens 0).

## The passes

| Pass | What ran | What it produced |
|---|---|---|
| **P0** — 20-pair pilot | Frozen-engine scoring, stratified across 10 communities | Recall 0.41; residual = 88% one thing (the Rheia section, byte-proven ABSENT from the .rup); first rule extracted: boots/diffusers = registers − 1 (exact 20/20) |
| **P1** — full corpus | 1,619 rups (0 parse errors), 1,076 pairs | Footage decode (DUCT block, ceil(Σ per-run lengths) — exact to the foot on 71%); takeoffs = run count (762/762); Goodman↔Daikin = same hardware (62 AHRI sheets); revision-skew list named |
| **P2** — memo + correlations | Plan-memo harvest + feature correlation | Fitting hardware is per-plan constant → memo closes it (holdout: recall 0.652→0.739, no leakage); heat strip already in the file 68% of the time (copy = 98.8%); dehumidifier = era effect, 93% rule |
| **P3** — document sweep | 21,362 docs enumerated, pricing docs read | Contractor pricing provably NOT in the archive (all money documents are ProCalcs design-service billing) → the 2 unavoidable Richard pastes |
| **P4** — targeted closures | Mount-type decode agent, ERV scan, xls fingerprint, skew recovery | The ceiling/sidewall split is per-register DATA in the file (DREGPERF stores the literal SKU — 92.6% exact triples); ERV variant = era; export toggles = fixed (148/150 identical); 91 skewed pairs recovered via sibling revisions |
| **P5** — the unread 95% | Email mining, standard-BOM census, ambiguous-pair recovery | Dehumidifier = Beazer spec revision **in writing** (removed from load calcs 2025-03-05, townhomes only); SKU generations = Rheia Phase-2 cutover **in writing** (2022-07-01); **standard projects: 5/5 sales-office BOMs reproduce at recall 1.0 with zero new work**; +245 ground-truth pairs recovered (final: 1,321) |
| **P6** — formal convergence | Zero-zero pass + new-question detector | Closed 0, opened 0, no unledgered pattern ≥5% of pairs → **CONVERGED by the rule as written** |

## Engine versions (each promoted only with corpus evidence)

| Version | Added | Recall (median) |
|---|---|---|
| v1 | RPITEM extraction | 0.41 |
| v2 | Register rules (boots/diffusers) | 0.59 |
| v3 | Home-run footage decode | 0.62 |
| v4 | Takeoffs = run count | 0.67 |
| v5/v6 | Per-plan memo + ERV default + merge fallback | 0.74–0.78 |
| **v7** | **Mount-type decode (per-register SKUs from the file)** | **0.75–0.78, qty accuracy 0.96–1.00** |

Standard (non-Rheia) projects: **recall 1.0** — Wrightsoft's own
takeoff covers conventional duct; the product there is "run the
export nobody ran."

## The question ledger — the loop's scoreboard

14 material questions entered across six passes. Final state:
**11 closed by the corpus itself** (6 deterministic decodes/rules,
5 documentary — answered by emails, spec sheets, and Rheia's own
checklist found *inside* the archive), **2 provably not-in-data**
(the price sheets), **1 sharpened one-liner** (heat-strip kW rule
for legacy files). The expert interview shrank from 31 questions to
**two pastes and one sentence** — with the evidence for every
retired question on file.

## Quality gates before the expert sees anything

- **Smoke suite** (29 real uploads through the staging API,
  stratified over community × master/lot/CO × era × standard ×
  negative controls): medians recall 0.773 / precision 0.864 /
  **qty 1.000**, ~5s per draft, zero errors. The suite caught two
  real defects pre-release (generation-pair duplicates; junk files
  returning empty drafts) — both fixed, redeployed, re-verified.
- **Behavioral checks**: price saved once → applied on every future
  upload (the core promise, re-verified on the shipped build); chat
  agent produces correct one-click price proposals.
- **P6 + verification re-walk**: formal convergence recorded;
  archive completeness walk running (expected clean — zero new
  files on all partial passes).

## What deliberately remains for the expert

1. **Rheia price sheet** (12 SKUs) — proven absent from 21k docs.
2. **Equipment cost sheet** — same proof.
3. One sentence: *"When a design file has no heat strip placed, is
   there a standing kW rule today, or is it per builder spec?"*

## Where everything lives

- Engine + parsers: `dev/bom-engine-20260716` (GitHub)
- App + ledgers + analysis tooling: `dev/designer-desktop-20260716`
- Question ledger: `contractor-rules/reliable/questions.yaml`
- Run artifacts: `~/Procalcs/full-corpus-run-2026-07-15/`
- Staging (tested build): designer rev 66 / BOM rev 120
