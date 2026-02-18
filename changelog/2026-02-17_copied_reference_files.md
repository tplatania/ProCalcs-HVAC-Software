# 2026-02-17 — Copied Reference Files from GitHub Repo

## What
Pulled relevant files from Gerald's ProCalcs_Design_Process GitHub repo into our project.
Source: https://github.com/tplatania/ProCalcs_Design_Process.git
GitHub repo was NOT modified — read-only copies only.

## Files Copied

### phase1_validator/reference_code/ (code to study & borrow from)
- gemini_estimate.py (1,633 lines — OVER 700 limit, needs breakdown)
- api.py (3,017 lines — OVER 700 limit, reference only)
- project_analyzer.py (314 lines)
- streaming_analyzer.py (263 lines)
- rup_parser.py (251 lines)

### shared/hvac_tables/
- manual_j_load_calculations.json

### shared/reference_data/
- manual_s_reference.json
- rheia_checklist.json
- summary_form_fields.json

### docs/reference/ (15 HVAC knowledge files)
- All hvac_knowledge/*.json files (diagnostics, manufacturers, regional, etc.)
- CHANGES_REQUESTED.md
- DEVELOPER_BUG_FIXES.md

## Why
These files contain the document reading pipeline, Wrightsoft parser, HVAC reference data,
and AI vision logic we'll adapt for the Phase 1 Validator.

## Next Step
Break down gemini_estimate.py into clean files under 700 lines each.

## Requested By
Tom
