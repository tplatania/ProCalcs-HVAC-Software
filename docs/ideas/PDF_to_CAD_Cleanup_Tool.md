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
| Columns, round features | CIRCLE | ✅ Keep |
| Dimension strings | DIMENSION | ❌ Strip |
| Text labels, room tags | TEXT, MTEXT | ❌ Strip |
| Furniture, fixtures, symbols | INSERT (block references) | ❌ Strip |
| Hatch/fill patterns | HATCH | ❌ Strip |

**The one-layer problem does not affect our approach** — entity types always
exist regardless of layer structure. Python reads each object, checks its type,
keeps it or deletes it. Output is a clean single-layer DXF with only wall geometry.

**Solution:** Python reads the DXF, keeps only geometry entity types
(LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE), strips everything else, outputs
clean file. High accuracy. Fast. Fully automatable. No layer dependency.

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

## What Gets Stripped (Digital PDFs)

- All DIMENSION entities
- All TEXT and MTEXT entities (labels, tags, room names, notes)
- All INSERT entities (furniture, symbols, fixtures, north arrow)
- All HATCH entities (fill patterns)
- All POINT entities
- All SPLINE entities not part of wall geometry

## What Gets Kept

- LINE entities (walls, doors, windows)
- LWPOLYLINE / POLYLINE entities (room outlines)
- ARC entities (curved walls, arched openings)
- CIRCLE entities (columns, round features)

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
   furniture, electrical symbols — everything that isn't wall geometry
2. **Output format needed?** DWG — imported into Wrightsoft as a plan background
3. **PDF types?** Both digital/vector (80%) and scanned/photographed (20%).
   Scanned drawings double the difficulty and manual work time.
4. **What is background used for?** Tracing layer — designers retrace wall lines
   over it in Wrightsoft for their duct design
5. **Conversion tool?** AutoCAD — designers convert PDF→DWG in AutoCAD first,
   then our tool handles the cleanup

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
*Source: Designer team feedback — PDF cleanup bottleneck*
*Owner: Tom Platania / ProCalcs LLC*
