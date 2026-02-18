# HANDOFF — START HERE
## Written by Claude Opus 4.6 on February 18, 2026 (Session 2)
## For the next Claude chat continuing this project

---

## WHO YOU ARE
You are continuing work on ProCalcs HVAC Software, Phase 1: Load Calc Validator.
Tom is the creative director. You are the architect and builder. Tom is NOT a coder.
Product name: **ProCalcs** — this is the brand for everything.

## READ THESE FILES FIRST (in this order)
1. D:\ProCalcs_HVAC_Software\PROJECT_RULES.md — The law. Read Rule 8 carefully.
2. D:\ProCalcs_HVAC_Software\docs\business\Build_Plan_v2.docx — The master plan.
3. D:\ProCalcs_HVAC_Software\shared\plan_reading_guide\PLAN_READING_GUIDE.md — How to read architectural plans.
4. D:\ProCalcs_HVAC_Software\changelog\ — Read all changelogs, newest first.

## WHAT WAS COMPLETED

### Session 1 (Feb 17-18): Plan Reading & Project Setup
- Project folder structure at D:\ProCalcs_HVAC_Software\
- 12 Project Rules established
- Plan Reading Guide written (teaches AI how to read architectural floor plans)
- PDF readability testing on 5 real plans — TWO methods proven:
  - Method 1: AutoCAD SHX annotation extraction (works on CAD PDFs with embedded text)
  - Method 3: High-DPI tiling at 300 DPI + AI vision with Plan Reading Guide loaded
- Tested Opus 4.6 on GT Bray plan with tiling + guide — got CORRECT conditioned sqft
- Determined 4 of 5 test plans need AI vision (only Del Rio had extractable annotations)
- Decision: Python checks PDF type first, extracts what it can, ALWAYS tiles for AI vision

### Session 2 (Feb 18): Wrightsoft Analysis & Strategic Decisions
- Wrightsoft Right-Suite Universal v25.0.05 installed and analyzed
- Mapped all three installation directories (see Wrightsoft section below)
- Discovered and cataloged key databases and file formats
- Confirmed: contractors submit PDF reports, NOT .rup files — PDF is what the Validator must parse
- Decision: Build ProCalcs as API-first architecture from day one
- Product name confirmed: ProCalcs (one brand across all phases)

## WRIGHTSOFT INSTALLATION ANALYSIS

### Installation Paths
- Program Files: C:\Program Files (x86)\Wrightsoft HVAC\ (application, DLLs, templates, demos)
- Program Data: C:\ProgramData\Wrightsoft HVAC\ (databases, weather data, construction data)
- Working Dir: C:\Users\<username>\OneDrive\Documents\Wrightsoft HVAC\ (user projects)

### Key Databases Found
1. **Construction.mdb** (7.7 MB) — Building materials database
   - 4 tables: Material (88 entries), Opaque, Fenestration, Info
   - Material table has: Name, Description, Type, Conductivity, Density, Specific Heat, R-value
   - Includes all standard materials: fiberglass batts, foam boards, concrete types, siding, roofing
   - Fenestration table has U-factors and SHGC values for windows/doors
   - Accessible via pyodbc with Microsoft Access Driver
   - **USE FOR VALIDATOR:** Cross-check Manual J material inputs against industry standard values

2. **arigama2.mdb** (942 MB) — AHRI certified equipment database
   - Complete manufacturer equipment data (every rated HVAC unit)
   - Updated to January 5, 2026 AHRI data
   - **USE FOR PHASE 2+:** Equipment selection validation (Manual S)

3. **Weather/Climate Data** — Hundreds of .et1 files
   - Organized by state: FL_Tampa.et1, FL_Miami.et1, GA_Atlanta.et1, etc.
   - Binary format based on TMY2/TMY3 data with lat/long, design temps, hourly data
   - Also has TMY3 versions: USA_FL_Miami.Intl.AP.722020_TMY3.et1
   - **USE FOR VALIDATOR:** Verify correct design temperatures for project location

### .rup/.rud File Format
- Binary with text markers: !BEG=SECTIONNAME / !END=SECTIONNAME
- Header: .WS.rsu.WSF.0004 with APP=, VRSN=, SN=, TIMESTAMP= fields
- Key sections found in Windsor Calculation Verification.rup (7,447 total sections):
  - COMPONTY (266) — construction type descriptions in plain text
  - SURFACE (280) — wall/ceiling/floor surfaces with references
  - WALLINFO/WALLSURF/GLAZSURF — wall and glazing surface data
  - DUCTLOCMJ8/DUCTRUNMJ8 — duct locations for Manual J
  - SYSTEM/EQUIP — HVAC system and equipment data
  - CConsMat/CConsLayer/CConstruction — construction material assemblies
- Gerald's rup_parser.py (252 lines) already parses this format
- NOTE: .rup is the WORKING file, not what contractors submit

### Template Files
- default.rut, defaultBase.rut, defaultMJ7.rut, Canada Air AC-Gas.rut
- Same !BEG/!END format as .rup files
- Contains default construction assemblies, equipment presets, schedules

### Demo Projects (20+ files)
- C:\Program Files (x86)\Wrightsoft HVAC\Demo\
- ExACCA.rud — ACCA standard example
- Windsor Calculation Verification.rup — verification example with comparison PDF
- Various duct, equipment, and radiant examples

### Wrightsoft Competitive Weaknesses (from designer feedback + analysis)
- Ancient architecture: Access databases, binary formats, Qt widgets
- Can't open multiple projects simultaneously
- No global construction updates (must change per floor)
- No API, no web version, no integration capability
- Supply/return grille linking requires manual updates
- Limited to 8 building orientations (should be 16)
- Desktop-only, single machine license

## STRATEGIC DECISIONS MADE THIS SESSION

### 1. API-First Architecture
- ProCalcs will be built as an API with a web UI on top (not a website with an API bolted on)
- Reason: Tom wants HVAC companies to connect ProCalcs to their own dashboards
- The Validator engine IS the API. The website is just one client.
- Phase 4 revenue stream: API access subscriptions for integrators
- Gerald should build the backend as a proper API from day one
- This costs nothing extra now but prevents a rewrite later

### 2. Product Name: ProCalcs
- One brand for everything: Validator, full engine, API, SaaS
- Already trusted in the HVAC industry
- Clean, memorable, says exactly what it does
- Works across all phases without renaming

### 3. Contractor Submission Format: PDF
- Contractors submit the Wrightsoft PDF output report, NOT .rup files
- .rup is the internal working file — contractors don't share it
- The Validator MUST extract Manual J data from PDF reports
- This is the next critical puzzle to solve (see "What Is Next" below)

## WHAT IS NEXT

### Immediate Priority: Read a Wrightsoft PDF Report
Tom is providing a sample Wrightsoft PDF output report — the actual document a
contractor would submit for validation. Drop it in:
D:\ProCalcs_HVAC_Software\phase1_validator\tests\

Once we have it, we need to:
1. Study the PDF layout — what fields, what format, how data is organized
2. Test extraction methods — can we get text directly, or need AI vision?
3. Map every data point to what the Validator needs to cross-check
4. Compare against the Construction.mdb reference data we found

### Then: Design the Phase 1 Validator Workflow Spec
The validator workflow (from Build Plan):
1. Document Upload — contractor uploads Manual J PDF + architectural plans
2. AI Extraction — parse R-values, window specs, sqft, orientation, ducts, infiltration
3. Review & Confirm — user sees extracted data with gaps highlighted
4. What-If Playground — real-time recalculation as users adjust values
5. Confidence Scoring — green/yellow/red per calculation element

We solved reading architectural plans for sqft (Plan Reading Guide + AI vision).
We need to solve reading Manual J PDF reports (the calculations being validated).
Then we can write the full workflow spec.

## REFERENCE CODE
D:\ProCalcs_HVAC_Software\phase1_validator\reference_code\ contains:
- gemini_estimate.py — 1,633 lines, old Gemini-based estimator (REFERENCE ONLY)
- api.py — 3,017 lines, Gerald's API (REFERENCE ONLY)
- rup_parser.py — 252 lines, Wrightsoft file parser
- project_analyzer.py — 315 lines
- streaming_analyzer.py — 263 lines

## HVAC REFERENCE DATA
- D:\ProCalcs_HVAC_Software\shared\hvac_tables\ — Manual J lookup tables
- D:\ProCalcs_HVAC_Software\shared\reference_data\ — 15 HVAC knowledge files
- D:\ProCalcs_HVAC_Software\docs\reference\ — Developer docs from Gerald

## TEST PLANS (5 real architectural plans)
D:\ProCalcs_HVAC_Software\phase1_validator\tests\
- GT Bray floor plan.pdf — Commercial renovation, vector paths, NO extractable text
- Del Rio Residence - Arch Set - 2026-1-15.pdf — Residential new, HAS SHX annotations
- 13 Five Star Bldg- Progress Drawing v6.0 for HVAC Design 01-19-26.pdf — No text
- 251216 Plan A1.1.pdf — No text
- Stone_Addition.pdf — No text

## CRITICAL REMINDERS
- Read Rule 8: Do NOT create files or write code unless Tom says "Proceed"
- Tom is not a coder. Speak plain English.
- Check what exists before creating anything new.
- The Build Plan docx requires python-docx to read (use Desktop Commander).
- Construction.mdb is readable via pyodbc with MS Access Driver.
