# Known failing tests (backend)

Snapshot 2026-09-03. `pytest tests/` shows **5 failures + 1 skip** on a
clean local tree; all 5 are pre-existing and NOT regressions from
recent work. Documented here so a red suite doesn't get re-investigated
from scratch every time. None block deploys (CI/prod behavior is
unaffected — see each entry).

## Skipped (expected, not a failure)

- **`test_pdf_service.py`** (whole module) — skips locally because
  WeasyPrint needs system libs (GTK/pango) not present on dev machines,
  and other test modules stub `weasyprint` into `sys.modules` with a
  mock. The module now detects the stub and skips cleanly (fixed
  2026-09-03; was 7 noisy failures). **Runs normally in CI/prod** where
  the real library is installed.

## Real failures needing domain ground truth (do NOT "fix" by editing assertions)

These four all read the **79th Ct / Trane edge-case fixtures** and the
parser now returns 2-3× the counts the tests assert (e.g. DTYPREF
ShtMetl 44 vs expected 24; VinlFlx 64 vs 20). The pattern says the
local fixture `.rup` was swapped for a different/larger file at some
point — the assertions encode the ORIGINAL file's ground truth.
Resolving needs confirming the correct 79th Ct fixture with Richard;
79th Ct is the labeled P99 outlier ("do not generalize"), so silently
matching the test to current parser output could mask a real parser
issue. Left red on purpose until the fixture is confirmed.

- `test_duct_summary.py::test_dtypref_type_counts_for_79th_ct`
- `test_rup_pipeline.py::test_parser_enumerates_all_eight_ahus`
- `test_equipment_model_extraction.py::test_parser_surfaces_trane_air_handler_model`
- `test_equipment_model_extraction.py::test_parser_preserves_ahu_naming_pattern`

## Cross-file test pollution (passes in isolation)

- **`test_catalog_match.py::TestPromptGrounding::test_call_ai_for_quantities_passes_through_claimed_lines`**
  — PASSES when run alone; fails only in the full suite, so some other
  module leaves global/monkeypatch state behind. A test-isolation fix
  (proper fixture teardown), not a product bug. Low priority.

## How to run green locally

    pytest tests/ --deselect tests/test_duct_summary.py::test_dtypref_type_counts_for_79th_ct \
      --deselect tests/test_rup_pipeline.py::test_parser_enumerates_all_eight_ahus \
      --deselect tests/test_equipment_model_extraction.py::test_parser_surfaces_trane_air_handler_model \
      --deselect tests/test_equipment_model_extraction.py::test_parser_preserves_ahu_naming_pattern \
      --deselect "tests/test_catalog_match.py::TestPromptGrounding::test_call_ai_for_quantities_passes_through_claimed_lines"
