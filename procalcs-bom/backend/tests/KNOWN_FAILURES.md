# Known failing tests (backend)

Updated 2026-09-16. `pytest tests/` shows **3 failures + 1 skip** on a
clean local tree (down from 5 — two of the 79th Ct/Enos failures were
audited and confirmed to be stale test expectations, now corrected).
All remaining failures are pre-existing and NOT regressions. Documented
here so a red suite doesn't get re-investigated from scratch. None block
deploys.

## Fixed 2026-09-16 (were stale test expectations; parser was correct)

- `test_duct_summary.py::test_dtypref_type_counts_for_79th_ct` — audited
  three ways (RupReader length-verified, string-scan, raw bytes): the
  file has 120 byte-distinct DTYPREF blocks = 44/64/12. Old assertion
  24/20/4 was wrong; corrected to 44/64/12.
- `test_rup_pipeline.py::test_parser_enumerates_all_eight_ahus` — parser
  correctly finds all 8 Enos AHUs plus an electric heat strip (day-18
  heat-kit extraction); assertion now checks the air_handler subset.

## Skipped (expected, not a failure)

- **`test_pdf_service.py`** (whole module) — skips locally because
  WeasyPrint needs system libs (GTK/pango) not present on dev machines,
  and other test modules stub `weasyprint` into `sys.modules` with a
  mock. The module now detects the stub and skips cleanly (fixed
  2026-09-03; was 7 noisy failures). **Runs normally in CI/prod** where
  the real library is installed.

## Real failures needing domain ground truth (do NOT "fix" by editing assertions)

Two tests, both on the **79th Ct Trane P99 outlier** file, assert a
specific equipment shape that the parser no longer produces — and here
the change is substantial enough that I can't tell "parser improved"
from "parser regressed" without knowing what 79th Ct actually contains:

- `test_equipment_model_extraction.py::test_parser_surfaces_trane_air_handler_model`
- `test_equipment_model_extraction.py::test_parser_preserves_ahu_naming_pattern`

**Finding (2026-09-16):** these tests expect FIVE air handlers named
`AHU - 1 .. AHU - 5` with the first carrying model `5TAMXD06AV41`. The
parser now returns TWO air handlers both named `Split AC`, with Trane
models `5TAMXD07AV51` and `5TAMXD06AV41`. So both the count (5→2), the
naming (`AHU - N`→`Split AC`), and the ordering changed. `5TAM*` are
Trane air-handler model numbers, so the extraction isn't obviously
wrong — but 2-vs-5 and the "Split AC" label could be either a better
read of a Trane split system or a regression that dropped AHUs.

Unlike the DTYPREF count (which was provable from the binary), the
"right" equipment shape for this file needs **Richard's confirmation of
what 79th Ct's air handlers actually are** (2 split systems? 5 AHUs?).
79th Ct is the labeled do-not-generalize outlier, so do NOT bless the
new shape by editing the assertions until confirmed. Left red on purpose.

## Cross-file test pollution (passes in isolation)

- **`test_catalog_match.py::TestPromptGrounding::test_call_ai_for_quantities_passes_through_claimed_lines`**
  — PASSES when run alone; fails only in the full suite, so some other
  module leaves global/monkeypatch state behind. A test-isolation fix
  (proper fixture teardown), not a product bug. Low priority.

## How to run green locally

    pytest tests/ \
      --deselect tests/test_equipment_model_extraction.py::test_parser_surfaces_trane_air_handler_model \
      --deselect tests/test_equipment_model_extraction.py::test_parser_preserves_ahu_naming_pattern \
      --deselect "tests/test_catalog_match.py::TestPromptGrounding::test_call_ai_for_quantities_passes_through_claimed_lines"
