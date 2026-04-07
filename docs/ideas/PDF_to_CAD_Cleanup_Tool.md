# PDF-to-CAD Cleanup Tool
### ProCalcs Designer Efficiency | Status: ACTIVE — High Priority
### April 2026

---

## The Problem

Every job ProCalcs receives from a builder client comes as a PDF floor plan.
Before a designer can start their HVAC drawing in Wrightsoft, they have to:

1. Convert the PDF to DXF/DWG (CAD format)
2. Import it into CAD software
3. **Manually delete everything that isn't a wall** — dimensions, labels, tags,
   room names, furniture, electrical symbols, plumbing fixtures, north arrows,
   title blocks, and more
4. Import the cleaned DXF into Wrightsoft as a background
5. Set the scale
6. Retrace the wall lines

Steps 1-4 take **30-60 minutes per job** of pure manual cleanup.
As volume grows, this becomes the single biggest bottleneck to scaling
designer output without hiring more people.

---

## The Opportunity

Most of this cleanup is eliminatable. The goal is:

**Upload messy PDF → Download clean DXF with only wall outlines, doors,
and windows — ready for Wrightsoft in under 60 seconds.**

---

## The 80/20 Split

Based on the team's experience, incoming PDFs fall into two categories:

### 80% — Digital PDFs (from architect's CAD software)

**Confirmed by design team:** When PDFs are converted to DXF/DWG, ALL elements
land on ONE layer regardless of whether the original PDF had layers. This means
layer-based filtering is useless — which is exactly why designers have to manually
delete element by element today.

However, even with everything on one layer, the DXF file internally knows what
each object IS via its entity type. This is what our tool exploits:

| Element | DXF Entity Type | Action |
|---|---|---|
| Walls, room outlines | LINE, LWPOLYLINE, POLYLINE | ✅ Keep |
| Door/window openings | ARC | ✅ Keep |
| Interior doors | INSERT (block reference) | ✅ Keep — see Smart INSERT Filter |
| Columns, round features | CIRCLE | ✅ Keep |
| Appliances (range hood, dryer) | INSERT (block reference) | ✅ Keep — ventilation provision |
| Dimension strings | DIMENSION | ❌ Strip |
| Text labels, room tags | TEXT, MTEXT | ❌ Strip |
| Furniture (beds, tables, etc.) | INSERT (block references) | ❌ Strip |
| Electrical symbols | INSERT (block references) | ❌ Strip |
| Plumbing fixtures | INSERT (block references) | ❌ Strip |
| Hatch/fill patterns | HATCH | ❌ Strip |

**The one-layer problem does not affect our approach** — entity types always
exist regardless of layer structure. Python reads each object, checks its type,
keeps it or deletes it.

**INSERT entities require special handling.** Not all block references are junk.
Interior doors and ventilation-relevant appliances (range hoods, dryers) must
be preserved. See the **Smart INSERT Filter** section below for the detection
strategy.

**Solution:** Python reads the DXF, keeps geometry entity types
(LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE), runs INSERT entities through
a smart filter to keep doors and ventilation appliances while stripping
furniture/electrical/plumbing, and removes all text and dimensions.
High accuracy. Fast. Fully automatable. No layer dependency.

### 20% — Scanned or photographed blueprints

No entity structure — just pixels. Walls and dimensions are visually
distinct but structurally identical in the file.

**Solution:** AI vision (Claude) analyzes the image, identifies wall geometry
vs. annotation noise, traces wall outlines, outputs a DXF approximation.
Not perfect, but dramatically reduces manual work.

---

## How It Works — User Flow

```
Designer uploads PDF to tool
        |
        ↓
System detects: Digital or Scanned?
        |
   ┌────┴────┐
Digital    Scanned
   |           |
Vector      AI Vision
Strip       Trace
   |           |
   └────┬────┘
        ↓
Clean DXF output
        |
        ↓
Designer downloads → imports to Wrightsoft → sets scale → traces walls
```

---

## What Gets Kept (Confirmed by Design Team + Richard)

| Element | DXF Entity Type | Reason |
|---|---|---|
| Walls, room outlines | LINE, LWPOLYLINE, POLYLINE | Primary drawing surface |
| Stairs | LINE, LWPOLYLINE | Reference points for room sizing |
| Door swings | ARC | Spatial reference for openings |
| Interior doors | INSERT (block reference) | Kept per Richard — spatial layout reference |
| Window openings | LINE | Wall break reference |
| Columns, curved walls | CIRCLE, ARC | Structural geometry |
| Range hood | INSERT (block reference) | Ventilation provision — exhaust/makeup air |
| Dryer | INSERT (block reference) | Ventilation provision — exhaust requirements |

**Key insight:** Stairs, doors, and windows drawn as pure geometry (LINE, ARC)
are kept automatically by the entity-type filter. Interior doors and
ventilation-relevant appliances drawn as INSERT block references require
the Smart INSERT Filter to be preserved.

## What Gets Stripped

| Element | DXF Entity Type |
|---|---|
| Dimension strings | DIMENSION |
| Text labels, room tags, notes | TEXT, MTEXT |
| Furniture (beds, tables, sofas, etc.) | INSERT (block references) |
| Electrical symbols | INSERT (block references) |
| Plumbing fixtures (sinks, toilets, tubs) | INSERT (block references) |
| Hatch / fill patterns | HATCH |
| Title blocks | TEXT + INSERT |
| North arrows, scale bars | INSERT |

**Note:** Appliances NOT related to ventilation (ovens without range hoods,
refrigerators, dishwashers, etc.) are stripped. Only range hoods and dryers
are kept because they have direct HVAC ventilation implications.

---

## Smart INSERT Filter — Block Reference Classification

### Why This Exists

The original spec assumed all INSERT (block reference) entities were junk —
furniture, electrical symbols, fixtures. Richard's feedback changed that:
interior doors and ventilation-relevant appliances (range hoods, dryers)
must be preserved because they directly impact HVAC design.

This means we can't blindly strip all INSERTs. We need a classification
strategy to decide which blocks to keep and which to remove.

### Detection Strategy (Priority Order)

**1. Block Name Matching (primary method)**
DXF block references have a NAME attribute — the block definition name.
CAD software uses recognizable naming patterns:

- **Keep patterns:** `*DOOR*`, `*DR*`, `*RANGE*`, `*HOOD*`, `*DRYER*`,
  `*VENT*`, `*EXHAUST*`
- **Strip patterns:** `*FURN*`, `*CHAIR*`, `*TABLE*`, `*BED*`, `*SOFA*`,
  `*ELEC*`, `*OUTLET*`, `*SWITCH*`, `*LIGHT*`, `*SINK*`, `*TOILET*`,
  `*TUB*`, `*SHOWER*`, `*NORTH*`, `*ARROW*`, `*TITLE*`

Block names vary by architect/software, so this uses fuzzy keyword matching
on the block name string. Case-insensitive. Works for most CAD-generated files.

**2. Block Geometry Analysis (fallback)**
If block names are generic (e.g., `BLOCK_001`, `A$C12345`), inspect the
block definition's child entities:

- **Door signature:** Contains ARC (swing) + LINE (frame) within typical
  door dimensions (24"-36" wide). High confidence detection.
- **Appliance signature:** Rectangular geometry within standard appliance
  dimensions (range hood ~30", dryer ~27"). Medium confidence.
- **Furniture signature:** Large rectangular footprint with no arc components.
  Strip these.

**3. Configurable Whitelist (user override)**
The designer can manually tag blocks to keep/strip via a simple UI before
processing. This handles edge cases neither method catches. Phase 2 feature.

### Implementation Notes

- Start with block name matching — covers 80%+ of cases with zero complexity
- Block geometry analysis is Phase 1.5 — add when we have real DWG test files
  to validate the heuristics against
- The filter runs ONLY on INSERT entities. All other entity types follow
  the simple keep/strip rules from the main table above.
- When in doubt, KEEP the block. A designer can delete an extra block in
  seconds. Losing a door they needed costs minutes of rework.

### Richard's Rule: When In Doubt, Keep It

Better to leave a questionable block in the output than accidentally strip
something the designer needs. The cleanup tool reduces 95% of the noise —
the designer can handle the remaining 5% in seconds.

## The Full Designer Workflow (Why Cleanup Quality Matters)

The cleaned CAD file is used **throughout** the design process:

```
1. Clean CAD file imported into Wrightsoft as background layer
2. Designer retraces entire building over the CAD layer in Wrightsoft
3. CAD layer stays ON — designer does load calcs and duct design
   while seeing the actual plans underneath
4. When finished, Wrightsoft drawing layer turned OFF, CAD layer kept ON
5. File converted back to CAD for final equipment schedules and details
```

**The CAD layer is visible for the majority of the project.** It stays on
during load calculations and duct design so the designer can reference the
actual architectural plans. This is why cleanup quality matters so much —
every unnecessary entity in that layer costs performance on every pan,
zoom, and click for the entire duration of the project.

Wrightsoft also allows toggling specific elements on/off when converting
back to CAD, so if something isn't needed for the final mechanical drawings
it can be hidden at that stage. But anything not needed for mechanical
drawings shouldn't be in the file at all — strip it during cleanup so it
never slows down the working session.

**Performance is the reason cleanup exists at all.** Wrightsoft's drawing
grid becomes extremely slow when loaded with unnecessary entities. The more
clutter in the imported background, the worse the navigation performance.
Designers aren't cleaning files for aesthetics — they're doing it because
Wrightsoft is unusable otherwise. Every unnecessary INSERT, DIMENSION, TEXT,
and HATCH entity that survives cleanup costs the designer lag on every
interaction for the entire duration of the project.

---

## Where It Lives

Part of the ProCalcs ecosystem — same infrastructure, same team.
Either:
- A tab inside Designer Desktop (cleanest integration)
- A standalone web upload tool at a ProCalcs URL

Designers upload, download, done. No CAD software required for the cleanup step.

---

## Impact on Designer Capacity

| Current State | With Tool |
|---|---|
| 30-60 min cleanup per job | Under 60 seconds |
| Manual, error-prone | Automated, consistent |
| Wrightsoft sluggish with cluttered imports | Clean file = fast grid performance |
| Bottleneck at high volume | Scales without hiring |
| One designer, one job at a time | Batch processing possible |

If the team runs 20 jobs/week, this tool saves 10-20 hours of designer
time per week — the equivalent of a part-time hire, at zero cost.

---

## Tech Stack

**Digital PDF engine:**
- Python + `ezdxf` library — reads/writes DXF files
- Entity-type filtering — strip non-geometry, output clean file
- No AI needed for this path — pure programmatic

**Scanned PDF engine:**
- PDF → high-DPI image (pdf2image / poppler)
- Claude AI vision — identifies wall geometry from pixel noise
- `ezdxf` — writes traced geometry as clean DXF output

**Delivery:**
- Flask API endpoint: `POST /api/v1/tools/pdf-to-cad`
- Accepts PDF upload, returns DXF download
- Fits inside existing `procalcs-bom` backend or its own service

---

## Build Priority

**HIGH.** This is not a nice-to-have. Every job the team takes is delayed
by 30-60 minutes before design even starts. As marketing grows and volume
increases, this bottleneck compounds. Solving it means ProCalcs can handle
significantly more work with the exact same team.

Build order recommendation:
1. Digital PDF engine first (80% of jobs, highest ROI, simplest build)
2. Scanned PDF engine second (AI vision, more complex)
3. UI integration into Designer Desktop

---

## Confirmed Answers — Designer Team (April 2026)

1. **What does cleanup mean?** Remove title blocks, dimension lines, notes,
   furniture, electrical symbols — everything that isn't wall geometry,
   doors, or ventilation-relevant appliances
2. **Output format needed?** DWG — imported into Wrightsoft as a plan background
3. **PDF types?** Both digital/vector (80%) and scanned/photographed (20%).
   Scanned drawings double the difficulty and manual work time.
4. **What is background used for?** Tracing layer — designers retrace wall lines
   over it in Wrightsoft for their duct design
5. **Conversion tool?** AutoCAD — designers convert PDF→DWG in AutoCAD first,
   then our tool handles the cleanup
6. **Interior doors?** KEEP — Richard confirmed. Doors stay in the cleaned output
   as spatial references for the HVAC designer.
7. **Appliances?** KEEP range hoods and dryers — Richard confirmed. These tie
   directly to ventilation provisions (exhaust, makeup air). Other appliances
   (refrigerators, dishwashers, etc.) are stripped.

---

## Critical Technical Note — DWG Output Format

The output must be **DWG** (AutoCAD's proprietary format), not DXF.

`ezdxf` (our Python library) reads/writes DXF natively but cannot write DWG.

**Solution: ODA File Converter**
- Free command-line tool from the Open Design Alliance
- Converts DXF → DWG programmatically, no AutoCAD license on the server
- Fully automatable — runs silently in the processing pipeline

**Full processing pipeline:**
```
Designer uploads DWG
    ↓
Server reads DWG → converts to DXF internally (ezdxf)
    ↓
Python strips all non-geometry entities
    ↓
Clean DXF written to disk
    ↓
ODA Converter: DXF → DWG
    ↓
Designer downloads clean DWG — ready for Wrightsoft
```

Designer uploads DWG, downloads DWG. Never sees DXF at all.

---

## Phase Plan (Updated)

**Phase 1 — Digital DWG cleanup (BUILD NOW)**
- Accept DWG upload
- Strip dimensions, text, furniture, symbols via entity-type filtering
- Output clean DWG via ODA Converter
- Saves 30-60 min per job on 80% of all incoming work

**Phase 2 — Scanned blueprint engine (LATER)**
- AI vision (Claude) analyzes scanned image
- Traces wall geometry from pixel noise
- Outputs approximated DWG
- Complex, never perfect, but dramatically reduces manual work on the 20%

---

*Document created: April 2026*
*Updated: April 7, 2026 — Richard's feedback on interior doors + ventilation appliances*
*Source: Designer team feedback — PDF cleanup bottleneck*
*Owner: Tom Platania / ProCalcs LLC*
