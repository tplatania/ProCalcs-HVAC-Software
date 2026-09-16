# Designer Desktop — project context

SPA + Express server for ProCalcs HVAC tooling. This repo is a
subtree-split of upstream `ProCalcs-HVAC-Software/procalcs-designer`
(sync helpers in `scripts/`, local-only).

## Current mission: the BOM Module

Produce priced Bills of Materials from Wrightsoft `.rup` design files
for **standard projects** — the projects that get no BOM today (the
company only makes BOMs for Rheia-system projects). Read
`docs/bom-strategy.md` FIRST — it explains the reproduce → residual →
extend plan and why previous framings (autonomous assembler, Windows
observer agent) were dropped.

Key docs, in reading order:
1. `docs/bom-strategy.md` — the strategy and its rationale
2. `docs/corpus-status.md` — what data we have (12-community Zoho archive)
3. `docs/corpus-findings-2026-07-14.md` — first analysis + corrections
4. `contractor-rules/reliable/rules.yaml` — the rules ledger (provenance-tagged)
5. `docs/qa-ui-spec.md` — how Richard reviews drafts (never questionnaires)
6. `docs/wrightsoft-com-surface.md` — COM contract (Windows-only, not used server-side)

## Domain facts that keep tripping people up

- BOM `.xls` exists ⇒ Rheia project. Any statistic over "projects
  with BOMs" is about Rheia projects ONLY (selection bias).
- `.rup` files without a BOM are the standard projects — the target.
- Richard (contractor-side expert) has NO written rules record and
  minimal time: engage him as a reviewer of concrete drafts, never an
  author of abstract rules. One correction at a time.
- "RE" suffix (` RE`, `-RE`, ` -RE`) on `.rup` = revision; prefer the
  non-RE variant.
- 79th Ct test file is a labeled Edge Case (Trane, P99 outlier) — do
  not generalize from it.

## Hard rules

- NEVER commit: `.mdb` files, credentials, tokens, the corpus
  (`~/Procalcs/RUPs-from-zoho/`), or anything from `crm.mdb`
  (customer PII — do not ingest, do not read beyond table names).
- Zoho/OAuth credentials live in `~/Procalcs/envs/` only.
- The `.rup` structural parsers live in the upstream repo
  (`procalcs-hvac-upstream/procalcs-bom/backend/utils/`) — import
  from there, don't fork copies.

## Deploy targets

- `procalcs-designer-desktop-staging` (Cloud Run) — this app.
- `procalcs-hvac-bom-staging` — the BOM backend.
- Observer tokens: Secret Manager `observer-tokens` (endpoint exists
  at `/api/observer/upload`; agent shelved, endpoint kept).
