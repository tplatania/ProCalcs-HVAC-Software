# Handoff Addendum #01 — v2 Direction Confirmed, Collaboration Model
## From: macOS BOM Module session → To: Windows Ghidra / Cowork session
### 2026-07-07

Read the original `HANDOFF_WRIGHTSOFT_REVERSE_ENGINEERING.md` first for context. This addendum picks up after you sent back `BOM_v2_Implementation_Handoff.md` (2026-07-07). Everything below reflects Gerald's decision after we digested it together on the macOS side.

---

## 1. TL;DR — what changed

- **v2 direction confirmed: Option A + Option B.**
  - **A** = Catalog-DB-driven pricing (read `RPRUWSF.mdb` schema and produce a catalog snapshot per project).
  - **B** = COM extraction station (drive `IBOMInterface.GetBOM` on a licensed WS box to return the canonical priced BOM).
  - **C** (SPA rename to v1/v2) is deferred until at least one end-to-end bundle has been ingested. We don't rebrand pages that aren't yet doing v2 things.
- **Your role: producer of intelligence and artifacts. Never deployment.** The macOS session builds and deploys everything customer-facing. Your outputs are files (docs, sample bundles, scripts) that we consume via git + GCS.
- **Do NOT re-implement the SPA v1 features** that the Gap 1–6 patch tried to build. All six of those already exist in `procalcs-designer-desktop` at `src/pages/diagnostics/wrightsoft-bom.tsx` — Quick Order Card, Duct Cuts, Equipment Specs, Rup Context banner, `.xls`-first upload, `?run=<id>` persistence, all live. Your patch would have been a rebuild on a page that isn't the canonical target.

---

## 2. Immediate next step — one focused task, blocks the least

**Run the COM smoke test on `IBOMInterface.GetBOM` for the two known test projects.** That's it. Everything else waits on the answer.

### Deliverable
A short markdown file `COM_smoke_test_2026-07-07.md` + two JSON sample outputs, one per project:

- `com_getbom_79th_ct.json` — the raw return payload of `IBOMInterface.GetBOM` (or the closest available call — `MakeDataSheetFile` / `GetDataSheetAsString` / iterating `GetBOMItem` for `GetItemCount` items) run against `79th Ct Residence Load Calcs.rup`.
- `com_getbom_ally.json` — same, for `Ally Residence (Main House).rup`.

The markdown answers three questions:

1. **Does the COM output include equipment (AHU / condenser / furnace / heat kit)?** Yes / No, with supporting evidence — count of equipment rows, or a snippet showing which model numbers appear.
2. **What is the field shape?** List every top-level field per item, with the type. Don't rewrite it into our schema — give it to us verbatim so I can build the adapter.
3. **What did you have to do to get it?** ~5-line procedure so the extraction script can automate it later. Which COM call succeeded, in what order, with what params.

### Why this task is blocking

The COM answer determines whether the extraction script we build next month is **simple** (dump COM output + catalog snapshot; retire the `.rup` parser) or **complex** (dump COM output + separately extract equipment via another route + catalog snapshot). Same script name, very different scope. Don't build the script yet.

### Estimated effort

30–90 minutes on a licensed WS box, assuming COM is reachable. Longer if `IBOMInterface` needs registration or DLL wiring.

### If the COM test hits a blocker

Ping back with the exact error + call sequence. Don't spend more than half a day on any single COM call — if `GetBOM` doesn't work, try `MakeDataSheetFile` next, then `GetDataSheetAsString`, then iterate `GetBOMItem`. Any one of those returning the priced BOM answers the question.

---

## 3. Parallel work you can start now (independent of COM outcome)

While the COM test is queued, these two threads can proceed:

### 3.1 — `RPRUWSF.mdb` schema dump

Deliverable: `procalcs-bom/docs/wrightsoft-catalog-schema.md` (commit to a branch on your side, we'll pull via bundle transfer or GitHub PR once you have write access).

For every table the ~138 BOM-generation reads touched during your Process Monitor capture:

- `CREATE TABLE` statement (columns + types + null/PK/index info)
- Row count
- 5–10 sample rows (redact PII if any)
- One-line description of what the table is for

Priority tables (from your `BOM_v2_Implementation_Handoff.md` §1):

- `ActItem` (38,757 parts master)
- `ActCateg` (436 pricing rules)
- `DFUnit` (1,035 equipment catalog)
- Any others that showed up in the trace as read >5 times

Use mdbtools if you want a repeatable dump (cross-platform, scriptable). The pure-Python `access-parser` undercounts overflow pages — you flagged that in your handoff, so avoid it here too.

### 3.2 — Bundle format proposal (v0 sketch)

Deliverable: `procalcs-bom/docs/wrightsoft-bundle-format.md` — a short spec for what an extraction-station bundle contains. Rough sketch to get you started; refine after the COM test:

```
<bundle-id>/
├── source_metadata.json     — WS version, project name, .rup path, extraction timestamp, station hostname
├── bom.json                 — the raw COM output (whatever shape it lands in — don't normalize)
├── catalog_snapshot.json    — subset of ActItem + ActCateg + DFUnit rows that BOM.json's line items reference
├── equipment.json           — if COM excludes equipment, this holds the fallback extraction (schedule, .rup parse, whatever)
└── raw_sources/
    ├── project.rup          — for archival / re-extraction / regression testing
    └── BOM.xls              — Wrightsoft's own export, for cross-check
```

Design principles:

- **Don't normalize into our schema.** Give us the Windows-side shape verbatim; I write an adapter on the macOS side that maps into `procalcs-bom`'s line-item shape. Field-name reconciliation happens on my side, not yours.
- **Bundle IDs are UUIDv7** (or timestamp-prefixed UUIDs so listings sort naturally).
- **JSON, not binary.** Except `raw_sources/` which is passthrough.
- **Every file self-contained.** Consumer should be able to read `bom.json` without needing to open `.rup`.

---

## 4. Collaboration model — how we exchange work

Two channels. Neither requires the Windows box to be reachable from Cloud Run.

### 4.1 — Git for docs, schemas, scripts

Same handoff pattern we're already using. You commit to your local `procalcs-bom` clone (from the bundle). When you have deliverables ready:

- **Preferred:** push to a branch on `github.com/tplatania/ProCalcs-HVAC-Software` (needs Tom to grant your account access). I fetch on the macOS side, review, merge.
- **Fallback:** run `git bundle create <name>.bundle --all` on Windows, transfer via Google Drive / OneDrive / USB, I `git fetch <bundle>` on macOS. Slow but bulletproof.

### 4.2 — GCS for actual extraction bundles

For the eventual real extraction bundles (JSON + catalog snapshots + raw sources), we'll use a GCS bucket. Not urgent for the current phase — sample bundles from your test runs can go through git-bundle transfer alongside the COM smoke test doc.

When we're ready to wire it up, I'll create `gs://procalcs-wrightsoft-extraction/` on our GCP project and give you write credentials. But that's after the COM test lands.

### 4.3 — What NOT to do

- **No Cloud Run deploys.** Only the macOS session touches `gcloud run deploy`.
- **No SPA changes.** All frontend work happens macOS-side. If you find a bug in the SPA or want a feature added, write it up as a task; I ship it.
- **No refactors of `rup_parser.py`.** The empirical parser is stable and covers v1. If your COM findings retire it, we'll delete it in one PR after v2 is proven. Don't touch it in the meantime.
- **No production data.** Everything you produce should be against the two known test files (79th Ct + Ally). Real customer projects come after v2 is stable.

---

## 5. Timeline expectation

No hard deadlines. Priority queue is:

1. **COM smoke test** — do first, don't wait for anything else.
2. **Schema dump** — start in parallel; can proceed independent of COM outcome.
3. **Bundle format v0** — sketch after schema dump; refine after COM test.
4. **Extraction script** — do NOT start until COM test result is in hand. Scope depends on the answer.

Ping when the COM smoke test doc + JSON samples are ready. That's the trigger for me to start building the ingest endpoint on `procalcs-hvac-bom`.

---

## 6. What I'm doing on macOS while you work

- **v1 stays production-supported.** Bugs get fixed, small features ship. Contractors keep using the current path.
- **No v2 code written until your COM test lands.** I could stub things speculatively, but the adapter shape depends on your COM answer. Better to wait a day than rewrite the adapter twice.
- **Preparing the ingest endpoint skeleton.** `POST /api/v1/bom/from-wrightsoft-bundle` route stub, GCS client wiring, adapter interface — all inert until your bundle format v0 is in hand.

---

## 7. Cross-references

- **Original handoff:** `HANDOFF_WRIGHTSOFT_REVERSE_ENGINEERING.md` (2026-07-03) — full context on the BOM Module, the .rup format, test files, capabilities and limitations.
- **Your handoff back to me:** `BOM_v2_Implementation_Handoff.md` (2026-07-07) — RE findings that this addendum builds on.
- **Test files:** `~/Procalcs/RUPs/79th Ct Residence Load Calcs.rup`, `~/Procalcs/RUPs/Ally Residence (Main House).rup`, `~/Procalcs/RUPs/BOM.xls`, `~/Procalcs/RUPs/BOM - Ally.xls` (all in your handoff bundle already).
- **Windows extraction self-check:** `ws_extract_check.ps1` in your prior artifacts — good starting point for the COM smoke test wrapper.

---

## 8. One-line summary of this addendum

> *"Green light on A + B. Do the COM smoke test first; produce artifacts, not services; C waits. macOS session preps the ingest endpoint skeleton while you produce the schema dump and bundle format sketch in parallel."*
