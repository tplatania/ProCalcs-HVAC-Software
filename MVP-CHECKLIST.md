# ProCalcs Designer Desktop — Road to MVP Checklist

> Generated: April 13, 2026
> Last updated: April 29, 2026 (post sample-RUP eval)
> Owner: Tom Platania (ProCalcs)
> Target launch: After 1-week testing period + sign-off

## Vision
Upload a Wrightsoft .rup file, get a complete, field-ready, branded BOM
with installation materials and contractor-specific pricing — in 60 seconds
instead of building it manually in a spreadsheet.

## Target User
ProCalcs design team (~11 people): Richard, Windell, Filipino designers.
Internal tool that produces a deliverable worth $50-$150 per project.

## Priority Tiers
- **P0 — Must Have (blocks launch):** Cannot go live without these.
- **P1 — Should Have (launch week):** Important but won't delay launch day.
- **P2 — Nice to Have (post-launch):** Planned but explicitly deferred.

---

## How far from "I upload RUP, app returns accurate BOM"?

**Updated 2026-04-29 (post Tom/Richard clarifications):**
**~2.5–3 weeks of focused work, all on internal capacity.** The previously
assumed contractor-spreadsheet roundtrip is no longer a blocker — Richard
confirmed that ProCalcs follows industry-standard BOM practice and general
knowledge is sufficient for the deterministic materials rules.

Eval ran 2026-04-29 against staging BOM service using 3 real RUPs from
designer Procalcs/RUPs/ folder. Artifacts archived at
`docs/eval-2026-04-29/`. Sample BOM target was the contractor's
`Lot 1 T075 Elm ACL` spreadsheet (21 line items across 3 sections —
Equipment / Duct System Equipment / Rheia Duct System Equipment, plus an
empty Labor placeholder).

| RUP | Parse | Generate | Items | vs Target |
|---|---|---|---|---|
| Easy (13th Ave ADU, 751 KB, Manual D / ducts only) | ✅ HTTP 200 — but only `project_info` + `building` + 487-char `raw_rup_context` | ❌ HTTP 400 — validator rejects empty equipment/ducts/fittings/registers | 0 | Cannot complete |
| Average (Ligon ADU, 1.8 MB, Manual D) | ✅ HTTP 200 — same shape, no `project_name`, 462-char context | ❌ HTTP 400 — same rejection | 0 | Cannot complete |
| Edge (79th Ct Residence, 5.4 MB, full load calcs) | ✅ HTTP 200 — **5 equipment + 37 rooms** + 1591-char context | ✅ HTTP 200 in 19.5 s | **46** ($23,162 cost / $29,267 price) | Ships, but structure mismatched |

The pipeline works **end-to-end on 1 of 3 sample RUPs** today. The richer
RUP the parser handled produces 46 items vs the contractor target's 22 —
more granular, but using generic categories (`duct`/`fitting`/
`equipment`/`register`/`consumable`) instead of the contractor's
sections (`Equipment` / `Duct System Equipment` / `Rheia Duct System
Equipment` / `Labor`) and lacking supplier SKUs (`GOODMAN AHVE24BP1300A`,
`PGM DRFg1712MI`, `RHEA 10-00-190`).

### Critical gaps surfaced

| Gap | Severity | Est. | Notes |
|---|---|---|---|
| Parser only extracts structured data from RUPs that include the FULL load-calc/equipment binary blocks. Manual D / ducts-only RUPs yield empty arrays. | **CRITICAL** | 10 h | `rup_parser.py` already builds `raw_rup_context` for every file — the data is there, the parser just doesn't promote it into structured arrays. |
| Validator rejects design_data when all 4 BOM-relevant arrays are empty, defeating the documented "AI estimates from `raw_rup_context`" hybrid path. | **CRITICAL** | 3 h | Loosen `validators.py` to also accept `raw_rup_context >= N chars`. |
| BOM output uses generic categories not the contractor's section structure (no `Rheia Duct System Equipment` section, no `Labor` section). | **HIGH** | 4 h | Sectioning lives in `bom_service.py:_format_line_items` and the PDF Jinja template. The new SKU catalog already declares the right sections (`section` field per item). |
| ✅ **In progress:** Supplier SKU catalog (GOODMAN/PGM/WSF/PRJ/RHEA). | — | 8 h remaining (was 15) | Starter catalog of 21 SKUs seeded from contractor sample → `procalcs-bom/backend/data/sku_catalog.json`. Loader live at `services/sku_catalog.py`. Remaining: tonnage→SKU variants for AHU/condenser/heat-kit, AI prompt updates so generated items reference real SKUs. |
| Rheia (small-diameter duct system) — Tom 2026-04-29: Rheia is **universal** across ProCalcs projects, lives in rules engine not profile overrides. 11 of 21 sample items are Rheia. | **HIGH** | 3 h (was 5) | Trigger keys built into the catalog (`rheia_in_scope`). Detection heuristic: small-diameter flexible duct in scope. |
| `materials_rules.py` deterministic engine for installation consumables (collars, hangers, mastic, tape, screws) and Rheia emission. | **HIGH** | 8 h (was gated; now internal) | Tom 2026-04-29: industry-standard practice is sufficient — no contractor spreadsheet needed. Engine reads the SKU catalog + design_data and emits line items per the `quantity` modes declared in the catalog. |
| Accuracy validation against real projects (Richard spot-check vs manual BOM). | **HIGH** | 4 h dev + ~1 week trial | Trial gates final sign-off. |

**Realistic path to "accurate BOM end-to-end":**

```
Week 1  — Validator hybrid path + parser robustness   → Easy & Avg unblock
Week 1  — Section reformat + SKU prompt updates       → output matches target shape
Week 1  — materials_rules.py engine + Rheia trigger   → deterministic consumables + 11 Rheia lines
Week 2  — Richard spot-checks 5 real projects, iterate
Week 3  — 1-week trial + sign-off ceremony
```

All internal — no external blockers. Total: **~2.5–3 calendar weeks**
from start of internal work to launch sign-off.

---

## Checklist

### Auth & Access
- [x] **P0:** Google OAuth restricted to `@procalcs.net` domain *(commits `fb84b18`, `3dca9e4` — domain gate verifies email suffix, not Workspace `hd` claim)*
- [x] **P0:** Individual accounts for each team member (~11 concurrent users) *(JWT session per user)*
- [ ] **P2:** Admin panel for user management — not needed at launch

### Core Features — .rup to BOM Pipeline
- [x] **P0:** .rup file upload replaces JSON textarea *(SPA dropzone + adapter proxy + `parse-rup` endpoint shipped Phase C, commits `485df30`, `7bed2c0`)*
- [/] **P0 PARTIAL:** Parser extracts all design data from .rup binary
  - [x] Project metadata, building type, duct location: works on all 3 sample RUPs
  - [x] Equipment + rooms: works on Edge (full load calc) RUPs only
  - [ ] **GAP:** Equipment/rooms not extracted from Manual D / ducts-only RUPs (Easy + Avg cases). Eval 2026-04-29 confirms.
  - [ ] **GAP:** Duct runs, fittings, registers — empty arrays for ALL 3 sample RUPs even when the data is in the RUP
- [ ] **P0:** Validator hybrid path — accept design_data with only `raw_rup_context` populated and let AI fill structured arrays *(currently the validator hard-rejects, defeating the parser docstring's documented design)*
- [ ] **P0:** Installation materials rules engine in Python — hardcoded, deterministic, not AI-estimated
  - Collars per duct run, tie straps per connection, hangers per LF, mastic/tape ratios
  - Rules validated by contractor via spreadsheet (see Installation Materials Validation below)
- [x] **P0:** Contractor Intelligence Profiles — pricing, brands, markups, part name overrides per client *(full CRUD + extended fields landed in commits `c96620e`, `7687749`. 2 profiles seeded: ProCalcs Direct + Beazer Homes AZ.)*
- [/] **P0 PARTIAL:** BOM generation applies profile to extracted design data + installation materials rules
  - [x] Profile applied (pricing/markup/overrides) — Edge case eval produced $23,162 cost / $29,267 price
  - [ ] **GAP:** Output uses generic categories (`duct`/`fitting`/`equipment`/`register`/`consumable`) not contractor sections (`Equipment` / `Duct System Equipment` / `Rheia Duct System Equipment` / `Labor`)
  - [ ] **GAP:** No supplier SKUs (`GOODMAN AHVE24BP1300A`, `PGM DRFg1712MI`, `RHEA 10-00-190`) — target sample BOM has 22/22 items with supplier-specific SKUs
  - [ ] **GAP:** Rheia small-diameter duct system not detected or emitted (11 of 22 lines in target sample)
- [ ] **P1:** Designer review/edit step — adjust quantities, add/remove items before finalizing
- [x] **P1:** Output mode selection (Full BOM, Materials Only, Client Proposal, Cost Estimate) *(5 modes shipped)*

### PDF-to-CAD Cleanup Tool (launches WITH BOM)
- [x] **P0:** DXF upload and entity-type cleanup working end-to-end *(`cleaner_routes.py` + `cleaner_service.clean_dxf`)*
- [x] **P0:** Smart INSERT Filter — keeps doors + ventilation, strips furniture/electrical/plumbing *(`insert_filter.py`)*
- [/] **P0 PARTIAL:** ODA File Converter wired up for DWG→DXF→clean→DXF→DWG pipeline *(config path exists, subprocess call still a TODO at `cleaner_service.py:172–185`)*
- [ ] **P0:** Test with real DWG files from designers *(test_fixtures/ contains only .gitkeep — needs Richard to send 3–5 real DWGs)*
- [ ] **P0:** Output file works cleanly in Wrightsoft — no performance issues *(gated on real-DWG test)*
- [ ] **P1:** Phase 2 scanned blueprint handling — AI vision, post-launch

### BOM Output & Deliverable
- [x] **P0:** Branded PDF output with ProCalcs logo *(commit `9fa39e5` — WeasyPrint + Jinja2 template, dedicated `/render-pdf` endpoint cached so Anthropic isn't re-hit)*
- [/] **P0 PARTIAL:** Professional layout — *(template ships and renders, but section structure doesn't match contractor target — see Core gap above)*
- [x] **P1:** CSV export
- [x] **P1:** Print-friendly view
- [ ] **P2:** Tiered pricing per output mode

### Profile Management
- [x] **P0:** Create/edit/delete contractor profiles
- [x] **P0:** Profile fields: supplier, pricing per unit, markup tiers, brand preferences, part name overrides
- [ ] **P1:** Search/filter on profile list
- [ ] **P2:** Profile import/export for bulk setup
- [ ] **P2:** Job history per profile

### Data & Integrations
- [x] **P0:** Firestore for contractor profiles
- [ ] **P0:** Cloud SQL Postgres for app data — *(open question: actually needed? Profiles live in Firestore; job history is P2. Was deleted in mockups retirement.)*
- [x] **P0:** Claude API for BOM quantity estimation where parser data is sparse *(hybrid prompt reads `raw_rup_context`)*
- [ ] **P2:** Supplier API integrations (Ferguson, Winsupply) for live pricing

### Infrastructure & Deployment
- [x] **P0:** Cloud Run deployment *(all three services live: api, bom, cleaner)*
- [x] **P0:** Secret Manager for API keys *(Anthropic + Flask secret + new `SERVICE_SHARED_SECRET` for inter-service auth on staging)*
- [x] **NEW (post-MVP-checklist):** Hardened BOM service for cross-app consumption — shared-secret auth middleware, `/api/v1/health`, 25 MB body cap, CORS whitespace-tolerant *(commit `fe88d02`, deployed to `procalcs-hvac-bom-staging`)*
- [ ] **P1:** Minimum instance to avoid cold start latency
- [ ] **P2:** Custom domain (designer.procalcs.net or similar)
- [ ] **P2:** CI/CD pipeline
- [ ] **P2:** Staging vs production environments

### Trust & Polish
- ~~**P0:** Installation materials rules validated by real contractor~~ — **Resolved 2026-04-29 (Tom + Richard):** ProCalcs follows industry-standard practice; rules are seeded from industry knowledge + the contractor sample BOM. No external spreadsheet roundtrip needed.
- [ ] **P0:** 1-week testing period — Richard and Gerald run real projects daily
- [ ] **P0:** Accuracy spot-check against manual BOM process *(gated on SKU + sectioning + materials_rules fixes — eval 2026-04-29 confirmed the gaps)*
- [ ] **P1:** Loading states and error messages for all async operations
- [ ] **P1:** Graceful handling of corrupt/unsupported .rup files
- [ ] **P2:** Empty states for new users

### Launch & Sign-off
- [ ] **P0:** Richard confirms accuracy on real projects
- [ ] **P0:** Gerald confirms tech stability
- [ ] **P0:** Catherine approves for production use
- [ ] **P0:** Tom gives final go
- [ ] **P1:** Contractor validation of BOM accuracy

---

## Eval 2026-04-29 — Sample-RUP Test Results

### Inputs
- 3 real RUPs from `/Users/geraldvillaran/Procalcs/RUPs/`:
  - `(Easy) 13th Avenue South ADU Residence Ducts.rup` (751 KB)
  - `(Average Case) Ligon ADU Manual D.rup` (1.8 MB)
  - `(Edge Case) 79th Ct Residence Load Calcs.rup` (5.4 MB)
- Target output: `(Sample BOM) Lot 1 T075 Elm ACL BOM.xls` (22 line items, 4 sections)

### Pipeline run
Hit `procalcs-hvac-bom-staging-69864992834.us-east1.run.app` directly.
Artifacts saved at `docs/eval-2026-04-29/`:
- `parse_EASY.json` / `parse_AVG.json` / `parse_EDGE.json` — output of `/parse-rup`
- `gen_EDGE.json` — full BOM generated from the Edge case (only one to clear validator)

### Findings
1. **Parser hybrid is the right design but underused.** Every parse output includes `raw_rup_context` (487/462/1591 chars) that lists CFM values, duct dimensions, and (for richer RUPs) equipment names. The downstream prompt is meant to read this when structured arrays are sparse. But validator rejects before AI sees it on Easy + Avg.

2. **Edge case proves the pipeline works when fed enough.** With 5 AHUs and 37 rooms parsed structurally, `/generate` returned 46 items in 19.5 s, totalling $23,162 cost / $29,267 price across 5 categories.

3. **Output format diverges from contractor target.** Sample target uses brand-supplier sections (GOODMAN equipment, PGM/WSF duct, RHEA Rheia parts, PRJ ERV) and per-item supplier SKUs. Edge output uses generic descriptions ("6\" round galvanized duct"). Profile overrides exist in the schema but aren't yielding the right shape.

4. **Rheia system support is missing.** 11 of 22 lines in target sample are RHEA-prefixed Rheia small-diameter parts (3-in duct, ferrules, take-offs, boots, hanger bars, ceiling diffusers). No equivalent in Edge output.

### Recommended next-step ordering (revised 2026-04-29)
1. ✅ **DONE:** Starter SKU catalog (21 items) + loader at `data/sku_catalog.json` + `services/sku_catalog.py`.
2. (3 h) Loosen validator to accept `raw_rup_context >= N` as a valid fallback. Unblocks Easy + Avg paths today; AI takes over from narrative.
3. (10 h) Extend `rup_parser.py` to fish `duct_runs` / `registers` / `equipment` / `fittings` from Manual D / ducts-only RUP shapes. The data is in the binary; the string-walker just doesn't reach it on those file types.
4. (8 h) Build `materials_rules.py` engine that walks the SKU catalog and applies each entry's `trigger` + `quantity` rule to a parsed `design_data`. Wire into `bom_service.generate()` so the deterministic items ship alongside (and reconcile with) AI-estimated ones.
5. (3 h) Rheia detection — set `rheia_in_scope` based on small-diameter flexible duct in `design_data.duct_runs` or context heuristic.
6. (4 h) Reformat `bom_service._format_line_items` + PDF Jinja template to emit contractor sections (Equipment / Duct System Equipment / Rheia Duct System Equipment / Labor) using `sku_catalog.sections()` as the canonical order.
7. (8 h) AI prompt updates so generated items reference real catalog SKUs. Tonnage→SKU map for AHU / condenser / heat-kit variants.
8. (~1 week) Richard's 5-project spot-check + iteration.
9. (~1 week) Trial + sign-off ceremony.

---

## Deferred (Explicitly NOT MVP)
- Landing page / marketing site
- Stripe / billing / payments
- Analytics / tracking
- Customer support widget
- Terms of Service / Privacy Policy
- Mobile responsive
- Validator
- Job history / "my previous BOMs"
- Scanned blueprint AI vision engine

## Open Questions
- ~~What are the complete installation materials rules?~~ **Resolved 2026-04-29:** industry-standard practice + iterating on real-project samples. No contractor spreadsheet needed.
- Does the .rup parser extract ALL BOM-relevant data, or are there gaps? **Eval 2026-04-29 answer: NO. Easy + Avg yield empty structured arrays.** Parser robustness work scheduled (10h).
- What does the branded PDF template look like? *(Currently shipped; doesn't match contractor target sectioning — section reformat scheduled (4h).)*
- How many output modes does the team actually need? *(5 built)*
- Cold start latency acceptable for internal use? *(Test during 1-week trial)*
- ~~Is Rheia a supported system across all designer projects, or contractor-specific?~~ **Resolved 2026-04-29:** universal across ProCalcs projects. Lives in rules engine, not profile overrides.
- ~~Where do the supplier SKUs come from?~~ **Resolved 2026-04-29 (interim):** seeded from contractor sample BOM into `procalcs-bom/backend/data/sku_catalog.json` (21 items, 5 suppliers). Followup needed on long-term source — static catalog vs Firestore vs supplier API. AI prompt will reference the catalog when emitting line items.
- **NEW:** Tonnage→SKU variants for AHU, condenser, and electric heat kit. Catalog has one SKU per equipment type today; real selection should depend on AHU tonnage from RUP equipment table. Need a tonnage→SKU map per supplier (e.g. GOODMAN AHU 2-ton vs 3-ton vs 5-ton SKUs).

---

## Installation Materials — Approach (revised 2026-04-29)

> **Tom + Richard, 2026-04-29:** ProCalcs follows industry-standard BOM
> practice. No contractor spreadsheet roundtrip is needed — general
> industry knowledge plus the patterns visible in real contractor sample
> BOMs is sufficient to seed the rules. Refine quantity rules as real
> projects expose edge cases.

### What this means
The BOM tool calculates installation materials (collars, tie straps,
mastic, tape, hangers, condensate line materials, etc.) from hardcoded
Python rules — deterministic, not AI-estimated. The rules are seeded
from industry standards and the SKU catalog.

### Where it lives
- **`procalcs-bom/backend/data/sku_catalog.json`** — 21 SKUs seeded from
  the contractor sample BOM (`Lot 1 T075 Elm ACL`). Each entry declares
  its section, supplier, trigger condition, and quantity rule. Editing
  this JSON does not require code changes.
- **`procalcs-bom/backend/services/sku_catalog.py`** — loader + lookup
  functions (`all_items`, `get`, `items_for_section`,
  `items_with_trigger`, `sections`).
- **`procalcs-bom/backend/services/materials_rules.py`** *(to build)* —
  the engine that maps `design_data` → emitted line items by walking
  the catalog and applying each entry's `trigger` + `quantity` rule.

### Validation timeline (revised)
- [x] SKU catalog seeded from contractor sample BOM (21 items)
- [x] Catalog loader live with section / trigger lookup helpers
- [ ] `materials_rules.py` engine — emit line items for any design_data
- [ ] Wire engine into `bom_service.generate()` so deterministic items
      ship alongside AI-estimated ones
- [ ] Richard spot-checks rules engine output against manual BOM on
      3–5 real projects
- [ ] Rules + catalog locked for launch

---

## Current State (what Gerald has built — updated 2026-04-29)
- ✅ Designer Desktop SPA deployed to Cloud Run
- ✅ .rup file upload and parsing — works on rich RUPs, partial on Manual D / ducts-only RUPs
- ✅ Contractor profiles CRUD in Firestore (2 demo profiles seeded)
- ✅ AI BOM generation with Claude API — verified end-to-end on Edge sample (46 items, $23k cost)
- ✅ Profile switching changes pricing/brands/totals
- ✅ CSV export and print view
- ✅ 5 output modes (Full, Materials Only, Labor+Materials, Client Proposal, Cost Estimate)
- ✅ Google OAuth (@procalcs.net restriction)
- ✅ Branded PDF output (WeasyPrint + Jinja2)
- ✅ BOM service hardened for cross-app use (shared-secret auth, versioned health, body cap)
- ✅ **NEW 2026-04-29:** Supplier SKU catalog seeded (21 items, 5 suppliers, 3 sections) at `data/sku_catalog.json` + loader at `services/sku_catalog.py`
- ⬜ `materials_rules.py` engine — walks SKU catalog + design_data and emits line items per declared trigger/quantity rules
- ⬜ Parser coverage for Manual D / ducts-only RUPs (gap surfaced in eval 2026-04-29)
- ⬜ Validator hybrid path through `raw_rup_context`
- ⬜ Output sectioning matches contractor target (Equipment / Duct System Equipment / Rheia Duct System Equipment / Labor)
- ⬜ AI prompt updates so generated items reference catalog SKUs
- ⬜ Rheia trigger detection in design_data (catalog supports it; detection logic still to write)
- ⬜ Designer review/edit step before finalizing

---
*Last eval: 2026-04-29 against 3 real RUPs + 1 contractor sample BOM. See `docs/eval-2026-04-29/` for raw artifacts.*
*Generated from road-to-mvp.md brainstorming session — Tom + Claude, April 13, 2026*
