# HANDOFF — START HERE
## Last Updated: April 7, 2026 by Claude Sonnet 4.6
## For the next Claude chat continuing this project

---

## WHO YOU ARE
You are continuing work on ProCalcs HVAC Software. **ROADMAP HAS CHANGED — READ THIS CAREFULLY.**

**Phase 1 (current build target): AI-Powered BOM with Contractor Intelligence Profiles**
The Validator has been deprioritized. It is a distant project. The BOM is what we are building first.
See: docs\ideas\AI_Powered_BOM_Contractor_Profiles.md — full concept document.

Tom is the creative director. You are the architect and builder. Tom is NOT a coder.

## PROJECT LOCATIONS
- **Primary (Windows):** D:\ProCalcs_HVAC_Software\
- **Google Drive Mirror:** G:\My Drive\Claude Projects\ProCalcs_Software\
- **Master Ideas File:** G:\My Drive\MASTER_IDEAS.md (add new ideas here)

## READ THESE FILES FIRST (in this order)
1. This file (HANDOFF.md)
2. PROJECT_RULES.md — The law. Read Rule 8 carefully.
3. docs\Build_Plan_v2.docx — The master plan.
4. shared\plan_reading_guide\PLAN_READING_GUIDE.md — How to read architectural plans.
5. changelog\ — Read ALL changelogs in date order for full history.
6. phase1_validator\design\wrightsoft_pdf_analysis.md — How Wrightsoft PDFs work.
7. docs\acca\Protocol_MJ8_Ver_250_Software_Review-2026.pdf — ACCA's official review protocol.

## WHAT HAS BEEN COMPLETED
1. Project folder structure created (4 phases)
2. 12 Project Rules established
3. Plan Reading Guide written (teaches AI to read architectural floor plans)
4. PDF readability testing — two methods proven:
   - Method 1: AutoCAD SHX annotation extraction (CAD PDFs with embedded text)
   - Method 3: High-DPI tiling at 300 DPI + AI vision with Plan Reading Guide
5. Wrightsoft fully reverse-engineered (databases, file formats, competitive weaknesses)
6. API-first architecture decision locked in
7. Confirmed contractors submit PDFs, not .rup files
8. ACCA Protocol analyzed — costs, process, timeline documented
9. DOE Common Engine intel gathered (see below)

## CRITICAL STRATEGIC INTEL (March 2, 2026)

### DOE Common Calculation Engine
ACCA is working with DOE to build a shared Manual J calculation engine.
- Expected launch: 2028
- Software companies would plug in their own front-end/experience layer
- Software companies still welcome to submit own engines for ACCA review
- STRATEGIC IMPACT: Do NOT build our own calc engine yet. Build the experience layer.

### ACCA Licensing Costs
- $10,000 non-refundable review fee
- $15,000/year licensing (5% annual increase)
- 5-year commitment: ~$83,000 total
- At $600/year pricing: need 25 subscribers just to break even on ACCA fee
- Wrightsoft charges $500-$1,500/year — they spread costs across thousands of users

### New ACCA Requirements (coming soon, not yet in formal docs)
- Software must output ACCA's Plan Review Form
- Software must output composite J1 Form + Worksheet A
- Must provide open license for ACCA staff use

### Strategic Decision
- Phase 1: Validator FIRST (no ACCA approval needed, pure margin from day one)
- Phase 2: Build the EXPERIENCE layer (AI visualization, conversational reviewer, smart data collection)
- Phase 3: When DOE engine launches (~2028), plug it in and apply for ACCA approval
- Revenue from Validator funds everything without the $83K ACCA anchor

## WHAT IS NEXT
1. **Design the Phase 1 Validator workflow spec** — This is a DESIGN DOCUMENT, not code.
2. **Build the Wrightsoft PDF parser** — Extract Manual J data from contractor-submitted PDFs
3. **Design the comparison engine** — How plan measurements get compared to report values
4. **Define confidence scoring** — What thresholds trigger green/yellow/red flags
5. **Test with Scott Residence** as first validation case (PDF in phase1_validator\tests\)

## THREE CONTRACTOR MANIPULATION POINTS THE VALIDATOR CATCHES
1. Inflated square footage (claiming rooms are bigger than plans show)
2. Wrong construction values (using better insulation R-values than actually installed)
3. Equipment oversizing (selecting larger units than the load calculation supports)

## TEAM
- **Tom** — Creative Director, HVAC logic, business strategy
- **Claude** — Architect, system design, documentation
- **Gerald** — Developer (part-time, Claude Desktop issues, jury still out)
- **Catherine** — CEO, ACCA liaison, business operations
- **Two Filipino developers** — Being sourced, $800-1,500/mo + commission

## CONTACT AT ACCA
Wesley R. Davis, Director of Technical Services
wes.davis@acca.org | (703) 824-8847
