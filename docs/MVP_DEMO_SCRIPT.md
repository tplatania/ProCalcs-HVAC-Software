# ProCalcs Designer Desktop — MVP Demo Script

**Audience:** Richard and Tom
**Length:** ~10 minutes end-to-end
**Goal:** Walk through the full `.rup` → priced BOM flow on live staging,
demonstrate profile switching, and capture feedback on copy / layout /
missing fields.

---

## 0. Prerequisites (before the call)

- [ ] A `.rup` file on hand. The `experiments/Enos Residence Load Calcs.rup`
      in this repo works; any Wrightsoft Right-Suite Universal v25.x export
      should.
- [ ] A modern browser (Chrome or Edge preferred — print dialog is cleaner
      than Firefox).
- [ ] A stable connection — the BOM generate call takes 10–20 s on a warm
      container, up to 45 s on cold start.
- [ ] Screen-recording running if you want a video for the archive.

**Staging URL:** https://procalcs-hvac-api-69864992834.us-east1.run.app

---

## 1. Dashboard overview (1 min)

1. Open the staging URL — the **Dashboard** page loads by default.
2. Point out the 5 summary tiles at the top:
   - Total Profiles **2**
   - Active Profiles **2**
   - Inactive Profiles **0**
   - Part Overrides **2**
   - Suppliers **2**
3. Point out the **Recent Profiles** panel — should show both profiles
   sorted by last-updated:
   - **Beazer Homes - Arizona** — Winsupply supplier, 10% markup
   - **ProCalcs Direct** — Ferguson supplier, 15% markup
4. Note the sidebar: Dashboard / All Profiles / New Profile / **BOM Engine**
   / BOM Output.

**Talking point:** "Everything you see here is live — the numbers come from
Firestore via the Flask backend through the Node adapter. Refresh the page
and you'll see they update if we add or remove profiles."

---

## 2. Client profiles page (1 min)

1. Click **All Profiles** in the sidebar.
2. Hover over the two profile cards — show the brand-color accent bar and
   the hover-lift.
3. Click **ProCalcs Direct** to open the profile detail page.
4. Point out the sections: Client info, Supplier details, Markup engine,
   Part overrides (2 entries — "4-inch collar" → "4\" snap collar" and
   "6-inch collar" → "6\" snap collar", both mapped to Ferguson SKUs).
5. Click **← All Profiles** to go back.

**Talking point:** "Richard and Windell maintain these profiles. Each
contractor's pricing rules, supplier costs, markup tiers, and part name
overrides live in one place. When we generate a BOM below, these values
drive the numbers."

---

## 3. BOM Engine — upload the `.rup` (2 min)

1. Click **BOM Engine** in the sidebar.
2. Pipeline header shows four steps: **Upload → Parse → Preview →
   Generate**. All currently idle.
3. Drag `Enos Residence Load Calcs.rup` onto the dropzone (or click to
   browse). Expected: the drop area shows the filename + file size, the
   progress bar fills to 45 %, and within ~3 seconds the "Parse" step goes
   green.
4. When parse completes, the "Parse Complete" preview card appears:
   - **Project:** Enos Residence
   - **4-column stat grid:** Equipment 8 / Rooms 32 / Total CFM 855 /
     Building single level
   - **Metadata row:** address (N Rackensack Rd, Cave Creek 85331),
     contractor (Tom Platania), ducts (attic), date (Nov 14, 2025)
5. Point to the right panel — scrollable list of 32 extracted rooms, each
   mapped to its assigned AHU. Scroll through: KITCHEN → AHU-3, MASTER
   BEDROOM → AHU-1, GAME RM → AHU-4, etc.

**Talking point:** "The parser pulled all of this directly from the
Wrightsoft binary — no Wrightsoft install required, no PDF export step.
The extraction strategy is hybrid: we get the structured fields from
regex, and the narrative context at the bottom of the parser output gives
the AI enough to estimate duct footage and fitting counts in the next
step."

---

## 4. BOM Output — pick profile + generate (3 min)

1. Click **Continue to BOM Output →** on the preview card. Navigates to
   `/bom-output`.
2. The parsed summary banner shows at the top:
   `Project: Enos Residence | Building: single level / attic |
   Equipment: 8 units | Rooms: 32 rooms`
3. Point out the **Client Profile** dropdown — defaults to "ProCalcs
   Direct — Ferguson". Open the dropdown to show both options including
   "Beazer Homes - Arizona — Winsupply".
4. Leave it on **ProCalcs Direct** for the first run.
5. Point out the **Output Mode** dropdown — four options:
   - **Full** — all items, cost + price (default)
   - **Materials Only** — no equipment
   - **Client Proposal** — price only, no cost exposure
   - **Cost Estimate** — cost only, no markup shown
6. Leave on **Full**.
7. Click **Generate BOM**. Expected: animated sparkles icon, "AI estimating
   quantities..." copy, 10–20 second wait.

**Talking point (during the wait):** "This is a single Claude Sonnet call
against the parsed design data plus the raw context. Python does all the
math — Claude only estimates quantities. The 10-to-20-second wait is the
AI round trip; in production we can stream the response for a snappier
feel, but for the demo we wait it out."

---

## 5. BOM Output — review the generated BOM (3 min)

When the generate call returns, the page flips to the rendered BOM:

1. **Top banner** — 4 cells:
   - Job: **Enos Residence**
   - Profile Applied: **ProCalcs Direct (Ferguson)**
   - Generated: **timestamp**
   - Grand Total: **~$18,000** (exact value varies per AI run — Claude is
     non-deterministic here)
2. **Category summary cards** — 4 buckets: Equipment, Duct, Fittings,
   Consumables. Each shows item count + subtotal. Click one to filter the
   table below; click again to clear.
3. **Search box** — type `flex` to filter to flex-duct rows.
4. **Expandable category sections** — click **Duct** to collapse. Click
   again to expand. Show the full table: Description / Qty / Unit / Unit
   Cost / Markup / Total.
5. **Point to a specific line** — something like "Flex duct 6\" (Atco) —
   180 LF — $615.60". Call out the Atco brand — that's pulled from the
   profile's `brands.flex_duct_brand` field, not invented by Claude.
6. **Grand Total card** at the bottom — big dollar figure, highlighted
   with a "ProCalcs Direct markup applied" badge.
7. Click **Export CSV** — browser downloads `enos-residence-<timestamp>.csv`.
   Open it in Excel / Sheets to show the full table.
8. Click **Print** — print dialog opens. Point out that the sidebar,
   header, and action buttons are hidden — only the BOM banner, category
   cards, and tables show. Cancel the print dialog.

**Talking point:** "Everything here is real. If we change the markup
percent in the profile and regenerate, these numbers move. If we add a
part override, the 'Flex duct 6\"' line could become 'FRG-FX-6' with
Ferguson's SKU — we already have that override flow working, just need
to exercise it with more real overrides."

---

## 6. Profile switching demo (1 min)

1. Click **Regenerate** (or Back → Continue → Generate again).
2. On the BOM Output ready-to-generate screen, open the **Client Profile**
   dropdown and pick **Beazer Homes - Arizona — Winsupply**.
3. Click **Generate BOM** again.
4. When it returns, compare:
   - Supplier badge now reads **Winsupply** instead of Ferguson
   - Grand Total is lower (10 % markup vs 15 %, and cheaper per-unit
     costs — Beazer's a volume customer)
   - Brand names in line descriptions shift from Atco / Carrier / Goodman
     to Thermaflex / Trane / Trane

**Talking point:** "Same job, same parsed .rup, different client — BOM
regenerates with different pricing, different brand names. This is
exactly the profile-switching flow Richard uses manually today, except
now it's one click instead of a spreadsheet rewrite."

---

## 7. Wrap-up — Q&A + feedback capture (2 min)

Ask Richard and Tom:

1. **Copy / language:** Does anything on the page use the wrong jargon?
   Wrong unit abbreviations (LF vs ft, EA vs ea)?
2. **Missing fields:** Are there fields in the parsed preview that should
   be visible but aren't? (State, county, number of stories, exterior wall
   area, etc.)
3. **Output modes:** Are the four modes (full / materials_only /
   client_proposal / cost_estimate) the right carve-out, or do you need
   more? Fewer?
4. **Accuracy check:** Spot-check 3 BOM line items against what you'd
   normally estimate for a job this size. Where did Claude over- or
   under-estimate?
5. **Profile fields:** Are there profile fields we're missing? The current
   schema has supplier costs, markup tiers, brand preferences, part name
   overrides — what else?
6. **Demo flow:** Did any step take too long? Feel awkward? Was the
   sessionStorage-between-pages invisible enough, or did you notice the
   state handoff?

---

## Known limitations to flag proactively

- **Cold start latency** — the first generate call after idle can take
  30–45 s. Warm calls are 10–20 s. Solvable with a minimum instance or a
  ping warmer.
- **Claude quantity estimates are non-deterministic.** The same `.rup`
  may produce slightly different quantities run-to-run. Production will
  need a seed or a rules-based pass for consistency.
- **brandColor / logoUrl / markupTiers / supplierContact / supplierEmail**
  — visible in the profile form but dropped on save because the Python
  `ClientProfile` model doesn't have them yet. Cosmetic-only right now;
  fix is a post-MVP model extension.
- **No job history.** Each generate run is ephemeral. No "my previous
  BOMs" list yet.
- **CSV only, no PDF.** Use the browser's Print → Save as PDF for now.
- **Single sample file.** Everything has been tested with one .rup
  (Enos Residence). Other Wrightsoft versions / project templates may
  surface edge cases — bring your own `.rup` files to stress-test.

---

## Troubleshooting

**"Parse Failed — not a Wrightsoft .rup project file"**
→ The file isn't a valid .rup export. Make sure you're dragging the
actual `.rup` file (not a PDF report or a screenshot).

**"BOM generation failed — No profile found for client_id"**
→ The seeded profiles were deleted from Firestore. Re-run
`python procalcs-bom/scripts/seed_demo_profile.py --also-beazer`.

**Generate button hangs > 60 seconds**
→ Cold start + AI latency. If still spinning after 90 seconds, reload
the page (the parsed data is stashed in sessionStorage and will survive)
and try again.

**Print dialog shows the sidebar / header**
→ Browser-specific. Chrome and Edge respect the `@media print` rules
correctly; Firefox may need `Print → More settings → Headers and
footers off`.

**Dashboard shows 0 profiles**
→ Firestore is empty. Re-seed: `python scripts/seed_demo_profile.py
--also-beazer` from the `procalcs-bom/` directory.

---

## What to file after the demo

Capture every piece of feedback in the `docs/` directory as a dated
markdown file (`docs/09-04-2026-richard-tom-feedback.md` or similar).
Tag individual items with `[copy]`, `[ux]`, `[backend]`, `[ai]`, or
`[profile-model]` so Gerald can triage into the next sprint.
