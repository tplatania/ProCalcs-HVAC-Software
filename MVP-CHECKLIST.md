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
  - Rules validated by contractor via spreadsheet (docs/ProCalcs_BOM_Installation_Materials_Rules.xlsx)
- [ ] P0: Contractor Intelligence Profiles — pricing, brands, markups, part name overrides per client
- [ ] P0: BOM generation applies profile to extracted design data + installation materials rules
- [ ] P1: Designer review/edit step — ability to adjust quantities, add/remove items before finalizing
- [ ] P1: Output mode selection (Full BOM, Materials Only, Client Proposal, Cost Estimate)

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

## Deferred (Explicitly NOT MVP — but PDF Cleaner is NEXT)
- **PDF-to-CAD Cleanup tool — launches immediately after BOM MVP is live**
  - Backend deployed, frontend page exists in Designer Desktop
  - Spec complete with Richard's feedback (interior doors + ventilation appliances kept)
  - Smart INSERT Filter built and tested (29 test cases)
  - Saves 30-60 minutes per job — biggest time/cost saver after BOM revenue
  - Needs: real DWG test files from designers, ODA converter wiring, production testing
- Landing page / marketing site — internal tool, not needed
- Stripe / billing / payments — revenue through normal ProCalcs invoicing
- Analytics / tracking (PostHog, GA) — not needed for internal tool
- Customer support widget — team uses Slack/direct communication
- Terms of Service / Privacy Policy — internal tool
- Mobile responsive — desktop-first is fine, designers work on desktop
- PDF-to-CAD Cleanup tool — separate project, different timeline
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
