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

When a digital PDF (AutoCAD, Revit, Chief Architect) is converted to DXF,
every element has a distinct entity type in the file structure:

| Element | DXF Entity Type |
|---|---|
| Walls, room outlines | LINE, POLYLINE, LWPOLYLINE |
| Dimensions | DIMENSION |
| Text labels, tags | TEXT, MTEXT |
| Furniture, symbols | INSERT (block references) |
| Hatch patterns | HATCH |

**Solution:** Python reads the DXF, keeps only geometry entity types
(LINE, POLYLINE, ARC, CIRCLE), strips everything else, outputs clean file.
High accuracy. Fast. Fully automatable.

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

## Open Questions (confirm with design team)

1. What CAD software do designers use to do the initial PDF→DXF conversion
   before cleanup? (Adobe, AutoCAD, online tool?) — this may be automatable too
2. Do any builders send DXF/DWG directly? If so, the PDF conversion step
   is skippable entirely
3. Are there specific element types they always keep beyond walls?
   (e.g., always keep stairs, always keep exterior doors)
4. Do they need layers preserved, or is a single-layer clean DXF acceptable?

---

*Document created: April 2026*
*Source: Designer team feedback — PDF cleanup bottleneck*
*Owner: Tom Platania / ProCalcs LLC*
