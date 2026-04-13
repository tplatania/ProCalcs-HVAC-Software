# ProCalcs Designer Desktop — Road to MVP Checklist

> Generated: April 13, 2026
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

## Checklist

### Auth & Access
- [ ] P0: Google OAuth restricted to @procalcs.net domain
- [ ] P0: Individual accounts for each team member (~11 concurrent users)
- [ ] P2: Admin panel for user management (not needed at launch — Google domain handles it)

### Core Features — .rup to BOM Pipeline
- [ ] P0: .rup file upload replaces JSON textarea (spec written: docs/GERALD_HANDOFF_RUP_UPLOAD.md)
- [ ] P0: Parser extracts all design data from .rup binary (Gerald's 570-line canonical parser in place)
- [ ] P0: Installation materials rules engine in Python — hardcoded, deterministic, not AI-estimated
  - Collars per duct run, tie straps per connection, hangers per LF, mastic/tape ratios
  - Rules validated by contractor via spreadsheet (see Installation Materials Validation below)
- [ ] P0: Contractor Intelligence Profiles — pricing, brands, markups, part name overrides per client
- [ ] P0: BOM generation applies profile to extracted design data + installation materials rules
- [ ] P1: Designer review/edit step — ability to adjust quantities, add/remove items before finalizing
- [ ] P1: Output mode selection (Full BOM, Materials Only, Client Proposal, Cost Estimate)

### PDF-to-CAD Cleanup Tool (launches WITH BOM)
- [ ] P0: DXF upload and entity-type cleanup working end-to-end
- [ ] P0: Smart INSERT Filter — keeps doors + ventilation appliances, strips furniture/electrical/plumbing
- [ ] P0: ODA File Converter wired up for DWG→DXF→clean→DXF→DWG pipeline
- [ ] P0: Test with real DWG files from designers (not just synthetic test fixtures)
- [ ] P0: Output file works cleanly in Wrightsoft — no performance issues
- [ ] P1: Phase 2 scanned blueprint handling (the 20% — AI vision, later)

### BOM Output & Deliverable
- [ ] P0: Branded PDF output with ProCalcs logo — this is the $50-$150 deliverable
- [ ] P0: Professional layout — not a spreadsheet printout, looks like real software output
- [ ] P1: CSV export (already working)
- [ ] P1: Print-friendly view (already working)
- [ ] P2: Tiered pricing per output mode (Idea #78 in MASTER_IDEAS.md)

### Profile Management
- [ ] P0: Create/edit/delete contractor profiles
- [ ] P0: Profile fields: supplier, pricing per unit, markup tiers, brand preferences, part name overrides
- [ ] P1: Search/filter on profile list (needed when profiles grow to hundreds)
- [ ] P2: Profile import/export for bulk setup
- [ ] P2: Job history per profile — AI compares estimated vs actual over time

### Data & Integrations
- [ ] P0: Firestore for contractor profiles (already provisioned)
- [ ] P0: Cloud SQL Postgres for app data (already provisioned)
- [ ] P0: Claude API for BOM quantity estimation where parser data is sparse (hybrid fallback)
- [ ] P2: Supplier API integrations (Ferguson, Winsupply) for live pricing

### Infrastructure & Deployment
- [ ] P0: Cloud Run deployment (already live at staging URL)
- [ ] P0: Secret Manager for API keys (already configured)
- [ ] P1: Minimum instance to avoid cold start latency (30-45s on first call)
- [ ] P2: Custom domain (designer.procalcs.net or similar)
- [ ] P2: CI/CD pipeline (currently manual gcloud deploy)
- [ ] P2: Staging vs production environments (same environment is fine for internal tool)

### Trust & Polish
- [ ] P0: Installation materials rules validated by real contractor (spreadsheet sent out)
- [ ] P0: 1-week testing period — Richard and Gerald run real projects daily
- [ ] P0: Accuracy spot-check against manual BOM process
- [ ] P1: Loading states and error messages for all async operations
- [ ] P1: Graceful handling of corrupt/unsupported .rup files
- [ ] P2: Empty states for new users (no profiles yet, no BOMs generated)

### Launch & Sign-off
- [ ] P0: Richard confirms accuracy on real projects
- [ ] P0: Gerald confirms tech stability
- [ ] P0: Catherine approves for production use
- [ ] P0: Tom gives final go
- [ ] P1: Contractor validation of BOM accuracy (only if Richard/Gerald find discrepancies)

---

## Deferred (Explicitly NOT MVP)
- Landing page / marketing site — internal tool, not needed
- Stripe / billing / payments — revenue through normal ProCalcs invoicing
- Analytics / tracking (PostHog, GA) — not needed for internal tool
- Customer support widget — team uses Slack/direct communication
- Terms of Service / Privacy Policy — internal tool
- Mobile responsive — desktop-first is fine, designers work on desktop
- Validator — deprioritized, distant project
- Job history / "my previous BOMs" — post-launch feature
- Scanned blueprint AI vision engine — Phase 2 of PDF cleaner

## Open Questions
- What are the complete installation materials rules? (Waiting on contractor feedback from spreadsheet)
- Does the .rup parser extract ALL BOM-relevant data, or are there gaps? (Testing will reveal this)
- What does the branded PDF template look like? (Needs design direction from Tom)
- How many output modes does the team actually need? (5 built, may be too many or too few)
- Cold start latency acceptable for internal use, or need minimum instance? (Test during 1-week trial)

---

## Installation Materials Validation Process

### What This Is
The BOM tool needs to add installation materials that Wrightsoft doesn't track —
the stuff that goes on the truck but nobody draws: collars, tie straps, mastic,
tape, brushes, screws, hangers, condensate line materials, etc. These quantities
must be calculated by hardcoded rules in Python, NOT estimated by AI, because
the output needs to be accurate and consistent every time for a $50-$150 deliverable.

### The Spreadsheet
**File:** `docs/ProCalcs_BOM_Installation_Materials_Rules.xlsx`

Two sheets:
- **Sheet 1 — Duct Run Materials:** Lists every installation material we think
  is needed, organized by category (per duct run, per equipment install, overall
  consumables, per register). Each row has the component, material, quantity rule,
  unit, notes, and a blue "Your Corrections" column. There are 10 blank rows at
  the bottom for items we missed entirely.
- **Sheet 2 — Questions for Contractor:** 18 direct questions about collar types,
  hanger spacing, mastic usage rates, brand preferences, pricing, and "what do
  we always forget?"

### Who Sends It
Richard or Catherine sends the spreadsheet to an HVAC contractor client who is
actively installing systems. This needs to be someone buying materials today —
not someone who was in the field 5 years ago. Current pricing, current products,
current installation practices.

### What To Ask the Contractor
"We're building a tool that automatically generates a complete materials list
from a finished HVAC design. We need your help making sure we're not missing
anything. Can you review this spreadsheet and fill in the blue columns? It
should take about 15-20 minutes. We want to know what materials you bring to
every job, how much of each, and what you're paying."

### What Comes Back
The contractor returns the spreadsheet with:
- Corrections to our quantity rules (e.g., "1 hanger per 4 ft, not 5 ft")
- Missing materials we didn't list (filled in the blank rows)
- Current pricing per unit from their supplier
- Brand preferences and product types
- Answers to the 18 questions on Sheet 2

### What Gerald Does With It
Gerald takes the validated rules and builds them into a Python rules engine:
- `procalcs-bom/backend/services/materials_rules.py` (new file)
- Each rule is a function: input = design data (duct count, LF, equipment count),
  output = material line items with deterministic quantities
- No AI involvement — pure math. 14 duct runs × 1 collar each = 14 collars.
- Client profile determines WHICH brand/type of collar and WHAT they pay.
  The rules engine determines HOW MANY.
- Rules engine output feeds into the existing BOM formatter alongside the
  .rup-extracted design items.

### Timeline
- [ ] Spreadsheet sent to contractor (Richard or Catherine)
- [ ] Contractor returns validated rules (target: 1 week)
- [ ] Gerald builds rules engine from validated data
- [ ] Richard spot-checks rules engine output against manual BOM on 3-5 real projects
- [ ] Rules are locked for launch

---

## Current State (what Gerald has built)
- ✅ Designer Desktop SPA deployed to Cloud Run
- ✅ .rup file upload and parsing (570-line canonical parser)
- ✅ Contractor profiles CRUD in Firestore (2 demo profiles seeded)
- ✅ AI BOM generation with Claude API
- ✅ Profile switching changes pricing/brands/totals
- ✅ CSV export and print view
- ✅ 5 output modes (Full, Materials Only, Labor+Materials, Client Proposal, Cost Estimate)
- ⬜ Google OAuth (@procalcs.net restriction)
- ⬜ Installation materials rules engine (hardcoded Python, not AI)
- ⬜ Branded PDF output
- ⬜ Designer review/edit step before finalizing
- ⬜ Contractor validation of rules (spreadsheet created, not yet sent)

---
*Generated from road-to-mvp.md brainstorming session — Tom + Claude, April 13, 2026*
