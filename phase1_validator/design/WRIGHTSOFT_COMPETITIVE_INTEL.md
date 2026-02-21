# Wrightsoft Right-Suite Universal — Competitive Intelligence Reference

## Purpose
This document captures everything learned from examining Wrightsoft Right-Suite Universal 2025 (v25.0.05) as a licensed user. ProCalcs owns 13 Wrightsoft licenses. This reference exists so future AI sessions can understand Wrightsoft's architecture, strengths, weaknesses, and how ProCalcs validators should interpret Wrightsoft-generated reports.

---

## Software Architecture

### Core Design
- **RSU.EXE**: Single 68MB monolithic executable (version 25.0.05, dated 2026-01-23)
- **Platform**: Windows only, 32-bit (installed in Program Files x86)
- **Data storage**: Microsoft Access .mdb databases (legacy format)
- **Project files**: .rup format (proprietary binary)
- **No API access** — everything runs through the desktop GUI
- **Cannot open multiple projects simultaneously**
- **Cloud features**: Limited — WCloudBrowser.dll.config points to wrightsoft cloud services for license management and Right-Catalog updates

### Installation Paths
- Program: `C:\Program Files (x86)\Wrightsoft HVAC\`
- Data: `C:\ProgramData\Wrightsoft HVAC\Data\`
- Projects: `C:\Documents and Settings\{username}\My Documents\Wrightsoft HVAC\`

### Key Technology Claims
- **Hotlink Technology**: Change in one area updates all connected modules automatically
- **Layered Materials Technology (LMT)**: Build construction assemblies component-by-component; single description translates across different calculation methods
- **HVAC Shapes**: Smart drag-and-drop objects that store properties (dimensions, materials, orientation)
- **Right-Catalog**: Auto-updating equipment database via internet

---

## Modules (Each Sold Separately)

| Module | Function |
|--------|----------|
| Right-Draw | Drag-and-drop graphical floor plan entry |
| Right-J | ACCA Manual J 7th or 8th Edition residential loads |
| Right-F280 | HRAI F280 (Canada) |
| Right-CommLoad | Commercial loads (ASHRAE RTS and 24-hour CLTD) |
| Right-D | ACCA Manual D duct design |
| Right-Duct | HRAI duct design (Canada) |
| Right-CommDuct | ASHRAE duct method |
| Right-HV | High-velocity duct design |
| Right-2Line | CAD-quality residential two-line duct drawing |
| Right-Comm2Line | CAD-quality commercial two-line duct drawing |
| Right-Radiant | Radiant panel loop design |
| Right-Loop | Residential geothermal loop calculations |
| Right-Proposal | Custom proposals, automatic parts takeoff, BOM |
| Right-Sales | In-home selling presentation and management tools |
| Right-$ | System comparison and operating cost analysis |
| Right-N | ACCA Manual N (standalone only) |
| Right-Rheia | Rheia radiant duct system design (bolt-on, not separate module) |
| Right-Energy | Title 24 (CA), Florida Code compliance |

---

## Databases

### AHRI Equipment Database (arigama2.mdb)
Updated via Right-Catalog. AHRI data effective 2026-01-05, database version 2017.091.

| Table | Records | What It Contains |
|-------|---------|-----------------|
| AC | 2,531,880 | Air conditioner outdoor/indoor unit combinations |
| HP | 756,907 | Heat pump combinations |
| FURNACE | 23,602 | Gas/oil/electric furnaces |
| BOILER | 1,298 | Hot water and steam boilers |
| GSHP | 4,456 | Ground-source heat pumps |
| GWHP | 4,382 | Ground-water heat pumps |
| WaterHeater | 6,735 | Water heaters |
| ACCoils | 5,661 | AC evaporator coil models |
| HPCoils | 2,018 | HP evaporator coil models |
| AHCoilMatch | 55,085 | Air handler to coil matching |
| Collector | 250 | Solar collectors |
| Family | 931 | Equipment family groupings |
| CLGMFR | 384 | Cooling manufacturer codes to names |
| HTGMFR | 384 | Heating manufacturer codes to names |

**Key columns in HP table** (representative of AC as well):
Manufacturer (4-char code), Condenser Model, Coil Model, AH Model, Capacity (Btuh), SEER, HSPF, EER95, High Capacity, Low Capacity, High COP, Low COP, Classification, Trade Name, Sound Level, ARI RefNo, Stages, DOE compliance flag

**Key columns in FURNACE table**:
Manufacturer, Model, Input, Output, AFUE, Classification, Trade Name, Fuel, Stages, Input_LS, Output_LS, EAE, PE, EF, GAMA ID, LoNoxOpt

**Equipment classifications found:**
- AC: RCU-A-C, RCU-A-CB, SP-A, SPY-A, SCP-RCU-A-CB, and numeric codes
- HP: HRCU-A-CB (most common, includes Scott Residence unit), HSP-A, HMSR-A-CB, HORC-A-C, etc.
- Furnace: U (upflow), D (downflow), H (horizontal), combinations with N (non-weatherized), V (variable)
- Boiler: I (indoor), O (outdoor)

**Stage distribution:**
- AC: 91% single-stage, 7% two-stage, <1% variable
- HP: 81% single-stage, 15% two-stage, <1% variable

**IMPORTANT**: All AHRI equipment data is PUBLIC. The AHRI Directory (ahridirectory.org) is the authoritative free source. ProCalcs should verify equipment against AHRI's public directory, not a static copy. Wrightsoft just packages this public data into their Access database.

### Construction Database (Construction.mdb)

| Table | Records | What It Contains |
|-------|---------|-----------------|
| Opaque | 15,203 | Wall, ceiling, floor assemblies with R-values |
| Fenestration | 1,867 | Window/door entries with U-factors and SHGC |
| Material | 88 | Base construction materials with conductivity, density, R-values |

**Opaque type codes**: W (wall), C (ceiling), F (floor), D (door)
**Opaque methods**: Multiple methods supported for same assembly
**Fenestration methods**: 7, 8, 8N, F, N

**Key columns in Opaque**: TypeCode, Method, MS_CST (construction string), MS_UHtg (heating U-value), MS_UHtgBG (below-grade heating U-value)
**Key columns in Fenestration**: Method, MS_CST, MS_UHtg, MS_UHtg_SW, MS_SHGC

**The 88 base materials** include conductivity (Cond), density (Dens), specific heat (SpHt), resistance (Res), and thickness (Thkns). These are ASHRAE Fundamentals published values. Examples: empty cavity (R-1.02), air gap (R-0.80), various attic types (vented, unvented, with/without radiant barrier), insulation types, framing materials, sheathing, etc.

**Custom Construction Builder**: Users can build custom wall/ceiling/floor assemblies layer-by-layer using these 88 base materials. This is the "Layered Materials Technology." Known issue: conflicting values between standard Manual J 8th edition lookup tables and actual calculated R/U values for the same assembly. This is a frustration point for contractors.

### Other Databases

| Database | Status | Contents |
|----------|--------|----------|
| Weather6.mdb | PASSWORD PROTECTED | Weather data for all locations |
| xeqp2.mdb | PASSWORD PROTECTED | Extended equipment data |
| xwhp2.mdb | INCOMPATIBLE FORMAT | Older format, could not open |
| crm.mdb | Empty (template) | CRM for customer/project tracking |
| GWizuWSF.mdb | Full | 13 wizards, 125 questions, 61 answers — project setup flow |
| RPRUWSF.mdb | Full | Reports/proposals: 38,757 parts, 1,035 ductfree units, templates |

### Weather Files
- Format: `.et1` (proprietary packed format, mixed text/binary header with binary data)
- Sources: TMY2 (1995), TMY3 (2008), ASHRAE 2013/2017/2021
- Header contains: station ID, lat/long, timezone, elevation, design temps
- Hundreds of station files covering US and Canada
- California: 16 EPW climate zone files for Title 24

---

## Load Calculation Workflow (from Quick Guide)

The complete contractor workflow in Wrightsoft:

### 1. Setup
- Create project from template or wizard
- Contractor info, customer info, project location
- Select weather data (design conditions)
- Set fuel costs
- Select building type and construction materials
- Set infiltration method (Simplified, Detailed, or Blower Door)

### 2. Drawing (Right-Draw)
- Set scale, grid, snap settings
- Set orientation (compass direction of North — critical for solar loads)
- Draw rooms using HVAC Shapes (stores dimensions automatically)
- Add windows, doors, skylights to rooms
- Set wall heights, ceiling types (vaulted, cathedral, flat)
- Custom floors, walkout basements
- Each object has a Property Sheet with all parameters

### 3. Load Calculation
- Select method: Manual J 7th, Manual J 8th, F280, RTS, CLTD
- Load Preferences screen sets global parameters
- Internal gains: occupants (bedrooms + 1), appliances (Btuh per room)
- Ventilation: ASHRAE 62.2 (2010, 2016, or 2019 version)
- View results: worksheet, load meter, or zone information screen

### 4. Equipment Selection
- Equipment Selection screen with tabs per system type
- "Auto Select" checkbox restricts to properly sized equipment (**contractors can uncheck this**)
- Pull from AHRI/GAMA database (Right-Catalog)
- Generic equipment available for cost analysis
- Fan data entry on equipment tabs

### 5. Zoning
- Multizone Tree for assigning rooms to zones/equipment
- Drag rooms between zones
- Visual zone display on floor plan (color-coded)
- Multiple air handlers supported

### 6. Duct Design
- Duct Preferences: materials, sizes, register shapes
- Automatic layouts: Radial, X-axis, Y-axis, Plenum, User-defined
- Manual design: draw supply/return trunks and branches
- Flex duct support with edit points
- Risers between floors
- Two-line CAD quality (Right-2Line module)
- High-velocity system option (Right-HV)

### 7. Reports and Proposals
- Report packages: groups of reports for different audiences
- Print Preview with PDF export
- Proposal document editor (built-in word processor)
- Variables auto-fill from project data
- Proposal blocks (boilerplate text)
- Bill of materials with automatic parts takeoff
- Parts mapping: generic Wrightsoft parts → actual manufacturer parts

---

## Where Contractors Can Manipulate Inputs

These are the specific places where a contractor can game the system to justify oversized equipment. This is ProCalcs' entire reason for existing:

### Design Conditions
- Selecting extreme weather locations (hotter/colder than actual site)
- Using outdated weather data (older ASHRAE years may have different design temps)

### Building Envelope
- Selecting worse insulation than actually installed (inflates load)
- Wrong window types (higher U-factor = more heat transfer = bigger load)
- Wrong window SHGC (higher = more solar gain = bigger cooling load)
- Conflicting values from custom vs. standard construction libraries

### Infiltration
- Using "Simplified" method with "Semi-Loose" or "Loose" when house is actually tight
- Not using Blower Door results even when available
- Overriding calculated values

### Internal Gains
- Inflating occupant count
- Inflating appliance loads

### Orientation
- Setting worst-case orientation instead of actual (maximizes solar loads)
- Double-clicking compass center forces worst-case automatically

### Equipment Selection
- Unchecking "Auto Select" to pick oversized equipment
- Using equipment that doesn't match the load
- Mismatching indoor/outdoor units (wrong AHRI combination)

### Ventilation
- Overriding ventilation values (F8 override key changes blue brackets to yellow)
- Using older ASHRAE 62.2 version with different requirements

### Duct Design
- Claiming duct location in conditioned space when actually in attic
- Underestimating duct leakage

---

## Rheia Integration

Rheia is NOT a core module — it's a surface-level bolt-on:
- Activated via "Rheia System" checkbox on Equipment screen
- Changes duct design to home-run/manifold layout instead of trunk-and-branch
- Only a 6-page supplement PDF documents it
- Zero mentions in 1,624 help files
- No separate DLLs, databases, or executables
- Designs export to separate "Rheia Portal" web platform
- Template requirements: "Split intersected ducts" OFF, 3" snap grid

**ProCalcs implication**: Manual J load calculation is identical regardless of duct system type. The validator works the same whether the house uses Rheia, traditional ducts, or ductless mini-splits. Rheia partnership would be a separate product line, not a load validation feature.

---

## California Title 24 / Energy Compliance

Wrightsoft has deep Title 24 integration:
- CA22RES (2022 standards) and CA25RES (2025 standards) directories
- CBECC-Res integration (California Building Energy Code Compliance)
- CSE.exe simulation engine
- BEMProc DLL (Building Energy Model processor)
- 16 climate zone weather files (EPW format)
- CAR25 Screens.txt: 1.5MB of UI/field definitions (8,696 lines)
- CM_Rules Input Data Model: 2,428 property definitions
- Supports Florida 2014/2017/2020/2023, IECC 2006

**ProCalcs opportunity**: Title 24 compliance is a separate market from Manual J validation but uses the same building data. Future module potential.

---

## Competitive Weaknesses

1. **No API** — cannot integrate with anything programmatically
2. **Cannot open multiple projects** simultaneously
3. **Legacy Access databases** — .mdb format from the 1990s
4. **32-bit application** running in compatibility mode
5. **Help system is 100% video** — zero searchable text documentation
6. **Conflicting R/U values** between Manual J 8 standard tables and custom LMT builder
7. **Custom construction builder is difficult to use** — contractor frustration point
8. **No verification layer** — generates reports but nobody verifies inputs
9. **Desktop-only** — no web, no mobile, no cloud processing
10. **Single-user per license** — no team collaboration

---

## Competitive Strengths (Why They're #1)

1. **20+ years of incremental development** — covers every edge case
2. **ACCA strategic partner** in US, **HRAI** in Canada
3. **Comprehensive module suite** — loads, ducts, radiant, geothermal, proposals, sales
4. **AHRI equipment database** with automatic updates (3.3M+ combinations)
5. **15,203 construction assemblies** pre-built and ready to use
6. **CAD import/export** capability
7. **Built-in proposal system** — contractors can generate customer-facing documents
8. **Title 24, Florida Code, Energy Star** compliance built in
9. **Right-Draw** graphical interface — visual, not just spreadsheet
10. **Brand recognition** — "Wrightsoft" is synonymous with load calcs in the industry

---

## What ProCalcs Has Saved (in this repo)

### Actual Data Files
- `wrightsoft_database_export.json` — Full 88 material records, schemas for all tables, sample records, all manufacturer codes, classifications, stage distributions, wizard Q&A
- `wrightsoft_features_export.json` — Template list, demo projects, help file index, report templates

### Documentation PDFs
- Quick Guide (88 pages — complete workflow reference)
- User Manual, Examples Manual
- Rheia, DuctFree, Florida Energy supplements
- HVAC Design Report fillable template
- Windsor Verification, F280 Canada notes
- Energy Star ERI examples

### Data Models
- CA25 Screens (complete Title 24 UI definitions)
- CM Input Data Model (all compliance property definitions)
- CM Simulation Data Model
- 15-year release history

---

## Verified Equipment Example (Scott Residence)

Queried AHRI database for exact equipment match:
- **AHRI Reference**: 214771733
- **Condenser**: BOVA-60RTB-M20S
- **Coil**: BIVA-60RCB-M20X
- **Manufacturer**: BOSC (Bosch Thermotechnology Corp.)
- **Capacity**: 52,000 Btuh
- **SEER**: 18.0 | **HSPF**: 9.5 | **EER95**: 11.7
- **High Capacity**: 55,000 Btuh | **Low Capacity**: 44,000 Btuh
- **Classification**: HRCU-A-CB
- **Stages**: 1 | **DOE Compliant**: Yes

This matched perfectly with our Wrightsoft parser extraction from the Scott Residence PDF, confirming the end-to-end validation chain works: PDF → Parser → AHRI lookup → Verified.

---

## Key Insight for ProCalcs

Wrightsoft (and all ACCA-approved software) performs calculations correctly. The math is right. The problem is INPUTS. Contractors can manipulate weather data, construction types, infiltration methods, orientation, and equipment selection to justify whatever size system they want to sell.

ProCalcs doesn't need to redo the math. ProCalcs needs to verify the inputs make sense for the actual building. That's the gap nobody else fills.

---

*Last updated: February 21, 2026*
*Source: Licensed examination of Right-Suite Universal v25.0.05*
