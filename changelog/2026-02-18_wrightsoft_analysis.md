# Changelog: Wrightsoft Analysis & Strategic Decisions
## Date: February 18, 2026 (Session 2)
## Author: Claude Opus 4.6

---

## What Happened
Analyzed the installed Wrightsoft Right-Suite Universal v25.0.05 to understand
the competitor's data structures, file formats, and capabilities. Made three
key strategic decisions for ProCalcs architecture.

## Wrightsoft Analysis Summary

### Databases Discovered
- **Construction.mdb** — 88 building materials with R-values, conductivity,
  density, specific heat. 4 tables: Material, Opaque, Fenestration, Info.
  Readable via pyodbc. Will use as reference data for the Validator.
- **arigama2.mdb** — 942MB AHRI equipment database. Every certified HVAC unit.
  Updated Jan 2026. Useful for Phase 2+ equipment validation.
- **Weather .et1 files** — Hundreds of climate files by city, TMY2/TMY3 format.

### .rup File Format Mapped
- Binary with !BEG=/!END= text section markers
- 7,447 sections in a typical project file
- Key sections: COMPONTY (construction descriptions), SURFACE, WALLINFO,
  GLAZSURF, DUCTLOCMJ8, SYSTEM, EQUIP, CConsMat
- Gerald's rup_parser.py already handles this format

### Competitive Assessment
Wrightsoft is powerful but architecturally stuck in the 2000s. No API, no web
version, no multi-project, no global updates. Desktop-only Access databases.
ProCalcs opportunity is clear: modern, API-first, AI-powered.

## Strategic Decisions

### 1. API-First Architecture
Tom wants HVAC companies to connect ProCalcs from their own dashboards.
The engine will be built as an API first, with the web UI as one client.
This is a Phase 4 revenue stream (API subscriptions) that costs nothing
extra if architected correctly from Phase 1.

### 2. Product Name: ProCalcs
One brand across all phases. Already trusted in the industry.

### 3. PDF is the Submission Format
Contractors submit Wrightsoft PDF output reports, NOT .rup working files.
The Validator must extract Manual J data from PDFs. This is the next
critical problem to solve — Tom is providing a sample PDF.

## Files Changed
- Updated HANDOFF.md with all findings and decisions
- Created this changelog

## Next Steps
- Tom providing sample Wrightsoft PDF report
- Analyze the PDF to determine extraction approach
- Design the Phase 1 Validator workflow spec
