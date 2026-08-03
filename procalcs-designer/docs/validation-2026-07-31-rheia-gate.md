# Validation artifact — day-31 Rheia gate separation (2026-07-31)

**Status: corpus-based supporting evidence.** The separation result
(50 known-Rheia pairs max 7 vs five built conventional projects
min 37) is measured against the private corpus and local ground-truth
files, which cannot be reproduced from GitHub. The independently
reproducible coverage is the synthetic suite
(`procalcs-bom/backend/tests/test_day31_gate_and_preflight.py`); this
artifact supports the *choice* of threshold, not the gate's logic.

Committed run log of
`scripts/corpus-analysis/validate_day28_engine_fixes.py` (extended per
Tom's 2026-07-31 review to check **every** local conventional
ground-truth project, not just SW 55th). The corpus and project `.rup`
files cannot live in the repo, so this log is the reviewable artifact;
the script reproduces it on any machine with the local corpus.

## Environment

- Engine: `procalcs-bom` @ the day-31 gate
  (`CONV_DUCT_FAMILIES` ×17, `CONV_SKU_THRESHOLD` = 15)
- Known-Rheia population: first 50 built pairs from
  `full-corpus-run-2026-07-15/pairs.jsonl` against the 12-community
  Zoho corpus
- Conventional population: the six local ground-truth projects
  (SW 55th, Jappeloup, Irvine, Enos, 79th Ct built, Clarke)

## Output (verbatim, exit 0)

```
  ⏭️  'Enos Residence Load Calcs.rup' has no Wrightsoft-built BOM (unbuilt — gate not applicable, skipped)
  ✅ SW55 conventional: 0 Rheia lines
  ✅ SW55 conventional: 0 phantom ERV
  ✅ SW55 flex DDVn04 summed to 126 (49+77)
  ✅ SW55 flex DDVn05 summed to 109
  ✅ T075 Rheia: takeoff intact (>0 lines)
  ✅ known-Rheia max duct-system SKUs < 15 (n=50, max=7)
  ✅ conventional 'SW 55th Ave Residence_duct2.rup' duct-system SKUs >= 15 (got 96)
  ✅ conventional 'Jappeloup Lane Residence_duct.rup' duct-system SKUs >= 15 (got 69)
  ✅ conventional '1257 Irvine Rd Residence.rup' duct-system SKUs >= 15 (got 37)
  ✅ conventional '79th Ct Residence Load Calcs+BOM.rup' duct-system SKUs >= 15 (got 99)
  ✅ conventional 'Clarke Residence Load Calcs.rup' duct-system SKUs >= 15 (got 52)
  ✅ conventional min across 5 projects = 37 (threshold 15, Rheia max 7)
```

## Reading it

- **Known-Rheia side:** 50 built pairs, maximum 7 distinct
  conventional-family SKUs. Threshold 15 → margin 8.
- **Conventional side:** 5 built local projects, minimum 37.
  Margin 22. (Enos is unbuilt — no RPITEM priced BOM — so the gate
  never evaluates it; unbuilt files take the synthetic path.)
- **Melko caveat (honest scope):** the "conventional min 27" quoted in
  earlier reports was measured from Melko's *stored run* SKU listing
  during the day-31 calibration; Melko's raw `.rup` is not in the
  local ground-truth set, so it does not appear in this artifact. Its
  fresh re-upload re-measures it end-to-end — that is acceptance
  criterion 3 in `docs/melko-acceptance-criteria.md`. Even at 27 the
  margin above threshold is 12.
- Synthetic unit coverage of the same threshold, the DREGINFO
  auto/user decode, malformed records, and regeneration carry-forward:
  `procalcs-bom/backend/tests/test_day31_gate_and_preflight.py`
  (13 tests, no corpus dependency).
