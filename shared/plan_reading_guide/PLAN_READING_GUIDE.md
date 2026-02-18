# PROCALCS PLAN READING GUIDE
## How to Read Architectural Floor Plans for HVAC Load Calculations
### Version 1.0 — February 17, 2026

---

**PURPOSE:** This guide is loaded every time the AI reads architectural plans. It teaches
the AI how to correctly interpret dimensions, identify conditioned spaces, and avoid
common mistakes that lead to incorrect square footage calculations.

**SOURCE:** Industry standards (ANSI, NCS, ACCA), architectural dimensioning best practices,
and real-world lessons learned from ProCalcs projects.

---

## 1. DIMENSION STRING HIERARCHY

Architectural plans use multiple parallel rows of dimensions called "strings."
These strings are layered from the building outward, and each layer means
something different. Understanding this hierarchy is CRITICAL.

### The Layers (from building outward):

**STRING 1 (Closest to building)** — OPENING DIMENSIONS
- Window locations (typically to CENTERLINE of window)
- Door locations (to centerline or edge of opening)
- These are NOT room dimensions. They tell the framer where to put holes in walls.
- On GT Bray plans, "10'-4" was this type — distance from outside wall to window center.

**STRING 2 (Next out)** — WALL BREAK DIMENSIONS
- Distances between major wall intersections
- Shows where interior walls meet exterior walls
- These CAN indicate room widths but only wall-to-wall at structural breaks

**STRING 3 (Outermost)** — OVERALL BUILDING DIMENSION
- Total length or width of the building, outside face to outside face
- This is the number used for gross building footprint calculations

### How to Tell Them Apart:
- Count the rows. Outermost row = overall. Innermost row = openings.
- Look at what the tick marks land on. Walls = structural dimension. 
  Centerline symbols (circle with cross) = window/door location.
- If a dimension string has 4-6 small segments adding up to the overall,
  it's likely opening locations, not room sizes.

### CRITICAL RULE:
**Never use the innermost dimension string as a room dimension.**
That string shows window and door LOCATIONS, not room sizes.
Room dimensions are either called out separately inside the room
or derived from wall-to-wall breaks on the second string.

---

## 2. WINDOW AND DOOR CALLOUTS

### Window Dimensions:
- In US wood frame construction, windows are dimensioned to the CENTERLINE
  of the rough opening. This is industry standard.
- The dimension runs from a wall corner or another opening to the window center.
- A window symbol (hexagon or circle with a number) identifies the window type.
  The actual window size is in the WINDOW SCHEDULE, not in the dimension string.
- For masonry construction (CMU, brick), dimensions may go to the EDGE of the
  opening instead of centerline.

### Door Dimensions:
- Doors may be dimensioned to centerline or to the edge of the jamb.
- Door WIDTH is shown as a segment in the dimension string (e.g., "3'-0" for
  a standard 3-foot door).
- Door swings are shown as arcs — the arc shows which direction the door opens
  and which room it belongs to.

### How to Identify Opening Callouts vs Room Dimensions:
- Opening callouts are on the INNERMOST dimension string
- They reference centerline symbols or opening edges
- They often have window/door schedule numbers nearby
- Room dimensions are wall-to-wall with tick marks at solid wall lines
- Room dimensions are often written INSIDE the room or on a separate string

---

## 3. ROOM DIMENSIONS

### Where Room Dimensions Appear:
- Written inside the room (e.g., "14'-10" x 6'-6"")
- On the second dimension string showing wall-to-wall breaks
- Sometimes only one dimension is given inside the room; the other must be
  derived from the dimension strings or overall building math

### What Room Dimensions Measure:
- **Face of stud to face of stud** — most common in wood frame
- **Face of finish (drywall) to face of finish** — used on some architectural plans
- **Centerline of wall to centerline of wall** — used for multi-unit/commercial
- The plan SHOULD note which convention is used, but many don't.
  When unclear, assume face of stud for residential, face of finish for commercial.

### Calculating Room Square Footage:
- Multiply the two room dimensions (length x width)
- For irregular rooms (L-shaped, angled walls), break into rectangles and add
- Interior dimensions will be slightly smaller than exterior due to wall thickness
- Wall thickness: Wood frame = ~4.5" (2x4) or ~6.5" (2x6) plus drywall
  CMU block = ~8" nominal, ~12" with furring and finish

---

## 4. CONDITIONED vs UNCONDITIONED SPACE

This is the most important determination for HVAC load calculations.
Getting this wrong means calculating loads for space that won't be heated/cooled,
or missing space that will be.

### Indicators That a Space IS Conditioned:
- "New 2x4 Fire Rated Acoustical Ceiling" or similar ceiling treatment notes
- HVAC supply registers or diffusers shown on the plan
- Return air grilles shown on the plan
- Thermostat locations
- Insulation noted in walls surrounding the space
- Ductwork routed to the space
- The space is listed in the HVAC schedule or equipment schedule

### Indicators That a Space is NOT Conditioned:
- Garage (almost never conditioned unless specifically noted)
- Attic space
- Crawl space
- Covered porches and patios
- Storage rooms without HVAC notes
- Mechanical/electrical rooms (SOMETIMES conditioned — check for HVAC notes)
- Rooms lacking ceiling treatment notes when adjacent rooms have them
- No supply/return registers shown

### Spaces That Are Tricky:
- **Electrical rooms** — Sometimes conditioned (like GT Bray), sometimes not. 
  Look for HVAC equipment or ceiling treatment notes.
- **Bathrooms** — Almost always conditioned, but some utility/commercial
  restrooms may not be.
- **Mud rooms / laundry rooms** — Usually conditioned but check.
- **Enclosed porches / sunrooms** — May or may not be. Look for HVAC connections.
- **Bonus rooms over garages** — Usually conditioned but may be separate zone.

### CRITICAL RULE:
**When a plan shows specific construction treatment (insulation, ceiling, HVAC)
in some rooms but NOT in others, the rooms WITHOUT those notes are likely
unconditioned. Use the notes as the primary indicator.**

### Labeled Square Footage:
- Some plans include a total conditioned area label (e.g., "LIVING AREA: 2,450 SF")
- When present, USE this number as the starting point
- BUT ALWAYS cross-check it against room dimensions — these labels are
  sometimes wrong, outdated, or include/exclude spaces incorrectly
- If the label and your calculation differ by more than 5%, FLAG IT for review

---

## 5. LINE TYPES AND WHAT THEY MEAN

### Solid Lines:
- **Thick solid** — Walls, columns, major structural elements (cut through in plan)
- **Medium solid** — Secondary elements, doors, windows in elevation
- **Thin solid** — Dimension lines, leader lines, hatching, door swings

### Dashed Lines:
- **Dashed** — Hidden elements: roof outline above, floor below, items behind
- **Long dash-short dash** — Centerlines, reference lines, column grids

### Hatching (Cross-hatching):
- Diagonal lines inside wall sections = insulation
- Cross-hatched areas = wall sections showing material (CMU, brick, concrete)
- Different hatch patterns indicate different materials
- On GT Bray: hatched walls = existing CMU block walls with stucco

### Line Weight Hierarchy:
- Heaviest lines = cut elements (walls in floor plan)
- Medium lines = visible elements beyond the cut (furniture, fixtures)
- Lightest lines = dimensions, annotations, leaders, door swings

---

## 6. COMMON SYMBOLS

### Doors:
- Thin rectangle = door panel
- Arc = door swing direction (shows which way it opens)
- Pocket doors = rectangle sliding into wall
- Sliding/barn doors = rectangle alongside wall
- Double doors = two rectangles with two arcs

### Windows:
- Break in wall crossed by thin parallel lines = window
- Number in hexagon or circle = window schedule reference
- Centerline symbol at window = dimension reference point

### Section Cuts and Detail Callouts:
- Circle with number/letter and filled arrow = section cut direction
- "SIMILAR" with arrow = same detail applies as referenced section
- Triangle with number = detail reference (e.g., "1/A-1" = Detail 1 on Sheet A-1)

### HVAC Symbols (relevant for conditioned space identification):
- Rectangle with X = supply air diffuser/register
- Rectangle with lines = return air grille
- Circle with T = thermostat
- Rectangles connected by lines = ductwork
- Equipment symbols vary — look for labels like "AHU", "FCU", "RTU"

### Title Block (usually right side or bottom):
- Project name and address
- Sheet number and title
- Scale
- Date
- Architect/engineer stamp
- Revision history

---

## 7. COMMON ABBREVIATIONS

### Construction:
- TYP = Typical (this detail repeats elsewhere)
- SIM = Similar (same as referenced detail)
- NIC = Not In Contract
- EQ = Equal (equal spacing)
- NTS = Not To Scale
- CMU = Concrete Masonry Unit (concrete block)
- GYP BD or GWB = Gypsum Board (drywall)
- MTL = Metal
- WD = Wood
- CONC = Concrete
- INSUL = Insulation
- CLG = Ceiling
- FLR = Floor
- FDN = Foundation

### Dimensions:
- O.C. = On Center (spacing between studs/joists)
- C/L or CL = Centerline
- R.O. = Rough Opening
- F.F. = Finish Floor
- T.O.S. = Top of Slab / Top of Steel
- A.F.F. = Above Finish Floor
- F.O.S. = Face of Stud
- F.O.F. = Face of Finish

### Rooms/Spaces:
- MECH = Mechanical Room
- ELEC = Electrical Room
- STOR = Storage
- CLO or CLOS = Closet
- BATH or BTH = Bathroom
- KIT = Kitchen
- LR or LIV = Living Room
- BR or BDR = Bedroom
- GAR = Garage
- UTIL = Utility
- LDRY = Laundry

---

## 8. CROSS-CHECK RULES

These checks catch errors in AI dimension reading. If the math doesn't add up,
something was read wrong.

### Rule 1: Room Widths Must Add Up
- All rooms along one axis + wall thicknesses should approximately equal
  the overall building dimension on that axis
- Allow ~4-6 inches per interior wall (frame + drywall both sides)
- Allow ~6-12 inches for exterior walls depending on construction type
- If the total is off by more than 2 feet, a dimension was misread

### Rule 2: Conditioned + Unconditioned = Total
- Add all conditioned room areas + all unconditioned room areas
- Should approximately equal gross building footprint
- Difference should only be wall areas (typically 5-10% of gross)

### Rule 3: Dimension String Segments Must Add Up
- Individual segments on any dimension string should add up to the
  overall dimension shown on the outermost string
- If they don't add up, one of the segments was misread

### Rule 4: Compare Label vs Calculated
- If the plan has a labeled square footage AND you calculated from dimensions,
  compare the two
- Within 5% = reasonable (wall thickness differences, rounding)
- 5-10% off = warning, investigate which rooms differ
- More than 10% off = something is wrong, flag for human review

---

## 9. KNOWN AI MISTAKES — LESSONS LEARNED

This section documents specific errors the AI has made on real plans.
Each entry teaches the AI what went wrong and how to avoid it.

### Mistake #1: Window Centerline Used as Room Width
- **Plan:** GT Bray Maintenance Building
- **What happened:** AI read "10'-4"" from the innermost dimension string
  and used it as the width of the two front rooms
- **Actual meaning:** 10'-4" was the distance from the exterior wall corner
  to the centerline of a window — a window location callout
- **Actual room widths:** 6'-6" and 6'-8" (shown inside the rooms)
- **Impact:** Overcounted unconditioned area by ~60 sq ft per room
- **How to avoid:** NEVER use innermost dimension string values as room
  dimensions. Check if the dimension terminates at a centerline symbol
  or a wall line. If centerline, it's an opening callout.

### Mistake #2: Misreading Overall Building Dimension
- **Plan:** GT Bray Maintenance Building
- **What happened:** AI read 31'-4" or 31'-8" for the building width
- **Actual dimension:** 31'-0" (clearly labeled on the plan)
- **Impact:** Gross building area off by 20-45 sq ft
- **How to avoid:** Zoom in on overall dimensions. Read the EXACT notation.
  Don't approximate or guess at the inches. 31'-0" means exactly 31 feet.

### Mistake #3: Misidentifying Unconditioned Rooms
- **Plan:** GT Bray Maintenance Building
- **What happened:** AI identified the wrong rooms as unconditioned
  (guessed bathroom and electrical instead of the two rooms flanking the front door)
- **Actual indicator:** The conditioned rooms had "New 2x4 Fire Rated
  Acoustical Ceiling" noted. The two unconditioned front rooms did NOT.
- **Impact:** Would have calculated completely wrong conditioned area
- **How to avoid:** Look for construction treatment notes (ceiling, insulation,
  HVAC) as primary indicators. Don't guess based on room function alone.

### Mistake #4: Confusing Dimension Purpose on Rotated Plans
- **Plan:** GT Bray Maintenance Building (landscape plan on portrait sheet)
- **What happened:** Plan was rotated 90 degrees, making it harder to
  orient which dimensions were width vs depth
- **How to avoid:** Always check the plan orientation. Look at the title block
  for plan orientation. North arrow if present. Read dimension strings in
  context of the building shape, not the page orientation.

---

## 10. COMMERCIAL vs RESIDENTIAL DIFFERENCES

### Commercial Plans (like GT Bray):
- More detailed dimension strings with more layers
- Column grid systems (lettered one axis, numbered the other)
- Wall types legend showing construction of each wall type
- Fire rating requirements noted on walls and ceilings
- Often include separate mechanical, electrical, plumbing sheets
- May show furniture/equipment layouts
- Building code occupancy classifications noted

### Residential Plans:
- Simpler dimension strings (often just 2-3 layers)
- Room names and sizes often written inside each room
- May include furniture layouts to show room function
- Window and door schedules on a separate sheet
- Garage is almost always unconditioned
- Attic/crawlspace shown with dashed lines
- Less formal notation — some hand-drawn plans still exist

### Renovation Plans (like GT Bray):
- Show EXISTING construction vs NEW construction
- Different line types or hatching for existing vs new
- "Existing" labels on elements that aren't changing
- New work may be highlighted, clouded, or use different line weight
- Critical for HVAC: existing walls may have different R-values than new walls
- Must identify what's being added/changed for accurate load calculations

---

## 11. READING PROCESS — STEP BY STEP

When analyzing a floor plan for HVAC load calculations, follow this order:

### Step 1: Orient Yourself
- Identify the title block (project name, address, sheet number)
- Note the scale
- Determine plan orientation (north arrow, or note if rotated)
- Identify if this is new construction or renovation

### Step 2: Read Overall Building Dimensions
- Find the OUTERMOST dimension string
- Read the overall length and width
- Calculate gross building footprint

### Step 3: Identify All Rooms
- Name every room/space on the plan
- Note room labels if provided
- Identify rooms by fixtures (sink = bathroom/kitchen, toilet = bathroom)

### Step 4: Determine Conditioned vs Unconditioned
- Look for HVAC notes, ceiling treatment, insulation callouts PER ROOM
- Rooms with HVAC treatment = conditioned
- Rooms without = likely unconditioned
- Flag any ambiguous spaces for human review

### Step 5: Read Room Dimensions
- Look INSIDE rooms for dimension callouts first
- If not inside, use the SECOND dimension string (wall break dimensions)
- NEVER use the innermost string (opening dimensions) as room sizes
- For each room, get length and width

### Step 6: Calculate Conditioned Area
- Calculate each conditioned room's area (length x width)
- Sum all conditioned room areas
- Compare to gross building footprint minus unconditioned rooms
- If a labeled conditioned sqft exists, compare to your calculation

### Step 7: Cross-Check (Section 8 rules)
- Do room widths add up to overall dimension?
- Does conditioned + unconditioned ≈ gross footprint?
- Do dimension string segments add up?
- Does labeled sqft match calculated sqft?

### Step 8: Report Findings
- State gross building area with source dimensions
- List each room: name, dimensions, conditioned yes/no, area
- State total conditioned area
- Flag any discrepancies or ambiguous determinations
- Flag any rooms where conditioned status was unclear

---

*This guide is updated as new lessons are learned from real plan analysis.
Every mistake becomes a new entry in Section 9.*
