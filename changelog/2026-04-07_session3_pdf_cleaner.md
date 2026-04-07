# 2026-04-07 — Session 3: PDF Cleaner Built + BOM Spec Updated

## What Was Built

### procalcs-pdf-cleaner — Full backend and frontend scaffolded

**Backend:**
- Flask app factory with centralized config, startup validation
- Health check endpoint (`/health`)
- Cleaner route (`POST /api/v1/tools/pdf-to-cad`) — file upload, validation, cleanup, download
- `cleaner_service.py` — Core ezdxf engine: reads DXF, classifies every entity, strips junk,
  preserves geometry + filtered INSERTs, writes clean output
- `insert_filter.py` — Smart INSERT Filter with keyword-based block classification.
  Keeps doors and ventilation appliances (range hoods, dryers). Strips furniture,
  electrical, plumbing. Unknown blocks default to KEEP (Richard's rule).
- `validators.py` — Upload validation (extension, file size)
- DWG pipeline stubbed — ready for ODA File Converter integration

**Tests (29 test cases):**
- `conftest.py` — Realistic sample DXF fixture with walls, doors, text, dimensions,
  hatch, furniture, electrical, plumbing, ventilation appliances, unknown blocks
- `test_insert_filter.py` (11 tests) — Keyword classification, case insensitivity,
  ambiguous defaults, empty inputs, stats builder
- `test_cleaner.py` (10 tests) — Full engine: geometry preserved, text/dims/hatch stripped,
  door and appliance blocks kept, furniture/plumbing stripped, unknown kept, stats returned
- `test_validators.py` (8 tests) — Valid/invalid extensions, no file, oversized, case handling

**Frontend:**
- React + Vite setup matching procalcs-bom pattern
- `CleanerPage` — Upload → process → auto-download flow
- `FileDropZone` — Drag-and-drop + click-to-browse, extension validation
- `StatusMessage` — Loading spinner, error state, success with "Clean Another" button
- `apiFetch.js` — Upload with AbortController timeout, blob download, filename extraction
- ProCalcs dark theme (amber/gold on dark navy)

### PDF-to-CAD Cleanup Tool spec updated with Richard's feedback
- Interior doors: KEEP (INSERT blocks, not just ARC geometry)
- Appliances: KEEP range hoods and dryers (ventilation provision)
- New "Smart INSERT Filter" section added to spec
- New "Full Designer Workflow" section — CAD layer stays ON during loads/duct design
- Wrightsoft performance context added — cleanup is mandatory because WS chokes on clutter

## Key Decisions

- **Richard's Rule:** When INSERT block classification is unknown, KEEP it.
  Designer can delete an extra block in seconds. Losing a needed door costs rework.
- **Block name matching is primary strategy.** Geometry analysis is Phase 1.5.
- **CAD layer stays ON during loads and duct design** — designers need to see actual plans.
  Only turned off temporarily for pure Wrightsoft drawing work.
- **Non-ventilation appliances stripped.** Fridge, dishwasher, microwave — gone.
  Only range hoods and dryers kept because they tie to exhaust/makeup air.

## Repo Structure

```
procalcs-pdf-cleaner/
├── backend/
│   ├── app.py, config.py, __init__.py
│   ├── routes/ (health_routes.py, cleaner_routes.py)
│   ├── services/ (cleaner_service.py, insert_filter.py)
│   ├── utils/ (validators.py)
│   ├── tests/ (conftest.py, test_cleaner.py, test_insert_filter.py, test_validators.py)
│   └── requirements.txt
├── frontend/
│   ├── src/ (App, CleanerPage, FileDropZone, StatusMessage, apiFetch, global.css)
│   ├── package.json, vite.config.js, index.html
├── test_fixtures/ (.gitkeep)
├── .env.example, .gitignore, pytest.ini, README.md
```

## What's Next
- Get sample DWG files from designers to test against real-world data
- Install ODA File Converter and wire up DWG→DXF→clean→DXF→DWG pipeline
- Gerald: review code, run tests, set up local dev environment

## Requested By
Tom
