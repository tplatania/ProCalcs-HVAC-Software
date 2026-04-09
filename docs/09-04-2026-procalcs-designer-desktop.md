09-04-2026 Updates

🔧 In Progress:
Wiring the Designer Desktop SPA to the new `.rup` upload flow end-to-end
for Richard and Tom's user test — upload `.rup` → preview extracted data →
pick client profile → generate priced BOM → review and export.

✅ Done Today

Project: ProCalcs Designer Desktop (`procalcs-designer`)

1. Recovery Investigation & Root Cause (`experiments/rup-parsing`)

Problem: User reported the Designer Desktop staging URL
(`procalcs-hvac-api-69864992834.us-east1.run.app`) was serving 404. The
previous session had retired the `mockups/` monorepo earlier the same
day and the retirement plan marked a 404 on this URL as a success
signal — but that URL was the actual Designer Desktop shell used for
the upcoming Richard/Tom demo. Scoping mismatch in the retirement.

Solution: Traced it to the retirement commit (`5961e0d`) which tore
down `procalcs-hvac-api` Cloud Run, `procalcs-hvac-pg` Cloud SQL, and
the two `procalcs-hvac-database-url*` secrets. The prior session had
(mis)built the Cloud Run image from inside `mockups/`, so deleting the
directory killed the demo surface. `procalcs-hvac-bom` and
`procalcs-hvac-cleaner` were both still 200 green — only the shell was
gone. Full investigation + findings written up in
`C:\Users\ermil\.claude\plans\bright-noodling-kay.md`.

2. Designer Desktop Recovery as Standalone App (`procalcs-designer/`)

Problem: The Designer Desktop SPA source code (shadcn/ui bom-dashboard,
api-server routes, Drizzle schema, Dockerfiles) was built from inside
`mockups/` which is supposed to be a UI-component reference only, not
a buildable app. Anything that pulls from `mockups/` at build time
blocks future deletion of that directory.

Solution: New top-level `procalcs-designer/` directory, parallel to
`procalcs-bom/` and `procalcs-pdf-cleaner/`. Copy-assembled the SPA
source (pages, 55 shadcn/ui components, hooks, styles, layout,
profile-form) from a fresh `mockups/` snapshot the user placed at
`C:\Users\ermil\projects\mockups\` (git HEAD `cdb8509` — matches the
parent repo's old submodule gitlink). Rewrote imports so
`@workspace/api-client-react` routes through a new local
`src/lib/api-hooks.ts`. Dropped pnpm catalog/workspace protocols in
favor of plain `npm install` for Windows friendliness. No Cloud SQL, no
Drizzle, no Secret Manager — a thin Express 5 adapter (`server/`) does
structural translation between the SPA's flat camelCase shape and
Flask's nested `ClientProfile` and computes `/api/dashboard/summary` on
the fly instead of persisting it.

Multi-stage Dockerfile: Node 20 builder → Vite SPA build + esbuild
server bundle → Alpine runtime on `:8080`. Client bundle comes out at
599 KB (~183 KB gzipped).

3. Decoupling Verified & Deployed (`procalcs-hvac-api`)

Problem: How do we prove `procalcs-designer/` has zero build-time
dependency on `mockups/` before telling the user it's safe to delete?

Solution: Ran a decoupling test — renamed
`C:\Users\ermil\projects\mockups` → `mockups.hidden`, blew away
`dist/` and `dist-server/`, reran `npm run build`. Output was
bit-for-bit identical (599.87 kB JS, same hash), proving every import
resolves inside `procalcs-designer/`. Deployed via
`gcloud run deploy procalcs-hvac-api --source . --region us-east1`.
Cloud Run reused the original project-number hash on recreate, so the
staging URL is bit-for-bit the same as the deleted one:
`https://procalcs-hvac-api-69864992834.us-east1.run.app`. All smoke
tests green — SPA shell, `/api/healthz`, `/api/client-profiles`,
`/api/dashboard/summary`, wouter client-side fallback, JSON 404 on
unknown `/api/*` paths. User then deleted the local `mockups/` copy;
rebuilt again to confirm no regression.

Commit `a42d06c` on `main`. 90 files, 16,606 insertions.

Project: `procalcs-bom` — .rup Upload Pipeline

4. Phase A — Unblock the MVP (`experiments/rup-parsing`)

Problem: Several independent things were all blocking any end-to-end
`.rup` → BOM demo: Firestore was empty (no profiles to pick against),
`experiments/rup_extractor.py` crashed on Windows stdout when printing
the "Room → AHU" arrow (cp1252 UnicodeEncodeError), the Room→AHU regex
was catching binary section markers like `ECDUCTSYS`/`SJD` as rooms,
and the `parse_sections` lazy match sometimes bled one section's body
into the next (`FLCLTY[1]` literally captured `!BEG=RHPANEL\nFS-STAPLE`).

Solution:
- Forced UTF-8 on `sys.stdout` via `reconfigure(encoding="utf-8", errors="replace")` at module import — no-op on Unix and on Windows consoles already at UTF-8.
- Added a `NON_ROOMS` whitelist filter rejecting all known section names + anything starting with `AHU`. The Enos sample now returns 32 real rooms instead of 38 (rooms + 4 garbage + 2 dupes).
- Replaced the regex with a balanced backreference (later rewritten again in Phase B after hitting the `JOBINFOK → JOBINFO` drift quirk — see Phase B).
- New one-shot seeder `procalcs-bom/scripts/seed_demo_profile.py` that POSTs to the live Flask `/api/v1/profiles/` endpoint — no Firestore SDK, no service account required. Seeded "ProCalcs Direct" using Tom Platania's JOBINFO details (`tom@procalcs.net`, license `CAC1815254` in notes), Ferguson supplier, 15% / 20% / 30% markup tiers, Carrier/Goodman/Rectorseal/Nashua/Atco brands, plus two sample part-name overrides. `--also-beazer` flag seeds a second "Beazer Homes - Arizona" profile for later.
- Added `procalcs-designer/public/favicon.svg` so the browser console stops logging 404s.

Verified: `curl /api/dashboard/summary` against the live adapter now
returns `totalProfiles: 1, activeProfiles: 1, suppliersCount: 1,
totalPartOverrides: 2`.

Phase A1 note: the adapter URL drift
(`/api/v1/client-profiles/ → /api/v1/profiles/`) that I thought would
need fixing was already corrected in commit `a42d06c` — verified by
re-reading `clientProfiles.ts` and live-probing the adapter before
touching anything.

Commit `85d1833`, merged to main.

5. Gerald Handoff Spec Reconciliation (`docs/GERALD_HANDOFF_RUP_UPLOAD.md`)

Problem: Mid-session Tom pushed commit `c79bbba` — a spec for the
exact `.rup` upload flow I was about to build, but with three
material differences from my plan: it points at a different starting
parser (`phase1_validator/reference_code/rup_parser.py`, not
`experiments/rup_extractor.py`), it picks Approach A (binary parse)
over my chosen rich-text passthrough strategy, and it specifies a
two-step UX (parse → preview → confirm → generate) rather than a
one-shot endpoint.

Solution: Re-read the spec carefully, confirmed that the hybrid clause
inside Approach A (*"Use Approach A for everything the binary parser
can extract reliably. Fall back to [AI text] only for data that's too
deeply buried"*) is the right middle ground. Surfaced the three-way
decision to the user, got Hybrid / consolidate-into-procalcs-bom /
keep-using-Enos-sample confirmation, updated
`bright-noodling-kay.md` with the spec-aligned plan, and proceeded.

6. Phase B — Canonical `.rup` Parser (`procalcs-bom/backend/utils/rup_parser.py`)

Problem: Two competing parser prototypes existed — my narrative-text
`experiments/rup_extractor.py` and the older structured-dict
`phase1_validator/reference_code/rup_parser.py`. Neither matched the
BOM engine's `design_data` contract or Tom's spec shape. The spec
wants duct_runs, fittings, equipment, registers, rooms, building info,
and a raw context for AI fallback — a consolidation is needed.

Solution: New 570-line canonical parser at
`procalcs-bom/backend/utils/rup_parser.py`, consolidating the best
ideas from both earlier prototypes:

- **UTF-16 byte-level string extraction with min-length filter** (from
  `experiments/`) — tolerates the binary chunks interspersed between
  ASCII runs in Wrightsoft's format.
- **BEG/END section scanner with stateful matching** — the earlier
  `!END=\1` backreference broke on the real-world quirk that
  `!BEG=JOBINFOK` is closed by `!END=JOBINFO` (the `K` suffix is only
  on the opener). The new scanner walks each `!BEG=`, scans forward
  for an `!END=` whose name equals *or is a prefix of* the BEG name,
  stopping at the next `!BEG=` to prevent body bleed. Handles the
  drift gracefully.
- **Structured dict output** matching the BOM engine contract —
  `{project, location, building, equipment[], duct_runs[], fittings[],
  registers[], rooms[], metadata, raw_rup_context}`.
- **Building enum mapping** — `BldgType: "Single Level"` →
  `building.type: "single_level"`; `PREFS: "Ducts in Attic"` →
  `building.duct_location: "attic"`. Both match `validators.py` enums.
- **JOBINFOK positional parse** for contractor + drafter + date blocks
  — picks up `Tom Platania / ProCalcs, LLC / CAC1815254 /
  tom@procalcs.net` and `Jayvee Layugn / Design Studio AR LLC` cleanly.
- **1.5 KB `raw_rup_context` narrative** listing CFM values, duct
  dimensions, rooms, and equipment — the AI fallback text the BOM
  engine reads when duct_runs / fittings / registers arrays are empty.
- Model-number extraction intentionally disabled — the free-text regex
  was picking up the Wrightsoft serial (`RSU27939`) and HVAC contractor
  license (`CAC1815254`) as "models". Left to the AI to find in
  `raw_rup_context` where context disambiguates.

7. Phase B — `POST /api/v1/bom/parse-rup` Endpoint

Problem: The spec's two-step UX needs a `/parse-rup` endpoint the SPA
can POST a file to and get back structured design_data, separate from
the existing `/generate` endpoint.

Solution: New route added to the existing `bom_bp` blueprint in
`procalcs-bom/backend/routes/bom_routes.py`. Accepts
`multipart/form-data` with a `file` field, or a raw
`application/octet-stream` body with optional `X-Filename` header.
20 MB upper limit. Sniffs the Wrightsoft magic bytes (`.\x00W\x00S`)
before parsing so obviously wrong files get a 400 instead of
confusing downstream errors. Returns the standard `{success, data,
error}` envelope with the parser's full output in `data`.

8. Phase B — BOM Engine Prompt Extension (`services/bom_service.py`)

Problem: The existing AI prompt only includes the structured
duct_runs / fittings / equipment / registers arrays. When the parser
leaves those empty (hybrid fallback mode), the AI has nothing to
estimate from.

Solution: Extended `_build_ai_prompt` to consume `raw_rup_context` and
`rooms` when present on the input design_data. New "RUP FILE CONTEXT"
block gets appended with an instruction telling Claude to infer duct
linear footage, fitting counts, and register quantities from the
narrative text when the structured arrays are sparse. Rooms list (up
to 60) is surfaced so per-room register counts can be estimated.
Harmless when absent — the block is skipped entirely and the prompt
matches the original shape.

9. Phase B — Pytest Fixture with Real Enos Sample (14/14 green)

Problem: Without tests, every parser change is a roll of the dice.
And no one should deploy a new endpoint without some regression
coverage.

Solution: New `procalcs-bom/backend/tests/test_rup_pipeline.py`, 308
lines, 14 tests, uses the real `experiments/Enos Residence Load
Calcs.rup` as the fixture (skips if not present). Covers the full
chain: top-level keys, project identity, contractor block, drafter
block, building enum mapping, all-8-AHU enumeration, room whitelist
filtering, raw_rup_context substance checks, metadata, validator
integration, prompt building, end-to-end pipeline with mocked
Anthropic client, and graceful handling of non-.rup input. Shimmed
`anthropic` and `google.cloud.firestore` in `sys.modules` so the
suite runs locally without installing those packages (prod container
has them installed via `requirements.txt`).

All 14 new tests pass. Total suite is 42 / 43 green — the one failure
(`test_apply_pricing_total_math_is_correct`, `46.24 vs 46.25`) is a
pre-existing rounding off-by-0.01 in `_apply_pricing` that my changes
didn't touch. Flagged for a separate cleanup.

10. Phase B — Deployed & Verified Against Live Cloud Run

Problem: Local tests only prove the code runs on my machine. Need to
confirm it works against the real procalcs-hvac-bom Cloud Run service
before wiring the SPA.

Solution: Deployed via `gcloud run deploy procalcs-hvac-bom --source
. --region us-east1 --project psychic-medley-469413-r3` — new revision
`procalcs-hvac-bom-00002-8zr` now serving 100% of traffic. Probed with
the real Enos sample:
```
curl -F file=@experiments/Enos\ Residence\ Load\ Calcs.rup \
  https://procalcs-hvac-bom-69864992834.us-east1.run.app\
  /api/v1/bom/parse-rup
```
Returns `success: true`, `project.name: Enos Residence`,
`project.county: Maricopa`, `building: {type: single_level,
duct_location: attic}`, 8 AHUs enumerated, 32 rooms, 1,536-char
`raw_rup_context`, 43 sections parsed. Matches local output exactly.

11. Supersession Note on Old Extractor

Problem: Two parsers in the repo would be confusing to a returning
session.

Solution: Added a SUPERSEDED header to `experiments/rup_extractor.py`
pointing at the canonical `procalcs-bom/backend/utils/rup_parser.py`.
File kept for history — its primitives live on inside the canonical
parser.

Commit `f88ccdb` on both `experiments/rup-parsing` and `main`.

Project: ProCalcs Direct — Demo Client Profile

12. Seed Profile in Firestore

Problem: The dashboard summary endpoint was returning `totalProfiles:
0` — an empty state that breaks the Richard/Tom demo.

Solution: Used the new `seed_demo_profile.py` script to POST one
"ProCalcs Direct" profile (`client_id: procalcs-direct`) with Tom's
real contact info from the Enos JOBINFO as flavor — email
`tom@procalcs.net`, license `CAC1815254` in notes. Ferguson supplier
with realistic per-unit costs (mastic $38.50/gal, tape $12.75/roll,
flex duct $2.85/ft, rect duct $6.40/sqft). 15 / 20 / 30 percent
markups. Carrier AC / Goodman furnace / Rectorseal mastic / Nashua
tape / Atco flex. Two sample part-name overrides (4" and 6" snap
collars mapped to Ferguson SKUs) to prove the override flow works.
Full round-trip verified through the Designer Desktop adapter — the
SPA-shape translation is clean.

Project: Designer Desktop SPA — Phase C Wiring

13. BOM Engine Page Becomes Real (`procalcs-designer/src/pages/bom-engine.tsx`)

Problem: The BOM Engine page was a copy-assembled mock from the
deleted `mockups/` directory. It had a hardcoded `MOCK_RESULT` constant
pretending to walk a DWG→DXF→INSERT-Filter pipeline that never matched
the actual backend. Zero real behavior.

Solution: Rewrote the page as a real `.rup` upload + preview state
machine — idle → parsing → parsed → error. The dropzone now accepts
`.rup` files only, routes each drop through a new `useParseRup` React
Query hook that POSTs multipart to `/api/bom/parse-rup`, and renders a
green "Parse Complete" card with:
- Equipment count, room count, total CFM, building type (4-column
  stat grid)
- Address + contractor + duct location + date metadata row
- Scrollable right panel showing all extracted rooms with their
  assigned AHUs
- A prominent "Continue to BOM Output →" button that stashes the
  parsed data in sessionStorage and navigates to `/bom-output`

Kept the 4-step pipeline visual at the top of the page but relabeled
the steps to match reality: Upload → Parse → Preview → Generate. The
active/done highlighting is now driven by the real hook lifecycle
instead of a fake setTimeout chain. Swapped the DWG/ODA info callout
for copy explaining the hybrid extraction strategy (structured binary
parse + AI fallback via `raw_rup_context`).

Error handling: if the parser rejects the file (not Wrightsoft, bad
version, corrupt), the page flips to an "error" state with the
server-provided message and a "Try Another File" button.

14. Adapter Proxy + Hooks for the BOM Pipeline

Problem: The existing `bom.ts` proxy was a one-branch catch-all that
forced `Content-Type: application/json` and JSON-stringified the body.
Multipart `.rup` uploads would break at the `JSON.stringify(Buffer)`
line. Also the SPA had no React Query hooks for the BOM endpoints — the
page needed `useParseRup` and `useGenerateBom` to be written.

Solution (three files, single focused commit):

- `procalcs-designer/server/index.ts` — extended the JSON parser
  bypass from `/api/pdf-cleanup` alone to also cover
  `/api/bom/parse-rup`, so multipart bodies flow through untouched.
- `procalcs-designer/server/routes/bom.ts` — split the catch-all into
  two branches. `/parse-rup` now streams the raw multipart body + the
  original Content-Type header to the Flask backend, mirroring the
  undici `duplex: "half"` pattern from `server/routes/pdfCleanup.ts`.
  Everything else (`/generate`, etc.) keeps the existing JSON
  forwarding. Both branches forward the Flask envelope verbatim.
- `procalcs-designer/src/lib/api-hooks.ts` — added TypeScript types
  (`RupDesignData`, `BomLineItem`, `BomResponse`) and three new hooks:
    - `useParseRup()` — POST FormData → `/api/bom/parse-rup`, returns
      unwrapped design_data
    - `useGenerateBom()` — POST JSON → `/api/bom/generate`, returns
      unwrapped BomResponse
    - `storeParsedRup` / `loadParsedRup` / `clearParsedRup` —
      sessionStorage helpers for threading parsed data between the
      BOM Engine and BOM Output pages (wouter has no built-in route
      state, and sessionStorage has zero new deps + survives tab
      reload + debuggable via DevTools)

15. BOM Output Page Becomes Real (`procalcs-designer/src/pages/bom-output.tsx`)

Problem: The BOM Output page was another copy-assembled mock. It had
a 15-row `MOCK_BOM` array hardcoded with Beazer Homes fake data and a
"Beazer Homes — Lot A7" metadata banner. Zero real backend calls.

Solution: Rewrote the page as a four-state machine driven by
sessionStorage + `useGenerateBom`:

- **needs-input** — no parsed data in sessionStorage. Shows a card
  directing the user to BOM Engine first.
- **ready-to-generate** — parsed data present. Shows the parsed
  summary banner (project, building, equipment count, room count), a
  client profile picker (`useListClientProfiles`, defaults to
  "procalcs-direct"), an output-mode picker (full / materials_only /
  client_proposal / cost_estimate), and a big "Generate BOM" button.
- **generating** — animated Sparkles icon + friendly copy explaining
  the expected 10–20 second AI round trip (and up to 45 s on cold
  start). The button disables while the mutation is pending.
- **done** — the existing category-grouped table UI renders with real
  `line_items` mapped from the Flask response. `BomResultView` is a
  dedicated sub-component for clarity.

Kept the existing visual skeleton intact (category summary cards,
search + filter controls, expandable category tables, grand total
card) — only the data source changed. A `mapLineItem` helper
normalizes the Flask shape into the existing `BomLine` display type;
unknown categories fall back to "consumable" so the 4-bucket UI
doesn't break. Prices come from `unit_price`/`total_price` when
available, `unit_cost`/`total_cost` for cost_estimate mode.

Wired the previously-fake Print button to `window.print()` and the
Export CSV button to a client-side blob + download trigger using the
`job_id` as filename. Added a "Back to BOM Engine" button that clears
sessionStorage and returns the user to step 1.

Also added `@media print` rules to `src/index.css` — hides sidebar,
header, footer, and any `.no-print` element; tightens tables with
page-break hints; neutralizes hover shadows — so the print dialog
produces a clean printable BOM instead of a clipped viewport.

16. Live End-to-End Smoke Test — Real .rup → Real Priced BOM

Deployed `procalcs-designer` to Cloud Run as revision
`procalcs-hvac-api-00002-zx6`. Probed the full flow via curl:

```
$ curl -F file=@experiments/Enos\ Residence\ Load\ Calcs.rup \
    https://procalcs-hvac-api-69864992834.us-east1.run.app/api/bom/parse-rup
success: true
project: Enos Residence          equipment: 8 AHUs
building: single_level / attic   rooms: 32
raw_rup_context: 1536 chars      sections: 43

$ curl -X POST -H "Content-Type: application/json" \
    -d @gen_body.json \
    https://procalcs-hvac-api-69864992834.us-east1.run.app/api/bom/generate
job_id:      enos-smoke-test
client_name: ProCalcs Direct
supplier:    Ferguson
item_count:  47
totals:      { total_cost: 14557.00, total_price: 18348.44 }

first 3 line_items:
  duct  Flex duct 6" (Atco)    qty=180 unit=LF  total=$615.60
  duct  Flex duct 8" (Atco)    qty=220 unit=LF  total=$752.40
  duct  Flex duct 10" (Atco)   qty=160 unit=LF  total=$547.20
```

Both the parse and generate calls flowed cleanly through the
Designer Desktop adapter. The "Flex duct 6\" (Atco)" line shows the
full hybrid pipeline working end-to-end: Claude inferred the quantity
from `raw_rup_context`, Python applied the Ferguson supplier's
per-foot cost, and the Atco brand name came from the "ProCalcs
Direct" profile's `brands.flex_duct_brand` field.

Latest branches:
main, dev/rup-parsing

Commits landed today:
- `485df30` Phase C-1: wire Designer Desktop adapter to
  /api/bom/parse-rup + /generate
- `7bed2c0` Phase C-2: real .rup upload + BOM generate UX in
  Designer Desktop

Cloud Run state after today:
- `procalcs-hvac-api`       revision `00002-zx6` (Phase C SPA wiring)
- `procalcs-hvac-bom`       revision `00002-8zr` (Phase B parse-rup
                                                  endpoint, unchanged)
- `procalcs-hvac-cleaner`   unchanged — still healthy

📅 ETA / Next Steps:
- **Phase D — Polish** — seed a second demo profile ("Beazer Homes -
  Arizona") via `seed_demo_profile.py --also-beazer` so the dropdown
  has >1 option, write a one-page `docs/MVP_DEMO_SCRIPT.md` for the
  Richard/Tom walkthrough. (1–2 hours)
- **Browser walkthrough by Tom** — click through the live staging URL
  end-to-end with the Enos sample to spot any UX issues the curl
  tests can't catch (browser print dialog, CSV column widths,
  tooltip copy, etc.).
- **Advanced: JSON textarea toggle** — spec acceptance criterion #5
  wants a hidden "Advanced" mode that reveals a JSON textarea for
  direct design_data input. Cut from Phase C to save time; revisit
  if Tom wants it before the demo.
- **Backlog — post-MVP:** Extend Python `ClientProfile` to add
  `brand_color` / `logo_url` / `markup_tiers` so the adapter stops
  dropping those fields on save. Revisit the `_apply_pricing`
  rounding bug in `test_bom.py` (46.24 vs 46.25). Consider moving
  the .rup parser from hybrid to pure Approach A for duct footage +
  fitting counts once we see how Claude performs on the rich-text
  fallback in more real demos.

⚠️ Blockers: None
