# Corpus analysis pipeline — Reliable RUP + BOM archive

Four-stage pipeline over the synced Zoho corpus
(`~/Procalcs/RUPs-from-zoho/`). Run in order; each stage consumes the
previous stage's JSON. All stages are incremental/idempotent — safe to
re-run as new files land from the sync.

```
corpus_analyzer.py    →  corpus_summary.json, corpus_aggregates.json
pair_analyzer.py      →  pair_analysis.json   (rup ↔ BOM xls joins)
profile_extractor.py  →  reliable_profile_draft.json + summary.md
qa_aggregator.py      →  qa_aggregate.json + .md  (questions for Richard)
```

## What each stage does

1. **corpus_analyzer** — structural parse of every `.rup` (RPITEM
   priced lines, EQUIP placements, BALDUCT register CFMs, duct
   segments). Uses the parsers in procalcs-bom `backend/utils/`.
2. **pair_analyzer** — matches each `.rup` to its BOM `.xls` by
   folder/stem affinity, parses the xls, aggregates SKU prices,
   sources, and appearance frequencies across matched pairs.
3. **profile_extractor** — derives the contractor-profile draft:
   brand tiers, ubiquitous equipment, fitting kit, catalog gaps.
4. **qa_aggregator** — collapses ~13 questions/file into one
   profile-level question set (dedup by category+SKU), ranked by
   priority. Designed so Richard answers each rule ONCE.

## Interpretation warning (2026-07-14 lesson)

BOM `.xls` files exist **only for Rheia projects** — the company does
not produce BOMs for standard projects (that's the BOM module's whole
purpose). Any "X% of matched projects use RHEA" style finding is
selection bias, not supplier preference. `.rup` files *without* a
paired BOM are (mostly) the standard projects — the actual target
population for generated BOMs.
