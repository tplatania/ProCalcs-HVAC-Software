# ACCA Manual J, S & D — AI Training Guide
## ProCalcs HVAC Software — Validator Knowledge Base
### Created: February 19, 2026 | Source: ACCA Standards & Published Technical Resources

---

## OVERVIEW: HOW THE THREE MANUALS WORK TOGETHER

The ACCA manuals form a chain. Each one feeds the next. Break any link and the whole
system fails. This is the sequence every properly designed residential HVAC system follows:

**Manual J → Manual S → Manual D**

1. **Manual J** (Load Calculation): Answers "How much heating and cooling does this house need?"
2. **Manual S** (Equipment Selection): Answers "What equipment satisfies those loads?"
3. **Manual D** (Duct Design): Answers "How do we deliver the right airflow to every room?"

A fourth manual, **Manual T** (Air Distribution), handles register and grille selection.
ProCalcs Phase 1 focuses on validating Manual J, with awareness of S and D for context.

---

## PART 1: MANUAL J — RESIDENTIAL LOAD CALCULATION (8th Edition)

### What It Is
Manual J 8th Edition (MJ8) is the ANSI-recognized national standard (ANSI/ACCA 2)
for calculating residential heating and cooling loads. It is required by the International
Residential Code (IRC) and most state/local building codes. Developed by Hank Rutkowski
and maintained by ACCA.

### What It Calculates
Manual J determines two things for every room and the whole house:
- **Heating Load (Heat Loss)**: BTU/h the house loses in winter at design conditions
- **Cooling Load (Heat Gain)**: BTU/h the house gains in summer at design conditions

These are PEAK loads at design conditions, not average loads.

### The Four Sources of Heat Loss and Gain

Every Manual J calculation accounts for four categories of thermal transfer:

**1. Conduction (through the building envelope) — ~75% of heat loss**
Heat moves through walls, ceilings, floors, windows, and doors. The rate depends on:
- Surface area (sq ft) of each component
- U-value (thermal transmittance) of the assembly — lower = better insulation
- Temperature difference (delta-T) between indoor and outdoor design temps
- Formula: Q = U x A x delta-T (BTU/h)

The building envelope includes every surface separating conditioned space from
unconditioned space or outdoors. This means exterior walls, ceilings below attics,
floors over crawlspaces or garages, basement walls, and all fenestration (windows/doors).

**2. Infiltration (uncontrolled air leakage) — ~25% of heat loss**
Outside air leaks through cracks, gaps, and openings in the envelope. Driven by:
- Wind pressure on the building
- Stack effect (warm air rises, pulls cold air in at the bottom)
- Mechanical imbalances (supply vs. return duct pressure differences)

Infiltration is measured or estimated using:
- **Blower door test**: Pressurizes house to 50 Pa, measures ACH50 (air changes per hour
  at 50 Pascals), then converts to natural infiltration rate at design conditions
- **Manual J Table 5A/5B estimates**: If no blower door test, classify as Tight, Semi-Tight,
  Average, Semi-Loose, or Loose based on construction practices

Infiltration can account for 25-40% of heating and cooling loads. A blower door test
yields the most accurate results. Guessing infiltration is one of the top two reasons
heat pumps get sized incorrectly.

**3. Ventilation (controlled outside air)**
Fresh air intentionally brought into the house per ASHRAE 62.2 requirements. This adds
both sensible (temperature) and latent (moisture) load. Methods include:
- Exhaust-only ventilation (bath fans)
- Supply ventilation (outside air duct to return)
- Balanced ventilation (HRV or ERV systems — these reduce the ventilation load)

**4. Internal Gains (heat generated inside the house)**
Heat produced by people, appliances, and lighting. Manual J uses standardized values:
- People: Based on number of bedrooms + 1 (NOT actual occupant count)
- Appliances: Default block load values per Manual J tables
- Lighting: Included in appliance block load

CRITICAL: Contractors should NOT inflate internal gains. Adding too many people or
wrong appliance loads is a common mistake that artificially increases cooling load.

### Required Inputs for a Manual J Calculation

Every Manual J requires these categories of input data:

**A. Design Conditions (Climate)**
- Outdoor design temperatures from ASHRAE/Manual J Table 1A/1B
  - Heating: 99% design temp (cold enough 99% of the hours in a year)
  - Cooling: 1% design temp (hot enough only 1% of the hours — about 88 hours)
- Indoor design temperatures (typically 70F heating, 75F cooling)
- Daily temperature range (Low, Medium, High) — affects thermal mass cooling credits
- Grains difference (moisture content difference indoor vs outdoor)
- Elevation and latitude of project location

RULE: You CANNOT mix Manual J Table 1A/1B data with ASHRAE data in the same project.
Pick one source and use it consistently.

RULE: Do NOT design for record-breaking weather extremes. Design temps are based on
30-year statistical averages. Sizing for extremes leads to gross oversizing.

**B. Building Envelope (Construction)**
For every surface separating conditioned from unconditioned space:
- Walls: Construction type (frame 2x4, 2x6, CMU, ICF, SIP), insulation R-value,
  exterior finish, interior finish, framing factor
- Ceilings/Roofs: Type (vented attic, cathedral, encapsulated), insulation R-value,
  radiant barrier presence
- Floors: Type (slab-on-grade, crawlspace, basement, over garage), insulation R-value
- Windows: U-factor, SHGC (Solar Heat Gain Coefficient), frame type, glass type,
  internal shading (blinds/drapes), external shading (overhangs/screens)
- Doors: Type, U-factor, glass percentage

Each component gets a Construction Number from Manual J tables that determines its
Heating Transfer Multiplier (HTM). The HTM times the area gives the load for that surface.

**C. Room-by-Room Measurements**
- Conditioned floor area for each room (sq ft)
- Ceiling height for each room
- Net wall area per orientation (gross wall minus window/door area)
- Window area per orientation, type, and shading
- Door area per orientation and type
- Exposed floor area and type
- Ceiling area and type

CRITICAL: Conditioned area means ONLY heated/cooled spaces. Garages, unconditioned
basements, unconditioned attics, and porches are NOT included. Getting this wrong is
a fundamental error.

**D. Building Orientation**
- Direction the front of the house faces
- Wrightsoft offers 8 orientations; ACCA ideally wants 16 for accuracy
- Orientation matters enormously for solar gain — south-facing windows can have
  3-4x the solar load of north-facing windows

**E. Infiltration / Air Leakage**
- Blower door test results (ACH50 and CFM50) — preferred method
- Or estimated tightness category (Tight/Semi-Tight/Average/Semi-Loose/Loose)
- Number of stories (affects stack effect)
- Wind shielding class (Category 1-5, from exposed to fully shielded)
- Number and type of fireplaces
- Combustion appliance types (sealed combustion vs. atmospheric)

**F. Ventilation Requirements**
- Method: ASHRAE 62.2 is the standard
- Type: Exhaust-only, supply, balanced (HRV/ERV)
- Rate: Based on floor area and number of bedrooms
- ERV/HRV efficiency (if applicable — reduces ventilation load)

**G. Duct System**
- Duct location: conditioned space, unconditioned attic, crawlspace, basement
- Duct insulation R-value
- Duct leakage: tested (preferred) or estimated
- CRITICAL: Ducts in conditioned space have much lower duct loads than ducts in
  an unconditioned attic. Getting this wrong inflates the load significantly.

### Manual J Output — What the Report Produces

A complete Manual J report provides:

**Room-by-Room Results:**
- Room name and conditioned area (sq ft)
- Heating load (BTU/h) per room
- Cooling sensible load (BTU/h) per room
- Cooling latent load (BTU/h) per room
- Cooling total load (sensible + latent) per room
- Required airflow (CFM) per room for heating and cooling

**Whole-House / System Totals:**
- Total heating load (BTU/h) for each AHU/system
- Total cooling sensible load (BTU/h)
- Total cooling latent load (BTU/h)
- Total cooling load (BTU/h)
- Sensible Heat Ratio (SHR) = sensible / total cooling
- Required blower CFM
- Duct load contribution

**Design Documentation:**
- Design conditions used (outdoor/indoor temps, humidity)
- Construction specifications for all envelope components
- Infiltration method and values
- Ventilation method and rates
- AED (Adequate Exposure Diversity) indication — required since 2016 edition
- ACCA software approval stamp ("Calculations approved by ACCA")

### Block Load vs. Room-by-Room

Manual J supports two calculation modes:
- **Block Load**: Calculates whole-house total only. Useful for quick sizing but
  does NOT provide room-level data needed for duct design.
- **Room-by-Room**: Calculates loads for each individual room. Required for
  proper duct design (Manual D) and register selection (Manual T).

ProCalcs will validate room-by-room calculations since these are required for
a complete HVAC design and are what Wrightsoft produces.

### The 19 Don'ts of Manual J (from ACCA)

These are ACCA's own published rules for what NOT to do. Every one of these is
something ProCalcs should flag as a potential problem:

1. Do NOT use Manual J on buildings it wasn't designed for (commercial, high-rise
   multifamily, indoor pools, earth-berm structures, passive solar homes)
2. Do NOT use the Abridged edition for homes with non-standard features (NFRC glass,
   large glass areas, atriums, excessive internal loads, heat recovery systems)
3. Do NOT design for record-breaking weather extremes
4. Do NOT add safety factors to weather data — ASHRAE data is already statistically valid
5. Do NOT design for abnormally high heating or low cooling indoor temperatures
6. Do NOT use incorrect outdoor design conditions for the project location
7. Do NOT ignore local construction practices when selecting insulation values
8. Do NOT use gross wall area — must subtract window and door openings (use NET area)
9. Do NOT ignore the effect of building orientation on solar gain
10. Do NOT guess at window specifications — use NFRC-rated U-factor and SHGC
11. Do NOT inflate occupant count — use bedrooms + 1, not actual people
12. Do NOT use wrong appliance block load amounts
13. Do NOT guess at infiltration — use blower door test data when available
14. Do NOT ignore duct location — ducts in conditioned space vs. unconditioned attic
    makes a massive difference
15. Do NOT fail to credit properly sealed and insulated ductwork
16. Do NOT apply a safety factor at ANY stage of the calculation
17. Do NOT apply a safety factor to the final answer — Manual J loads are peak
    estimates and have been tested against actual buildings
18. Do NOT mix ASHRAE and Manual J Table 1A/1B weather data sources
19. Do NOT ignore the Adequate Exposure Diversity (AED) requirement

KEY INSIGHT FOR PROCALCS: "Even when you're as stingy as possible with things that
add load, you still end up oversized by 10-15%. So there's no need to add extra load."
— ACCA HVAC Blog (Dr. Allison Bailes)

### Common Contractor Mistakes the Validator Should Catch

Based on ACCA published guidance and DOE studies, these are the most frequent errors:

**Sizing Without Calculations:**
- "Manual E" (eyeball method) — looking at a house and guessing tonnage
- "Square-foot-by-ton" — using 400-600 sq ft per ton rule of thumb
- Studies show slightly less than half of contractors do comprehensive load calcs

**Input Manipulation (Padding the Load):**
- Using design temperatures more extreme than ASHRAE tables specify
- Selecting "Loose" infiltration when construction is actually "Average" or better
- Inflating window areas or using worse U-factors than actual windows
- Adding more people than the bedrooms + 1 standard
- Putting ducts in "unconditioned attic" when they're actually in conditioned space
- Stacking multiple small "safety factors" that compound into massive oversizing

**Why Oversizing Is Bad (ProCalcs should educate contractors on this):**
- Short cycling: System turns on/off too frequently, never reaching efficiency
- Poor dehumidification: System doesn't run long enough to remove moisture
- Temperature swings: Rapid cooling creates 5-7F variations instead of steady comfort
- Higher equipment costs: Paying $2,000-5,000 extra for unnecessary capacity
- Increased wear: 40% more mechanical stress from frequent cycling
- Shorter equipment life: 2-5 years less than properly sized systems
- 15-30% higher energy consumption

**Data from ACCA: The actual sq ft per ton from 40 proper Manual J calculations in
hot and mixed climates averaged 1,431 sf/ton — ranging from 624 to 3,325 sf/ton.
This is 2-3x higher than the 400-600 sf/ton rule of thumb contractors commonly use.**

---

## PART 2: MANUAL S — RESIDENTIAL EQUIPMENT SELECTION

### What It Is
Manual S (ANSI/ACCA 3) is the national standard for selecting and sizing residential
heating and cooling equipment. It takes the loads from Manual J and matches them to
real equipment using OEM (Original Equipment Manufacturer) expanded performance data.

### Why It Matters
Manual S exists because you can't just pick equipment by matching the Manual J load
to an AHRI certificate. AHRI certification data is tested at specific conditions
(80F indoor, 95F outdoor) that almost never match your actual design conditions.
Manual S requires using OEM expanded performance data that shows capacity at YOUR
project's specific design conditions.

### The Manual S Equipment Sizing Rules

**Cooling Equipment (Air Conditioners):**
- Sensible cooling capacity must be >= 100% of Manual J sensible cooling load
- Total cooling capacity must be between 95-115% of Manual J total cooling load
- Or the next nominal size available to satisfy latent and sensible requirements

**Heat Pump Cooling:**
- Cooling-dominant climate: Total cooling capacity 100-115% of total cooling load
- Heating-dominant climate: Total cooling capacity 100-125% of total cooling load
- The larger allowance in heating-dominant climates lets you size up slightly
  to cover more of the heating load with the heat pump

**Heating Equipment (Furnaces, Boilers):**
- Output heating capacity must be between 100-140% of Manual J heating load
- Or the next nominal size available

**Heat Pump Heating:**
- For fixed-speed: Heat pump may not cover 100% of heating load at design conditions.
  This is normal — supplemental electric heat strips make up the difference.
  The "balance point" is where heat pump capacity equals the heating load.
- For variable-capacity: New Manual S (2022) allows sizing heat pumps to fully
  cover heating when following specific rules using OEM min/max capacity data.

### The Four Steps of Manual S (Cooling Equipment Selection)

1. **Set Design Parameters**: Use the SAME temperature and humidity conditions
   from the Manual J calculation. Pull sensible load, latent load, total load.
   
2. **Estimate Target Airflow**: Use the home's Sensible Heat Ratio (SHR) to
   calculate target CFM. SHR = sensible cooling / total cooling.
   - High SHR (dry climate): Higher airflow, more sensible capacity
   - Low SHR (humid climate): Lower airflow, more latent capacity (dehumidification)
   
3. **Search for Equipment Candidates**: Find MATCHED systems (AHRI-certified
   combinations of outdoor unit + indoor unit + coil) that deliver adequate
   capacity at YOUR design conditions using OEM expanded performance tables.
   
4. **Evaluate and Select**: Verify the candidate meets all sizing limits.
   Multiple candidates may be acceptable — offer options to the customer.

### What Manual S Provides to Manual D
Manual S determines two critical values that feed into duct design:
- **Design airflow (CFM)**: How much air the blower must move
- **Temperature rise requirement**: For heating mode — the difference between
  return air temp and supply air temp through the furnace/heat pump

### ProCalcs Validation Points for Manual S
The validator can check:
- Equipment capacity percentages against Manual J loads (the 95-115%, 100-140% rules)
- Whether OEM data was used (not just AHRI certificate values)
- Whether the system is a matched AHRI-certified combination
- Whether supplemental heat is specified when heat pump heating falls short
- Whether sensible cooling capacity meets or exceeds the sensible load
  (this is often the binding constraint, not total capacity)

---

## PART 3: MANUAL D — RESIDENTIAL DUCT DESIGN

### What It Is
Manual D (ANSI/ACCA 1) is the standard for designing residential duct systems.
It ensures the right amount of conditioned air reaches every room without
excessive noise, energy waste, or comfort problems.

### The Five Steps of Manual D Duct Design

**Step 1: Determine External Static Pressure (ESP)**
From the manufacturer's blower performance data, find the total external static
pressure at the design CFM. This is the blower's total pressure budget.

**Step 2: Sum Component Pressure Losses (CPL)**
Subtract pressure drops from components in the airstream:
- Evaporator coil (typically 0.15-0.30 IWC)
- Air filter (typically 0.05-0.15 IWC depending on type)
- Supply registers and grilles (typically 0.03 IWC each)
- Return grilles (typically 0.03 IWC)
- Heat strips, humidifiers, dampers, etc.

**Step 3: Calculate Available Static Pressure (ASP)**
ASP = ESP - Total CPL
This is what's left for the duct system itself.
Example: 0.6 IWC (ESP) - 0.25 (coil) - 0.10 (filter) - 0.05 (accessories) = 0.20 IWC

**Step 4: Determine Total Effective Length (TEL)**
Measure the longest supply duct run + longest return duct run + equivalent lengths
of all fittings (elbows, tees, transitions). Each fitting adds equivalent feet:
- 90-degree elbow: ~20 equivalent feet
- Tee: ~35 equivalent feet
- Transition: varies

**Step 5: Calculate Friction Rate and Size Ducts**
Friction Rate = (ASP x 100) / TEL
This gives IWC per 100 feet of duct.

ACCA Rule: Friction rate MUST fall between 0.06 and 0.18 IWC per 100 feet
(inside "the wedge" on the Manual D chart).
- Below 0.06: Ducts are oversized (low velocity, wasted space/material)
- Above 0.18: Inadequate fan performance, noisy, poor airflow

Use the friction rate with a duct calculator (ductulator) to size each run:
- Set friction rate
- Set required CFM for the room (from Manual J)
- Read the required duct diameter or equivalent rectangular size

### Key Manual D Concepts

**Airflow Requirements:**
- Cooling: Typically 400 CFM per ton of cooling capacity
- Below 350 CFM/ton: Coil may freeze, reduced capacity
- Above 450 CFM/ton: Poor dehumidification in humid climates

**Static Pressure Budget:**
- Most residential systems work best at or below 0.6 IWC total
- Higher static = lower airflow = reduced capacity and efficiency
- For ECM motors: Avoid operating in top 1/3 of pressure range

**Return Air:**
- Returns are chronically undersized — the #1 airflow problem
- The blower can only deliver what the returns allow
- Aim for adequate return area: 200 sq inches per ton minimum
- Closed bedroom doors without transfer grilles create pressure imbalances

**Duct Leakage:**
- Ducts in unconditioned spaces lose 15-30% of conditioned air through leakage
- Duct sealing and insulation have huge impact on actual system performance
- Many jurisdictions now require duct leakage testing

### ProCalcs Validation Points for Manual D
The validator can verify from the duct design report:
- Friction rate falls within ACCA's 0.06-0.18 IWC range
- Room CFM values match Manual J room-by-room airflow requirements
- Total system CFM matches blower capacity from Manual S equipment selection
- Static pressure budget is reasonable for the equipment selected
- Return air sizing is adequate relative to supply

---

## PART 4: HOW PROCALCS USES THIS KNOWLEDGE

### Validation Tiers (What to Check, In Order of Priority)

**Tier 1 — Conditioned Square Footage (Phase 1 Primary Focus)**
Compare room areas from the Manual J report against architectural plan measurements.
This catches the most fundamental error: wrong room sizes produce wrong loads.
- Sum of room areas should equal system/AHU total
- System totals should equal whole-house total
- Individual room areas should match plan dimensions within tolerance

**Tier 2 — Design Conditions**
Verify the calculation used appropriate inputs:
- Weather station matches project location (not a warmer/cooler nearby city)
- Indoor design temps are standard (70F heating, 75F cooling)
- Outdoor temps match ASHRAE/Manual J tables for that location
- Grains difference is appropriate (negative in dry climates, positive in humid)
- Daily temperature range classification is correct for the location

**Tier 3 — Construction Inputs**
Cross-check envelope specs against plans and code:
- Wall R-values match specifications on the architectural plans
- Window U-factors and SHGC match the window schedule
- Insulation values meet or exceed local energy code minimums
- Floor and ceiling types match the foundation/roof shown on plans
- Infiltration method and values are reasonable for construction type
- Duct location matches what the plans show

**Tier 4 — Equipment Sizing (Manual S Compliance)**
Check that selected equipment meets ACCA sizing rules:
- Cooling sensible capacity >= 100% of sensible load
- Total cooling capacity between 95-115% (AC) or 100-125% (heat pump) of total load
- Heating capacity between 100-140% of heating load
- Supplemental heat specified if heat pump can't cover full heating load
- Equipment is AHRI-matched system

**Tier 5 — Duct Design (Manual D Compliance)**
Verify duct system design is consistent:
- Room CFM values trace back to Manual J room loads
- Friction rate within 0.06-0.18 IWC range
- Static pressure budget is reasonable
- Total system CFM consistent with equipment blower capacity

### Confidence Scoring Framework

For each validation tier, ProCalcs assigns a confidence level:

**GREEN (High Confidence — Passes)**
- Values match within expected tolerance
- Design conditions are standard for the location
- Equipment sizing within ACCA limits
- No red flags in construction inputs

**YELLOW (Medium Confidence — Review Recommended)**
- Values are close but outside tight tolerance (e.g., room area off by 5-10%)
- Non-standard but defensible design choices
- Equipment sizing at the edge of ACCA limits
- Infiltration estimate used instead of blower door test

**RED (Low Confidence — Likely Error)**
- Room areas don't match plans by >10%
- Sum of room areas doesn't equal system total
- Design temperatures don't match ASHRAE data for location
- Equipment grossly oversized (>125% cooling for AC, >150% heating)
- Construction values contradict what's shown on plans
- Multiple safety factors stacked (padding detected)

### ACCA-Approved Software List (for reference)
The following software platforms are ACCA-approved for Manual J v.8:
- Wrightsoft Right-Suite Universal
- Elite RHVAC (worksheet-based approach)
- Conduit Tech (iPad LiDAR scanning)
- Cool Calc (free calculation, paid reports)

ProCalcs should verify the Manual J report was produced by ACCA-approved software
by checking for the "Calculations approved by ACCA" stamp in the output.

---

## PART 5: KEY FORMULAS AND REFERENCE VALUES

### Heat Transfer Formulas
- Conduction: Q = U x A x delta-T (BTU/h)
- Sensible air load: Q = 1.1 x CFM x delta-T (BTU/h)
- Latent air load: Q = 0.68 x CFM x delta-grains (BTU/h)
- Where CFM = cubic feet per minute of airflow

### Standard Values
- Indoor heating design: 70F (ACCA standard)
- Indoor cooling design: 75F (ACCA standard)
- Occupant count: Number of bedrooms + 1
- Cooling airflow target: ~400 CFM per ton
- 1 ton of cooling = 12,000 BTU/h

### Window Performance Ranges (for reasonableness checks)
- U-Factor: 0.20 (excellent triple-pane) to 1.20 (poor single-pane)
- SHGC: 0.15 (heavy tint/low-e) to 0.80 (clear glass)
- Typical modern double-pane low-e: U=0.25-0.35, SHGC=0.20-0.40

### Wall Insulation Typical Values
- 2x4 frame, R-13 batt: U ≈ 0.082
- 2x6 frame, R-19 batt: U ≈ 0.064
- 2x6 frame, R-21 batt: U ≈ 0.060
- ICF (insulated concrete form): U ≈ 0.040-0.050
- SIP (structural insulated panel): varies by thickness

### Manual S Sizing Limits Summary Table
| Equipment Type | Cooling Size Range | Heating Size Range |
|---------------|-------------------|-------------------|
| Air Conditioner | 95-115% of total cooling load | N/A |
| Heat Pump (cooling-dominant) | 100-115% of total cooling load | Check balance point |
| Heat Pump (heating-dominant) | 100-125% of total cooling load | Check balance point |
| Furnace / Boiler | N/A | 100-140% of heating load |

### Manual D Friction Rate Limits
| Condition | Friction Rate (IWC/100ft) |
|-----------|--------------------------|
| Minimum acceptable | 0.06 |
| Maximum acceptable | 0.18 |
| Common residential range | 0.08-0.12 |

---

## DOCUMENT STATUS
- Version: 1.0
- Created: February 19, 2026
- Author: Claude Opus 4.6 (compiled from ACCA published standards and technical resources)
- Reviewed by: Tom (pending)
- Sources: ACCA Technical Manuals, ACCA HVAC Blog, Building America Solution Center,
  Utah Energy Code technical series, Energy Vanguard, HVAC School, load-calculations.com,
  Contracting Business, MrCool technical guides
- NOTE: This guide is compiled from publicly available ACCA educational materials.
  The actual Manual J, S, and D standards should be purchased from ACCA for the
  complete normative procedures and tables.
