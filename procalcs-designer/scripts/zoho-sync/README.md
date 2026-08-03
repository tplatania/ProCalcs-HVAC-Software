# Zoho WorkDrive sync — Reliable's RUP + BOM archive

Recursive downloader for Richard's Zoho WorkDrive project archive
(Reliable Heating and Cooling). Produces the local corpus used by the
BOM reproduction engine and contractor-profile analysis.

## Files

- `zoho_sync.py` — the downloader. Rate-limited (5 QPS), resumable
  (skips files already present with matching size), retries listing
  AND download calls with exponential backoff, and survives failed
  subtrees without aborting the community walk.
- `batch_sync.sh` — all 12 communities, sequential (avoids Zoho
  rate-limit deadlock). Canopy (Mustang Way) excluded by instruction.
- `batch_sync_missing.sh` / `batch_sync_final3.sh` — targeted retry
  passes from the 2026-07-14 sync (kept for provenance; superseded by
  re-running `batch_sync.sh`, which resumes cleanly).

## Credentials

Reads `~/Procalcs/envs/zoho-workdrive.json` (never committed):
Zoho self-client OAuth with scopes `WorkDrive.files.ALL`,
`WorkDrive.workspace.ALL`, `WorkDrive.team.ALL`,
`WorkDrive.organization.READ`. Access token auto-refreshes mid-run.

## Endpoint notes (hard-won, do not "simplify")

- Listing AND download go through `https://workdrive.zoho.com/api/v1/…`.
  `www.zohoapis.com` starts hanging after ~80 min of sustained walking;
  `download-accl.zoho.com` (the host in `attributes.download_url`)
  rejects OAuth bearer tokens outright.
- Download endpoint is `GET /api/v1/download/{file_id}` — probed
  empirically 2026-07-13; not documented under that path.

## Output

Destination: `~/Procalcs/RUPs-from-zoho/<Community>/…` mirroring the
WorkDrive folder tree, filtered to `.rup,.xls,.xlsx`, RE-suffix .rup
revisions excluded (`--exclude-re`). A pairing index CSV maps each
.rup to its most likely BOM .xls.
