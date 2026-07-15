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
