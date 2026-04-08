# .rup File Upload for BOM Input
### Gerald Developer Handoff | Status: SPEC READY
### April 8, 2026

---

## The Problem

The current BOM input is a JSON textarea where design data gets pasted manually.
Nobody is going to write JSON by hand in production. All the design data already
lives in the Wrightsoft `.rup` project file that designers save to the project
folder for every single job.

## The Solution

Replace the JSON textarea with a `.rup` file upload. The parser extracts
everything the BOM engine needs — duct runs, fittings, equipment, rooms,
construction values — and feeds it directly to the AI BOM generator.

**Designer flow:** Finish design in Wrightsoft → save `.rup` (already doing this)
→ upload to ProCalcs BOM → parser extracts everything → BOM generated.
Zero manual data entry.

---

## What Already Exists

### rup_parser.py (251 lines)
Location: `phase1_validator/reference_code/rup_parser.py`

This parser already reads `.rup` binary files and extracts:
- **Header:** Software version, timestamp
- **Project info:** Address, client name
- **Location/Weather:** Weather station, state
- **Rooms:** Room names (BEDROOM, KITCHEN, LIVING, etc.) — up to 30
- **Equipment:** Model numbers, tonnage, SEER ratings, CFM values
- **Construction:** R-values, U-factors
- **Raw sections:** Lists all BEG=/END= section markers in the file

### .rup File Format (what we already know)
- Binary file, UTF-16-LE encoded
- Uses `BEG=SECTIONNAME` / `END=SECTIONNAME` markers
- 7,447 sections in a typical project file
- Key sections for BOM:
  - `EQUIP` — Equipment selection (model, capacity, AHRI ref)
  - `DUCTLOCMJ8` — Duct location and configuration
  - `SYSTEM` — System type and zoning
  - `COMPONTY` — Construction descriptions
  - `SURFACE` — Building surfaces with areas
  - `WALLINFO` — Wall details
  - `GLAZSURF` — Window/glass surfaces

---

## What Gerald Needs To Build

### 1. Enhanced .rup Parser — Extract BOM-Specific Data

The existing parser gets header/rooms/equipment basics. For BOM generation,
we need deeper extraction from these specific sections:

**Duct data (from DUCTLOCMJ8 and related sections):**
- Duct runs: size (e.g., 12x8), length in linear feet, material (flex/rigid)
- Supply and return trunk sizes
- Duct location (attic, crawlspace, conditioned space)

**Fittings (from duct design sections):**
- Elbows (45°, 90°), tees, reducers, transitions
- Quantities per fitting type

**Equipment (from EQUIP section):**
- Air handler model, outdoor unit model
- AHRI reference number
- Capacity (Btuh heating/cooling)
- Tonnage, SEER/SEER2, HSPF

**Registers/Grilles (from room/duct assignments):**
- Size per room (e.g., 4x12, 6x10)
- Supply vs return
- Room assignment

**Building info (from header + construction sections):**
- Building type (single level, two story, etc.)
- Square footage
- Number of systems/zones

### 2. Frontend — Replace JSON Textarea With File Upload

On the Generate AI BOM page, replace the "DESIGN DATA (JSON)" textarea with:
- A file upload drop zone (same pattern as PDF-to-CAD page)
- Accept `.rup` files only
- On upload: send to backend, parse, show extracted summary to designer
- Designer confirms the extraction looks right, then hits Generate BOM
- Keep the JSON textarea as a hidden "Advanced" toggle for dev/testing

### 3. API Endpoint

`POST /api/v1/bom/parse-rup`

**Input:** Multipart file upload (.rup file)

**Output:**
```json
{
  "success": true,
  "data": {
    "project": { "address": "...", "client": "..." },
    "building": { "type": "single_level", "sqft": 2400 },
    "equipment": [
      { "type": "air_handler", "model": "Carrier FB4C", "tonnage": "3.0" }
    ],
    "duct_runs": [
      { "id": "duct-1", "size": "12x8", "length_lf": 45, "material": "flex" }
    ],
    "fittings": [
      { "type": "elbow-90", "quantity": 4 }
    ],
    "registers": [
      { "location": "bedroom-1", "size": "4x12", "type": "supply" }
    ]
  }
}
```

This JSON output is the same schema the BOM engine already expects —
it just comes from the parser instead of manual entry.

---

## Two Approaches — Gerald's Choice

### Approach A: Direct Binary Parse (recommended)
Extend `rup_parser.py` to extract BOM-specific sections directly from
the binary. Faster, no dependencies, no Wrightsoft needed on server.
The parser already handles UTF-16-LE decoding and section markers.

**Pro:** No external dependencies, fast, works anywhere
**Con:** Binary format is undocumented — extraction is regex/pattern-based

### Approach B: PDF Export + Parse (Gerald's initial idea)
Open .rup in Wrightsoft → export PDF reports → parse with pdfplumber →
feed to Claude with HVAC domain prompt → get structured JSON.

**Pro:** Wrightsoft does the hard work of interpreting the binary
**Con:** Requires Wrightsoft installed, adds manual export step,
PDF parsing is lossy, extra AI call adds cost and latency

### Hybrid Option
Use Approach A for everything the binary parser can extract reliably.
Fall back to Approach B only for data that's too deeply buried in
the binary format. Gerald can decide based on what he finds.

---

## Test Files

Scott Residence .rup file was tested during development. Path in the
original parser: `G:\My Drive\Claude Projects\ProCalcs_Design_Process\
Test_Project\1901 Loch Berry\`

Designers save .rup files for every project — any project folder has one.

---

## Acceptance Criteria

1. Designer uploads a .rup file — no other input needed
2. Parser extracts duct runs, equipment, fittings, registers, building info
3. Extracted data shown to designer for confirmation before BOM generation
4. Same BOM output quality as current JSON input method
5. JSON textarea still available as hidden Advanced mode for testing
6. Handles corrupt/incompatible .rup files gracefully with clear error

---

*Spec written: April 8, 2026*
*Source: Tom + Claude session — Gerald requested spec*
*Owner: Gerald Villaran*
