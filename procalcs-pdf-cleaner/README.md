# ProCalcs PDF Cleaner

Automated DWG cleanup tool for HVAC designers. Strips non-essential entities
(dimensions, text, furniture, electrical symbols) from architect-converted DWG
files, producing a clean background ready for Wrightsoft import.

## Tech Decisions

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Backend | Python / Flask | ezdxf library is Python-only; matches procalcs-bom stack |
| DXF Processing | ezdxf | Industry-standard DXF read/write, no AutoCAD dependency |
| DWG Conversion | ODA File Converter | Free CLI tool, converts DXF↔DWG without AutoCAD |
| Frontend | React + Vite | Consistent with procalcs-bom; drag-drop upload UX |
| Hosting | Google Cloud Run | Standard ProCalcs deploy target |

## Why This Exists

Designers spend 30-60 minutes per job manually deleting non-wall elements
from imported DWG files. Wrightsoft's drawing grid becomes extremely slow
with cluttered imports — every unnecessary entity costs performance on
every pan, zoom, and click for the entire project duration.

The CAD layer stays visible throughout the design process (load calcs,
duct design) so cleanup quality directly impacts daily productivity.

## What Gets Kept

- Walls, room outlines (LINE, LWPOLYLINE, POLYLINE)
- Door swings (ARC), interior doors (INSERT — smart filtered)
- Window openings, stairs, columns, curved walls
- Ventilation-relevant appliances: range hoods, dryers (INSERT — smart filtered)

## What Gets Stripped

- Dimension strings, text labels, room tags
- Furniture, electrical symbols, plumbing fixtures
- Hatch/fill patterns, title blocks, north arrows, scale bars

## Processing Pipeline

```
Designer uploads DWG → Server converts to DXF (ezdxf) →
Python strips non-geometry + smart INSERT filter →
Clean DXF written → ODA converts DXF → DWG →
Designer downloads clean DWG
```

## Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
flask run --port 5001

# Frontend
cd frontend
npm install
npm run dev
```

## Deployment

```bash
gcloud run deploy procalcs-pdf-cleaner --source . --region us-east1
```

## Full Spec

See `docs/ideas/PDF_to_CAD_Cleanup_Tool.md` in the main repo for the
complete specification including Smart INSERT Filter logic and designer
workflow context.
