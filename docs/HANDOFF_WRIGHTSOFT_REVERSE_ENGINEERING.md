# Handoff — Wrightsoft Reverse-Engineering Session
## From: BOM Module session (macOS) → To: Ghidra session (Windows)
### 2026-07-03

You're picking up the reverse-engineering work on Wrightsoft's binaries with Ghidra. This document is self-contained — you don't need to read the BOM Module codebase to understand what's needed and why. If you do want to look at code, all specific file paths are cross-referenced at the end.

---

## TL;DR

We've built a working BOM Module that parses Wrightsoft's `.xls` exports and its `.rup` binary files empirically — extracting UTF-16 strings and pattern-matching. That works today but is brittle: we keep discovering file-format quirks reactively as real contractors test new files. **Your job is to give us a documented structural map of the `.rup` binary format so we can retire the reactive heuristics and build a proper automated integration with Wrightsoft.**

Downstream goal: replace manual `.xls`/`.rup` file drops with an automated import path — either a Wrightsoft plugin, a file-watcher on a canonical output directory, or an API hook we identify during the RE pass.

---

## Context — what we've built

**ProCalcs BOM Module** takes a contractor's Wrightsoft HVAC design output and produces a fully priced Bill of Materials with:
- Aggregated Quick Order Summary (grouped by SKU family + size, packaging math applied)
- Per-piece Duct Cuts view (every individual duct cut + joint count)
- Equipment lines with AHRI certification specs (SEER / HSPF / AFUE / capacity)
- Consumables auto-calculation (mastic, tape, screws, etc., configurable per contractor)
- Per-contractor pricing overrides + inline editing

Two input paths:
1. **`.xls` path (canonical).** The contractor exports Wrightsoft's own BOM.xls sheet via File → Bill of Materials. Our engine reads the 75-ish line items, matches SKUs against `mapped_parts.csv`, and produces a full BOM within ~1.3% of Wrightsoft's total on real projects. **This path works well.**
2. **`.rup` path (supplemental).** The contractor uploads the source `.rup` binary alongside the `.xls`. Our parser extracts equipment (AHU, condenser, furnace, ERV, heat kit) from the binary, since Wrightsoft's `.xls` export deliberately excludes those. **This path is where the empirical parsing lives — and where every recent bug has been.**

The `.rup` parser lives at `procalcs-hvac-upstream/procalcs-bom/backend/utils/rup_parser.py`.

---

## Current user workflow (what the contractor does today)

Concrete end-to-end, so you understand what "automated import" would replace.

1. **Contractor opens Wrightsoft** on their Windows box, works through a project (load calc, duct design, equipment selection).
2. **Contractor exports the BOM** — File → Bill of Materials → save as `.xls`. This is Wrightsoft's own canonical BOM output; 75-ish rows of ducts, fittings, registers, plenums, but NO equipment (AHU / condenser / furnace live in a separate schedule).
3. **Contractor opens ProCalcs Designer Desktop** in a browser (`procalcs-designer-desktop.run.app`), logs in, navigates to **Wrightsoft BOM** (in the sidebar under Diagnostics).
4. **Picks their contractor profile** from a dropdown (the profile carries their supplier preference, markup tiers, consumables config, pricing overrides).
5. **Uploads the `.xls` file** — drag-and-drop or file picker. Optionally also attaches the source `.rup` file via a second "Also add source .rup (optional)" uploader — this triggers the equipment merge from the binary.
6. **Clicks "Build BOM."** Server does its work in ~3-8 seconds.
7. **Result renders in-place** — a Quick Order Summary card at the top (aggregated view), a Duct Cuts card below (per-piece view), then the full line-items table grouped by section (Equipment / Duct System / Labor / Consumables), then an Equipment Specs card at the bottom with AHRI data. Grand total in the header. Each line's price is editable inline; each fitting SKU can be corrected inline; unpriced lines get a "needs price" / "$0 OK" affordance.
8. **Contractor tweaks pricing / SKUs** for anything that landed unpriced or mis-mapped.
9. **Downloads PDF and/or XLS** — same data, three artifacts, contractor forwards the PDF to their supplier for ordering and keeps the XLS for internal use.
10. **Result persists via `?run=<id>` URL** — the contractor can bookmark or share, refreshes preserve state, and the run is browseable later under Run History.

**Every one of these steps except #7-#10 involves the contractor moving files or clicking things a live Wrightsoft integration would automate away.** The Ghidra pass is scoped to replace steps 2, 5, and possibly 4 with automation.

---

## Capabilities and limitations

Honest inventory. RE session needs to know what's solid vs. what's fragile so time isn't wasted "fixing" things that already work — and so priorities focus on what's still brittle.

### Solid (don't touch)
- **`.xls` line-item ingestion** — full-fidelity, matches Wrightsoft output within ~1.3%. All row types (duct, fittings, registers, plenums) work correctly.
- **SKU translation via `mapped_parts.csv`** — deterministic catalog lookup, produces manufacturer SKU + supplier code per line. Falls back to passthrough for unknown generics.
- **Contractor profile system** — per-contractor supplier prefs, markup tiers, consumables config, pricing overrides, all editable via the SPA. No code changes to onboard a new contractor.
- **Consumables auto-calc** — mastic, foil tape, flex tape, screws, plus any custom items. Contractor-configurable multipliers with sensible system defaults.
- **PDF / XLS / SPA all show the same data** — recently aligned. Column set, sections, Quick Order Summary, Duct Cuts, Equipment Specs consistent across all three renderers.
- **Pricing edits round-trip** — inline pricing edits persist to `contractor_overrides` and apply automatically on future BOM builds for that contractor.
- **AHRI spec enrichment** — every equipment line gets SEER / HSPF / AFUE / capacity / AHRI ref number from `procalcs-catalog`, when the model matches an entry there.

### Working but brittle (this is what Ghidra should reduce)
- **`.rup` binary parsing** — walks UTF-16 strings and pattern-matches. Every recent bug traced to a file-format quirk we didn't know about (odd byte alignment, models outside EQUIP entries, template-vs-instance ambiguity). Works on the two files we've verified; new files can surface new quirks.
- **Equipment model detection** — hardcoded regex table of known manufacturer prefixes (Trane 5TAM/5TTV/BAYE, Goodman GSX/GMV/HKR, Carrier 24/25/FV4, Rheem RA1/RH1). A file with an unlisted manufacturer would silently produce no equipment.
- **Fitting quantities** — currently AI-estimated for the AI-path (not the `.xls` path). The `.xls` path uses exact Wrightsoft counts.
- **Room / branch attribution** — we parse room names from `BALDUCT` but don't cleanly attribute each duct run to a specific room. Contractors have asked for this.

### Not yet built (out of scope for RE — for context)
- **Automated Wrightsoft → BOM import** (this is what the Ghidra pass unblocks).
- **Contractor logo upload + branded sign-in flow.**
- **Multi-project batch mode** — one contractor uploading N projects at once.
- **Wrightsoft version pinning / detection** — we don't currently detect which Wrightsoft version generated a `.rup`, so future Wrightsoft updates could silently break parsing.
- **Scheduled AHRI refresh** — runbook exists; automation doesn't.
- **Windows COM/plugin integration with Wrightsoft** — dependent on what you find during RE.

---

## Two-service architecture — how procalcs-bom and procalcs-catalog fit together

Both bundles are in the handoff package. This section explains the split so you know which one your findings affect.

### procalcs-catalog (the reference service)
- Owns the equipment library. Not opinionated about any single contractor.
- **Data:** Wrightsoft's `manufacturers.csv`, `categories.csv`, `generic_parts.csv`, `mapped_parts.csv`, `DFUnit.csv`, `fitting_template.csv`, plus the AHRI-certified equipment tree (~70 manufacturers, ~1.4M rows).
- **Storage:** Cloud SQL Postgres. Every row is versioned by `batch_id + is_current` so refreshes are non-destructive.
- **Interface:** REST API (`/api/v1/catalog/ahri/{product_type}`, `/api/v1/catalog/dfunit`, `/api/v1/catalog/mapped-parts`, etc.). Read-only from the outside.
- **Refresh path:** `python -m scripts.import_catalog --source /path/to/Catalogs` (documented in `procalcs-catalog/docs/ahri-refresh.md`).
- **Deployed as:** `procalcs-catalog` Cloud Run service (prod + staging), stateful backing is Cloud SQL.

### procalcs-bom (the BOM engine — this is where the parser lives)
- Owns per-contractor BOM generation. Consumes procalcs-catalog data via HTTP.
- **Data of its own:** per-contractor `client_profiles`, `contractor_overrides` (pricing / SKU corrections), `bom_runs` (persisted BOM outputs for the `?run=<id>` URL feature), `rup_duct_totals` (cached user-entered LF per RUP SHA-256).
- **Storage:** Cloud SQL Postgres, separate database instance from procalcs-catalog.
- **Interface:** REST API mostly consumed by the SPA (`procalcs-designer-desktop`). Key endpoints:
  - `POST /api/v1/bom/from-wrightsoft` — upload .xls (+ optional .rup), get JSON BOM
  - `POST /api/v1/bom/render-pdf` / `/render-xls` — render an already-built BOM as file
  - `GET/POST /api/v1/profiles/<id>` — CRUD contractor profiles
  - `GET/POST /api/v1/contractor-overrides` — CRUD per-contractor SKU/price overrides
  - `GET /api/v1/bom-runs/<id>` — hydrate a persisted BOM run
- **Deployed as:** `procalcs-hvac-bom` Cloud Run service (prod + staging).

### The two together — request flow

Simplified path for a "Build BOM" click on the SPA:

```
[SPA]                                             [procalcs-bom]                     [procalcs-catalog]
Contractor uploads BOM.xls + .rup ────────────►   /api/v1/bom/from-wrightsoft
                                                     │
                                                     ├─ Parse .xls line items
                                                     ├─ For each line's generic_id:
                                                     │    lookup_skus_for_generic(gen_id) ────► /api/v1/catalog/mapped-parts?generic_id=...
                                                     │                                     ◄──── manufacturer SKU + supplier code
                                                     │
                                                     ├─ Parse .rup for equipment models (rup_parser.py)
                                                     ├─ For each equipment model:
                                                     │    lookup_ahri_by_model(model) ─────────► /api/v1/catalog/ahri/AC?condenser_model=...
                                                     │                                     ◄──── SEER, HSPF, capacity, AHRI ref no
                                                     │
                                                     ├─ Load contractor profile (own DB)
                                                     ├─ Apply per-contractor pricing overrides (own DB)
                                                     ├─ Compute Quick Order Summary, Duct Cuts,
                                                     │    consumables math (all in-process, own logic)
                                                     ├─ Persist as bom_runs row (own DB)
                                                     └─ Return JSON BOM ─────────────────────────►
Result renders
```

Key point for your work: **all Wrightsoft parsing lives in `procalcs-bom`. `procalcs-catalog` is a passive reference service and is not affected by Ghidra findings.** You can safely ignore `procalcs-catalog` unless you need to understand where equipment specs come from.

### Why procalcs-catalog is in the bundle at all

Two reasons:
1. **Optional context** — if you want to see how equipment specs flow (e.g., "where does SEER 20.6 come from on the Trane 5TTV0X48A1?"), it's in `procalcs-catalog/backend/models/ahri_unit.py`.
2. **AHRI refresh runbook** — the doc I mentioned earlier, at `procalcs-catalog/docs/ahri-refresh.md`, might be relevant if RE surfaces a new equipment-data source we haven't tapped.

You don't need to run procalcs-catalog locally. The parser you'll be improving runs standalone — it doesn't call the catalog API to do its job; that call happens later in the BOM-generation flow, downstream of the parser.

---

## What we already know about the `.rup` format (empirically)

Do NOT re-derive this from scratch — use it as your starting map and confirm/correct with Ghidra.

### Header
- First bytes are UTF-16 LE: `.W.S..r.s.u..W.S.F..0.0.0.4.` (magic + format version, best we can tell).
- 5+ MB typical file size for a single-family residential project (79th Ct is 5.6 MB, Ally is 1.9 MB).

### Section structure
- Sections are delimited by ASCII-style tags encoded in UTF-16 LE:
  - `!BEG=SECTIONNAME` opens a section
  - `!END=SECTIONNAME` closes it
- Sections we've identified and use:

| Section    | Contents                                                             | Reliability |
|------------|----------------------------------------------------------------------|-------------|
| `EQUIP`    | Equipment records — MIXED catalog templates and per-instance entries | HIGH (structural) |
| `ZEQUIP`   | Per-zone equipment placement                                         | LOW (mostly `PEAKCV/PACKAGE` on files we've seen — semantics unclear) |
| `DUCT`     | Duct records                                                         | MEDIUM |
| `DUCTRUN`  | Individual duct run definitions                                      | MEDIUM |
| `DTYPREF`  | Duct type preferences (Sheet metal / Vinyl flex / Rectangular fiberglass counts) | HIGH |
| `DREGINFO` | Register info                                                        | LOW |
| `BALDUCT`  | Room / branch context — where our room-name enumeration comes from   | MEDIUM |
| `ECDUCTSYS`| System-level duct data                                               | LOW |
| `FITNG`    | Fittings (24 entries typical, but not yet wired to the BOM)          | HIGH — mine this in Ghidra! |

### The two hard bugs we've hit — worth confirming structurally
Both of these were empirical fixes. Confirming or refuting them via Ghidra would let us retire fragile heuristics.

1. **Odd-alignment strings.** Some UTF-16 string fields land at ODD byte offsets, not even. Our string extractor originally walked bytes 2 at a time starting at offset 0 — silently dropped ~50% of Trane model numbers on any file where Wrightsoft happened to write them at an odd offset. On 79th Ct, `5TTV0X48A1` was even-aligned (2 hits, found), `5TTV0X60A1` was odd-aligned (2 hits, missed). We now walk both and interleave by byte position. **Ghidra should tell us WHY Wrightsoft writes some strings at odd offsets — is it record padding, a struct alignment quirk, or something else?**

2. **Template vs instance EQUIP entries.** Real per-instance EQUIP entries reference the manufacturer name TWICE (e.g., `Trane\n` then `Trane` — a display name plus a code marker). Catalog-template entries reference it only ONCE. This lets us filter templates out, but the mechanism is empirical. **Ghidra should tell us what the two Trane tokens actually mean — is one an FK/index and one a display string?**

### File-variant quirks we've observed

On some files (79th Ct-style), placed-instance model numbers live inside EQUIP entries. On others (Ally-style), the EQUIP section only contains single-line catalog labels ("Split AC", "Gas furnace") and the actual placed-instance models float as free-standing UTF-16 strings elsewhere in the file. **We don't know why the difference exists — Wrightsoft template? File-format version? User workflow variant?** This is a first-class question for Ghidra.

### Model prefix patterns we recognize (Trane / Goodman / Carrier / Rheem)

| Prefix       | Type         | Manufacturer |
|--------------|--------------|--------------|
| `5TAM*` / `5TEM*` / `5TFC*` | Air handler | TRANE |
| `5TTV*` / `5TWV*`           | Condenser   | TRANE |
| `BAYE*`                     | Heat kit    | TRANE |
| `GSX*` / `GSZ*`             | Condenser   | GOODMAN |
| `GMV*` / `GMS*`             | Furnace     | GOODMAN |
| `AVPTC*` / `ARUF*`          | Air handler | GOODMAN |
| `HKR*`                      | Heat kit    | GOODMAN |
| `24*` / `25*`               | Condenser   | CARRIER |
| `FV4*` / `FE4*`             | Air handler | CARRIER |
| `58*` / `59*`               | Furnace     | CARRIER |
| `RA1*`                      | Condenser   | RHEEM |
| `RH1*`                      | Air handler | RHEEM |

If Wrightsoft has a structural manufacturer/model table inside the binary that we could pull instead of pattern-matching, that would let us drop these heuristics entirely.

---

## Test files — expected values

Two real project files with known expected outputs. These are the ground-truth references.

### File 1 — `79th Ct Residence Load Calcs.rup`
Location on the Windows box: whatever path Gerald has synced it to. On macOS it's at `/Users/geraldvillaran/Procalcs/RUPs/79th Ct Residence Load Calcs.rup`.

- Size: 5,612,983 bytes
- Systems: 2 (per project data)
- Zones: 12
- AHUs: 4 (per Wrightsoft's Equipment Schedule)
- CUs: 4
- Heat kits: 4 (one per AHU)

Expected equipment extraction (5 unique Trane models):
| Model         | Type        | Wrightsoft schedule qty |
|---------------|-------------|-------------------------|
| 5TAMXD07AV51  | Air handler | 2 (AHU-1, AHU-3)       |
| 5TAMXD06AV41  | Air handler | 2 (AHU-2, AHU-4)       |
| 5TTV0X60A1    | Condenser   | 2 (CU-1, CU-3)         |
| 5TTV0X48A1    | Condenser   | 2 (CU-2, CU-4)         |
| BAYEAAC08BK1  | Heat kit    | 4                       |

Current parser output (as of 2026-07-03): matches all 5 with correct qty after this month's fixes.

### File 2 — `Ally Residence (Main House).rup`
Location on the Windows box: sync from `/Users/geraldvillaran/Procalcs/RUPs/Ally Residence (Main House).rup`.

- Size: 1,926,926 bytes
- Systems: 2
- AHUs: 2

Expected equipment extraction (6 unique Trane models):
| Model                   | Type        | Qty |
|-------------------------|-------------|-----|
| 5TAMXB02AV21            | Air handler | 1   |
| 5TAMXD07AV51            | Air handler | 1   |
| 5TWV8X24A1              | Condenser   | 1   |
| 5TWV8X60A1              | Condenser   | 1   |
| BAYEA(13/AC)08++1       | Heat kit    | 1   |
| BAYEA(13/AC)10++1       | Heat kit    | 1   |

Note the parenthesized heat-kit model format — real Trane part numbers can contain `(`, `)`, `/`, `+` characters. Our regex allows those explicitly for the BAYE prefix. Ghidra should confirm whether Wrightsoft stores these as literal strings or as some encoded form.

---

## What we need from Ghidra

Ranked by impact.

### Must-have (unblocks integration work)

1. **Documented file-header structure.** Magic bytes, format version field, size fields, offset table (if any).
2. **Section table.** Does the file have an index of `!BEG=`/`!END=` positions? If yes, we don't need to scan the whole file.
3. **EQUIP record structure.** Field-by-field layout of a per-instance EQUIP record. Confirm what the two "Trane" tokens really are. Confirm what makes an entry a "template" vs an "instance." Confirm the shape well enough that we can iterate records structurally instead of via string extraction.
4. **Answer the alignment question.** Why do some UTF-16 fields land at odd offsets? Struct padding? Variable-length record header?
5. **Answer the file-variant question.** On some files (Ally) models are outside EQUIP entries. Where are they structurally? Is there a ZEQUIP or SYSTEM record type we're missing?
6. **DUCTRUN / BALDUCT record structure.** We currently know these exist but we don't decode per-run duct data. For the per-piece Duct Cuts view we care about individual cut lengths + room/branch attribution. Documented offsets for these fields.
7. **FITNG record structure.** 24 entries typical, not wired to the BOM yet. Contains individual fitting placements. Documenting this would let us stop AI-estimating fitting counts.

### Nice-to-have (opens future work)

1. **Wrightsoft's own BOM generation logic.** How does Wrightsoft compute BOM.xls from the underlying `.rup`? If we can see the logic in the binary (or an accompanying DLL / plugin API), we might be able to skip re-implementing it.
2. **File-write hooks.** When does Wrightsoft flush its state to disk? Is there an on-save trigger we could subscribe to for auto-import?
3. **Any exported COM/API surface.** Wrightsoft has documented plugin points — confirm whether we can hook there directly instead of tailing a file directory.
4. **Version-string location.** So we can gate our parser on Wrightsoft version at run time.

---

## Downstream goal — automated import

Once you have the structural map:

- **Phase 1** — Rewrite `rup_parser.py` to walk the binary structurally instead of extracting UTF-16 strings and pattern-matching. Retire the odd-offset walker, the free-standing model scanner, the template-vs-instance mfr-line-count filter, and the prefix regex table. Each of those was a reactive fix for a format quirk we now understand structurally.

- **Phase 2** — Identify the Wrightsoft output surface (file save location, plugin hook, or API call) and build an auto-import path so a contractor doesn't hand-drop files. Options include: a Windows service watching a canonical `.rup` output directory; a Wrightsoft plugin that POSTs to our API on save; a scheduled sweep of a shared network drive.

- **Phase 3** — Add file-version awareness to the parser so future Wrightsoft updates don't silently break us. Ideally: pin a supported version list, log the version we're parsing, and refuse to process a version we don't recognize.

---

## What NOT to do

- **Don't rewrite the BOM Module.** The pricing, contractor-profile, Quick Order Summary, Duct Cuts, and consumables layers are stable and out of scope for this pass.
- **Don't try to reverse-engineer Wrightsoft's pricing.** Contractor pricing is per-contractor and overridden via `contractor_overrides` — we own that data.
- **Don't ship a parser rewrite from Ghidra alone without regression-testing against the two files above.** Every structural finding needs to reproduce the existing correct output before we retire the corresponding heuristic. The heuristics work today; they just aren't durable.
- **Don't touch `procalcs-catalog`.** That's the AHRI + Wrightsoft-catalog reference service, independent of `.rup` parsing.

---

## Deliverable

A structural spec document (markdown or otherwise) at `procalcs-hvac-upstream/docs/RUP_BINARY_FORMAT.md` covering:

1. File-header layout with field offsets, sizes, and types
2. Section index / table of contents (if any)
3. Per-section record layouts for at least: EQUIP, DUCTRUN, BALDUCT, DTYPREF, FITNG
4. Answered questions: alignment mystery, template-vs-instance mechanism, file-variant explanation
5. Any discovered API / plugin surface for auto-import

Cross-reference every finding against `procalcs-hvac-upstream/procalcs-bom/backend/utils/rup_parser.py` — where a structural fact would let us retire an existing empirical helper, call it out inline (e.g., "This retires `_scan_free_models` at line 543").

Once the spec lands, we'll plan Phase 1 rewrite as a follow-up task.

---

## Code references (paths on macOS side, sync as needed)

- `procalcs-hvac-upstream/procalcs-bom/backend/utils/rup_parser.py` — current empirical parser
- `procalcs-hvac-upstream/procalcs-bom/backend/services/bom_from_rup.py` — .rup → BOM lines path
- `procalcs-hvac-upstream/procalcs-bom/backend/services/bom_from_wrightsoft.py` — .xls → BOM lines path (with optional .rup merge)
- `procalcs-hvac-upstream/procalcs-bom/docs/data-sources.md` — data-source-of-truth contract (all engine changes consult this first)
- Test files: `~/Procalcs/RUPs/79th Ct Residence Load Calcs.rup`, `~/Procalcs/RUPs/Ally Residence (Main House).rup`, `~/Procalcs/RUPs/BOM.xls`, `~/Procalcs/RUPs/BOM - Ally.xls`

---

## Contact / synchronization

The BOM Module session (this side) is on macOS. Ping when:
- You have preliminary format findings — we'll spot-check them against the test files.
- You identify a Wrightsoft plugin/API hook — that changes the Phase 2 integration plan.
- You need clarification on any of the empirical behavior described here.

Standing between sessions: this side keeps the BOM Module stable and doesn't refactor `rup_parser.py` while your work is in flight — no merge conflicts, no duplicate effort.
