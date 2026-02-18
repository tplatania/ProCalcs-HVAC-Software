# Wrightsoft PDF Report Analysis
## Scott Residence Load Calcs - First Sample Report
### Date: 2026-02-18 | Session 3

---

## KEY FINDINGS

### 1. PDF Text Extraction = EXCELLENT
The Wrightsoft PDF exported clean, extractable text. No OCR or vision needed.
This is a HUGE win — it means our validator can use simple text parsing for
Wrightsoft reports, not expensive AI vision calls.

### 2. Report Structure (50 pages total)
The PDF contains these report sections in order:

| Pages | Report Type | What It Contains |
|-------|------------|-----------------|
| 1-2 | Manual S Compliance | Equipment sizing verification (AHU 1 & 2) |
| 3-4 | Building Analysis | Heating/cooling component breakdown by % |
| 5-11 | Load Short Form | Room-by-room loads with sq footage totals |
| 12-15 | Component Constructions | Wall/window/door/ceiling specs with U-values |
| 16-17 | Project Summary | Design conditions + equipment + ventilation |
| 18-43 | Right-J Worksheets | Detailed room-by-room calculation worksheets |
| 44-48 | Duct System Summary | Manual D duct sizing (AHU 1 & 2) |
| 49-50 | Static Pressure & Friction | Duct system pressure calculations |

### 3. Data Points Available for Validation

#### Phase 1 Priority (Conditioned Square Footage)
- **AHU 1 Total Area: 2,682 sq ft** (Page 5-6)
- **AHU 2 Total Area: 4,806 sq ft** (Page 7)
  - Zone 2A: 1,735 sq ft
  - Zone 2B: 3,072 sq ft
- **Combined Total: 7,488 sq ft**
- Individual room areas listed with names

#### Room-Level Detail Available
Each room has: Name, Area (sq ft), Htg Load (Btuh), Clg Load (Btuh),
Htg AVF (cfm), Clg AVF (cfm)

#### Equipment Data
- Manufacturer: Bosch Thermotechnology Corp.
- Model: BOVA-60RTB-M20S + BIVA-60RCB-M20X
- Both AHUs use identical 5-ton Bosch heat pumps
- AHRI ref: 214771733

#### Design Conditions
- Location: Asheville 8 Ssw, NC, US
- Heating outdoor: 17°F / Indoor: 70°F
- Cooling outdoor: 84°F / Indoor: 75°F
- Infiltration: Blower door method, 3.0 ACH @ 50 Pa
- Ventilation: ASHRAE 62.2-2010

#### Construction Details
- Walls: Frame 2x6, R-19 (U=0.064)
- Windows: Double Pane, Low-E, Aluminum (U=0.290, SHGC=0.24)
- Ceilings: Encapsulated Tile Roof, R-38
- Floors: Various (crawlspace R-10, ambient R-19, garage R-19, slab R-10)
- Basement walls: R-10

### 4. Validation Cross-Check Opportunities

#### Tier 1 - Square Footage (Phase 1 focus)
- Report lists room areas → compare to plan measurements
- Sum of room areas should equal AHU total
- AHU totals should equal whole-house total

#### Tier 2 - Design Conditions
- Weather station selection → verify against address
- Indoor design temps → verify against standards
- Infiltration method/values → check reasonableness

#### Tier 3 - Construction Inputs
- Wall R-values → verify against code requirements
- Window specs → cross-check with plan schedules
- Floor types → verify against plan foundation details

#### Tier 4 - Equipment Sizing
- Manual S percentages (should be 90-115% for sensible)
- AHU 1 cooling: 108% sensible ✓, 113% total ✓
- AHU 2 cooling: 115% sensible ✓, 124% total (high but within range)
- AHU 2 heating: 74% (needs supplemental heat) — flaggable

### 5. Parsing Strategy
The text is well-structured with consistent patterns:
- Headers clearly identify section type and AHU number
- Room data appears in fixed-width table format
- Key values (loads, areas, equipment) have consistent labels
- "Calculations approved by ACCA" appears as a validation marker

## WRIGHTSOFT FEEDBACK (from contractor)
### Dislikes:
- Can't open multiple projects simultaneously
- Can't copy equipment selections between similar AHUs
- Manual N (commercial) performance tab broken
- Encapsulated attic setup issues
- Only 8 building orientations (wants 16)
- Supply-to-return grille linking is manual and error-prone
- Global construction updates are labor-intensive (per-floor only)

### Likes:
- Room drawing makes setup easy vs manual input
- Auto equipment selection (Manual S)
- Pre-loaded ASHRAE climate data
- Integrated duct design with auto TEL calculation
- Ceiling tool handles complex ceiling geometry

## NEXT STEPS
1. Build PDF text parser for Wrightsoft Load Short Form section
2. Extract room names and areas into structured data
3. Design comparison engine: plan areas vs report areas
4. Define confidence scoring thresholds
5. Test with Scott Residence as first validation case
