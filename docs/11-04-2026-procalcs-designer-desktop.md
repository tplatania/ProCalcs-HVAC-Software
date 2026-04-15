11-04-2026 Updates

🔧 In Progress:
Google OAuth with @procalcs.net domain restriction. Largest remaining
dev item on the MVP runway (~10 hours), hard launch blocker, and
parallelizable with the contractor materials-rules spreadsheet wait.
Planning the implementation now before writing code.

✅ Done Today

Project: ProCalcs Designer Desktop

1. MVP Gap Analysis

Problem: After the Phase C + Phase D + backlog pass sessions, it was
unclear where the codebase actually stood against the MVP checklist.
Tom dropped a 4-step velocity guide (P0 reconciliation, burn-down,
Gantt plotting, deferred-feature audit) that expected a status table
with code evidence and a calendar estimate to launch.

Solution: Ran two parallel explore agents to verify what's actually
in the code vs the checklist. Produced a one-shot audit artifact
covering the four deliverables — P0 status table with file-level
evidence, 31-hour Gerald burn-down broken out per remaining P0 item,
Mermaid Gantt showing the parallel dev / validation / trial / sign-off
phases, and a deferred-feature zombie-code scan. Scorecard: 13 P0
items completed, 4 partial, 10 missing. Realistic launch target is
about 16 calendar days from kickoff.

2. Deferred-Feature Zombie Code Scan

Problem: The checklist explicitly defers a pile of features (Gemini,
QuickBooks, Bland AI, Zoho Cliq, Stripe, analytics, validator, job
history, blueprint vision). Any of those still wired into active code
paths could cause surprise bugs during the 1-week trial.

Solution: Grepped every deferred feature name across all three
services. Every hit landed inside the phase1_validator reference
directory, and nothing outside that directory imports from it. Clean
bill of health — zero zombie-code risk for the trial. No disable work
needed.

3. Critical-Path Arithmetic

Problem: Tom needed a defensible number to plan around, not a vibe.

Solution: Dev work and contractor spreadsheet roundtrip run in
parallel, so the critical path is max(5 dev days, 7 spreadsheet days)
+ 7 trial days + 2 sign-off days = about 16 calendar days. Five open
questions captured in the report that could move the date (Cloud SQL
necessity, ODA install mechanism, branded PDF template ownership,
contractor spreadsheet status, sign-off ceremony format).

Latest branches:
origin/dev/rup-parsing, origin/main — both synced at the same tip

📅 ETA / Next Steps:
- Plan and implement Google OAuth with @procalcs.net domain
  restriction. Session middleware on the Express adapter, OAuth flow,
  domain allow-list check, route protection across all services,
  SPA login page. (10 hours)
- Confirm contractor spreadsheet has actually been sent. If not, the
  external 7-day wait hasn't started and the Gantt shifts day-for-day.
- Branded PDF output — pick a library (WeasyPrint leaning), template
  design, wire the Download PDF button. (8 hours)
- ODA File Converter wiring for DWG roundtrip. Needs a product call
  on how to install the binary before coding starts. (5 hours)
- Real DWG testing against designer-supplied files. (3 hours)
- Build materials_rules.py once the contractor spreadsheet comes back.
  (5 hours, gated)

⚠️ Blockers:
- Contractor spreadsheet status unknown. Does not block OAuth work
  starting immediately, but does block the 1-week trial milestone if
  the spreadsheet hasn't been sent yet.
