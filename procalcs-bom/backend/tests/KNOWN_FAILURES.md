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
parser returns 2-3× the counts the tests assert (DTYPREF ShtMetl 44 vs
expected 24; VinlFlx 64 vs 20; RectFbg 12 vs 4).

**Investigated 2026-09-16 — NOT a fixture swap** (earlier hypothesis,
now ruled out): all three local 79th Ct files
(`79th Ct Residence Load Calcs.rup`, the `+BOM` variant, and the
`(Edge Case)` variant) parse to the SAME 44/64/12. So the parser
reads consistently; it's the test's original expected values (24/20/4)
that disagree.

**Hypotheses ruled out (2026-09-16 investigation):**
1. NOT a fixture swap — all three local 79th Ct files parse identically
   to 44/64/12.
2. NOT a global string double-find — `extract_utf16_strings` has only a
   0.7% consecutive-identical rate across the whole file (676/102286).
3. NOT fixable by consecutive-dedup — collapsing consecutive-identical
   DTYPREF entries yields {ShtMetl:2, VinlFlx:13, RectFbg:12}=27, which
   matches neither the raw 44/64/12 nor the expected 24/20/4. Those
   consecutive-identical entries are mostly legitimate same-type runs,
   not extraction artifacts.

So the relationship between the parser's 44/64/12 and the test's
original 24/20/4 is genuinely unresolved from the code side. Resolving
needs **Richard's actual 79th Ct duct-run count** OR a hand audit of
the binary DTYPREF section (what does each entry encode, and why 120?).
79th Ct is the labeled P99 outlier ("do not generalize"), so do NOT
silently match the test to current parser output — 44/64/12 could be a
real over-count that would also inflate the synthetic DUCT-* rows on
unbuilt files. Left red on purpose until confirmed with Richard.

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
