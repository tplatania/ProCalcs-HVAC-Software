# Corpus findings — first pass (2026-07-14), corrected

*Analysis of the partial corpus (401 built `.rup` / 221 matched BOM
pairs, 4 communities). **Corrected 2026-07-15** after learning that
BOMs are produced only for Rheia projects — findings marked ⚠ were
originally overstated due to selection bias. Full-corpus re-run
pending sync completion (~3,200 rups / 12 communities).*

## Corrections first

1. ⚠ **"RHEA on 100% of projects" → selection bias.** BOMs exist only
   for Rheia projects, so "projects with BOMs" ≡ "Rheia projects".
   Corrected claim: *IF a project is Rheia, THEN the 12-SKU kit
   appears* — still useful as the Rheia fitting-kit definition.
2. ⚠ **Equipment percentages describe Rheia projects only.** Standard
   projects (rups without BOMs — e.g. Windham Park, 151:15) may have a
   different equipment mix. Verify against EQUIP blocks in unpaired
   rups during the full-corpus run.
3. **Trane correction stands.** 79th Ct ("Edge Case" in filename) is
   Trane-equipped and a P99+ priced-total outlier. Production is
   Goodman/Daikin/Broan — zero Trane in 401 files.

## Findings that hold

- **All 401 rups parse with zero errors** through the structural
  parser stack — the extraction machinery is corpus-proof.
- **Every rup in the sample was built** (RPITEM/RPRPART present).
- **Rheia fitting kit** (12 SKUs, `10-*`/`00-*` part numbers): duct,
  ferrules, boot assemblies, diffusers, takeoffs, hangers. One
  townhome = ~668 ft of 3-in duct (10-00-190).
- **RHEA SKUs carry no Wrightsoft price anywhere** — Rheia pricing
  lives outside WS. Highest-leverage catalog fill available
  (~6 minutes of Richard's time for the 12 core SKUs).
- **Equipment defaults on Rheia projects**: Broan B150E75NT ERV
  (94.6%), Goodman HKTSD05X1 5kW strip (79.2%), Goodman AHVE24BP1300A
  AH (72.4%), Goodman GZV6SA1810A condenser (54.8%); Daikin as the
  alternate line (~11–18%).
- **QA aggregation works**: ~2,800 raw per-project questions collapse
  to 31 profile-level ones. Top question: heat-strip sizing rule.

## Artifacts

`~/Procalcs/reliable-analysis-2026-07-14/` — scripts (also committed
at `scripts/corpus-analysis/`), JSON outputs, profile draft, QA list.
Derived rules now live in `contractor-rules/reliable/rules.yaml` with
provenance and confirmation status.

## Full-corpus run (2026-07-15 overnight — supersedes the 20-pair pilot)

1,619 canonical Finals rups (0 parse errors) / 1,076 scored pairs.
Artifacts: `~/Procalcs/full-corpus-run-2026-07-15/` (features.jsonl,
pairs.jsonl, summary.json); script committed at
`scripts/corpus-analysis/full_corpus_pass.py`.

- **Scoreboard** (engine v3 → v4): recall 0.62 → 0.67, precision
  0.93 → 0.88, qty 0.77. v1 baseline was 0.41.
- **Footage decode: exact on 762/1,074 pairs (71%)**; the 312
  "skewed" pairs are rup↔xls revision mismatches — now a named
  exclusion list for ground truth.
- **Takeoffs = home-run count, exact on 762/762 clean pairs.** Two
  SKU generations (040/050 vs 041/051) split by community era.
- **Fitting hardware is per-plan constant** (ferrule/run IQR width
  ≈ 0 within communities): exact formulas need Rheia's elbow-placement
  geometry, BUT per-plan memoization sidesteps that — copy fitting
  quantities from any prior BOM of the same plan. Highest-value next
  engine feature.
- **Goodman↔Daikin equivalence confirmed** by 62 AHRI export sheets
  in lot folders (R32 platform rebadge) — retires one QA question.
- **Rheia's own Design Checklist** (in corpus) confirms manifold
  holes == registers and 3"/4" run sizing; elbow rules are public
  Rheia docs.

## Final v6 scoreboard (2026-07-16, all 1,076 pairs, engine as deployed)

**recall 0.783 / precision 0.857 / qty-accuracy 0.889** (medians;
means within 0.03). v1 baseline 48h earlier: 0.41 / 1.00 / 1.00.
Includes plan-memo with merged-community fallback. Honest holdout
reference: 0.739 recall (memo learned excluding the scored lot).
Document sweep complete: 21,362 docs, zero contractor-side pricing —
pricing questions confirmed not-in-data exhaustively.

## P5 — standard-project ground truth found and PASSED (2026-07-16)

Census of all 2,630 BOM xls: 2,611 Rheia, **15 standard (non-Rheia) —
all Sales Office projects** (5 unique). Scored the existing engine
against every one: **recall 1.00 on 5/5, precision 0.73–1.00, qty
0.93–1.00.** Standard projects need NO new derivation: Wrightsoft's
own takeoff populates RPITEM for conventional duct — the Rheia gap
existed only because the Rheia plugin bypasses RPITEM. The BOM module
for standard projects is, in effect, "run the export Wrightsoft never
ran" — already working in the deployed engine.

## P5 complete — corpus exhausted (2026-07-16)

- **Ground truth final: 1,321 pairs** (1,076 base + 154 ambiguous-lot
  recoveries + 91 revision recoveries).
- **Email mining** (22 threads read): dehumidifier = Beazer townhome
  spec revision, removed from load calcs 2025-03-05 (Pratt emails);
  takeoff SKU generations = Rheia Phase-2 cutover 2022-07-01. Both
  closed documentarily. Heat-strip legacy variance = builder-spec
  churn (proven) → one confirmation line remains.
- **Standard projects: solved without new work** — 5/5 sales-office
  BOMs reproduce at recall 1.0 with the existing engine (Wrightsoft's
  takeoff populates RPITEM for conventional duct).
- **Plan versions change fitting quantities (12/12 multi-version
  plans)** — memo agreement gate handles it; version-aware keys are
  the refinement if sub-90% entries ever matter.
- Memo v2 harvested from full ground truth: 62 plans, median
  agreement 1.000; deployed (MEMO_VERSION=2).

**Corpus learning is DONE. Final Richard ask: Rheia price sheet +
equipment costs + one heat-strip one-liner.**
