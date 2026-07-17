# Corpus status — Reliable Zoho archive

*Snapshot 2026-07-15 ~00:55 PST. Sync still completing (Pennyroyal
walking its archive tree; Creekside queued). Numbers below are lower
bounds; refresh by re-running the tally in `scripts/corpus-analysis/`.*

Source: Reliable Heating and Cooling's Zoho WorkDrive project archive.
Local mirror: `~/Procalcs/RUPs-from-zoho/` (never committed).
Sync tooling: `scripts/zoho-sync/`. Scope: all 12 communities under
the shared folder; **Canopy (Mustang Way) excluded by instruction**.
Filter: `.rup,.xls,.xlsx`; RE-suffix revisions excluded at download.

| Community | Files | .rup | BOM/.xls |
|---|---:|---:|---:|
| Pennyroyal | 1,175 | 796 | 379 |
| Towns at Riverwalk | 771 | 473 | 298 |
| Aulin Square Towns | 621 | 313 | 300 |
| Estates at Lake Jesup | 620 | 360 | 260 |
| Park View at the Hills | 576 | 349 | 227 |
| Towns at Greenleaf | 484 | 255 | 229 |
| Acuera Estates | 473 | 271 | 198 |
| Glades at Crossprairie | 189 | 109 | 79 |
| Vintner Reserve | 180 | 110 | 70 |
| Windham Park Townhomes | 170 | 151 | 15 |
| Creekside | 11+ | 9+ | 1+ (syncing) |
| General Documents | 3 | 0 | 3 |
| **Total** | **5,275+** | **3,196+** | **2,059+** |

Disk: ~8.0 GB and growing.

## How to read the rup:xls ratio

BOMs are produced **only for Rheia projects** (company practice,
confirmed 2026-07-14). So:

- Near-parity communities (Aulin 313:300) → heavily Rheia.
- Skewed communities (Windham Park 151:15) → mostly standard projects
  — **the BOM module's target population.**
- Any statistic computed over "projects with BOMs" describes Rheia
  projects only. See `scripts/corpus-analysis/README.md`.

## Provenance

- Synced 2026-07-14/15 via Zoho self-client OAuth (WorkDrive scopes),
  5 QPS, resumable. Endpoint quirks documented in
  `scripts/zoho-sync/README.md`.
- Pairing index: `~/Procalcs/RUPs-from-zoho/pairs-index.csv`.
- First-pass analysis (401 rups / 221 pairs, partial corpus):
  `~/Procalcs/reliable-analysis-2026-07-14/`. Re-run pending full sync.
