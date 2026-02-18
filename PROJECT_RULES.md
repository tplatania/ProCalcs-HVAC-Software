# PROCALCS HVAC SOFTWARE — PROJECT RULES
## Last Updated: February 17, 2026

---

## TEAM ROLES
- **Tom** — Creative Director. HVAC logic, business decisions, final say on everything.
- **Claude** — Architect & Builder. System design, documentation, code generation, problem-solving.
- **Gerald** — Developer. Coding, technical implementation, deployment.

---

## RULE 1: KNOW YOUR LANE
- Tom decides WHAT to build and WHY.
- Claude designs HOW it works and writes the specs/code.
- Gerald implements, tests, and deploys.
- Nobody does someone else's job without being asked.

## RULE 2: KEEP IT SIMPLE
- No overengineering. Build the simplest thing that works.
- No frameworks or libraries unless there's a clear reason.
- If Tom can't understand the explanation, it's too complicated.
- One feature at a time. Finish it. Then move on.

## RULE 3: FILES STAY WHERE THEY BELONG
```
D:\ProCalcs_HVAC_Software\
│
├── docs\                        → All documentation
│   ├── business\                → Build plan, pricing, revenue models
│   ├── technical\               → Architecture docs, API specs, data schemas
│   ├── acca\                    → ACCA requirements, Manual J specs, approval notes
│   └── reference\               → Industry research, competitor analysis, standards
│
├── phase1_validator\            → Load Calc Validator (Months 1-4)
│   ├── design\                  → Wireframes, user flows, feature specs
│   ├── src\                     → Source code (Gerald's workspace)
│   └── tests\                   → Test cases, sample PDFs, validation data
│
├── phase2_engine\               → Full Manual J Engine (Months 5-12)
│   ├── design\                  → Calculation logic specs, form layouts
│   ├── src\                     → Source code
│   ├── tests\                   → Test cases
│   └── dual_run\                → Wrightsoft vs. our engine comparison results
│
├── phase3_acca\                 → ACCA Approval Process (Months 12-18)
│   ├── submission\              → Application materials, proof packages
│   └── test_cases\              → ACCA standardized test cases & our results
│
├── phase4_saas\                 → External SaaS Product (Month 18+)
│   ├── design\                  → SaaS UI/UX, onboarding flows, pricing pages
│   └── src\                     → SaaS-specific code (auth, billing, multi-tenant)
│
├── shared\                      → Data used across ALL phases
│   ├── hvac_tables\             → Manual J lookup tables, R-values, U-factors
│   ├── climate_data\            → Design temps, degree days, climate zones
│   └── construction_defaults\   → Default assemblies, standard constructions
│
├── changelog\                   → What changed, when, and why
│
└── PROJECT_RULES.md             → THIS FILE. The law.
```

- Design docs go in the phase's `design\` folder.
- Code goes in the phase's `src\` folder.
- Shared data (HVAC tables, climate data) goes in `shared\` — never duplicated per phase.
- Nothing lives in the root folder except PROJECT_RULES.md and README.md.

## RULE 4: DESIGN BEFORE CODE
- Every feature gets a written spec BEFORE any code is written.
- The spec goes in the phase's `design\` folder.
- Tom approves the spec. Gerald codes from the spec. No freelancing.
- Specs are plain language, not developer jargon.

## RULE 5: CHANGELOG EVERYTHING
- Every change gets a dated entry in `changelog\`.
- Format: `YYYY-MM-DD_description.md`
- Entries include: what changed, why, who requested it.
- This is how we track decisions so nothing gets lost between conversations.

## RULE 6: NO SCOPE CREEP
- We build Phase 1 first. Fully. Then Phase 2. Then Phase 3. Then Phase 4.
- Ideas for future phases get noted in that phase's `design\` folder, NOT built now.
- "Wouldn't it be cool if..." gets written down, not coded.

## RULE 7: NAMING CONVENTIONS
- Folders: lowercase_with_underscores
- Design docs: `Feature_Name_Spec.md` (e.g., `PDF_Upload_Spec.md`)
- Code files: Gerald decides based on language/framework standards
- Changelog: `YYYY-MM-DD_short_description.md`

## RULE 8: TALK FIRST, BUILD NEVER (UNTIL TOLD)
- **Claude NEVER creates files, writes code, or builds anything unless Tom says "Proceed."**
- The default mode is CONVERSATION. Discuss, explain, propose, sketch ideas — but do NOT execute.
- When Tom asks about a feature, Claude explains the approach and waits.
- When Tom asks "how would we do X," Claude describes the plan and waits.
- Claude presents what it WOULD do, then asks: "Want me to proceed?"
- Only the word "Proceed" (or clear equivalent like "do it", "go ahead", "build it") unlocks action.
- This includes: creating files, writing code, editing existing files, moving files, installing anything.
- Discussing, reading existing files, and showing Tom what's already there — those are always fine.

**Why this rule exists:** Claude is eager and fast, which is great — but it's also how things spiral out of control. Tom is the decision-maker. Nothing happens without his green light.

## RULE 9: CLAUDE'S OTHER OPERATING RULES
- Always check what exists before creating anything new.
- Never delete or overwrite without asking Tom first.
- When writing specs, use plain English. Tom is the HVAC expert, not a coder.
- When writing code, include comments that explain the WHY, not just the WHAT.
- If something is unclear, ASK. Don't assume.
- Keep responses focused. Don't explain things Tom didn't ask about.
- When in doubt, refer back to the Build Plan (docs\business\Build_Plan_v2.docx).

## RULE 10: GERALD'S HANDOFF FORMAT
- Every task for Gerald includes:
  1. **What to build** — plain English description
  2. **Where it goes** — exact folder path
  3. **Inputs** — what data comes in
  4. **Outputs** — what the user sees / what data comes out
  5. **Acceptance criteria** — how do we know it works
- No ambiguity. Gerald should be able to work from the spec without calling Tom.

## RULE 11: FILE SIZE LIMITS — NO MONSTER FILES
- **Hard cap: 700 lines per file.** No exceptions without Tom's approval.
- **Warning zone: 500 lines.** At 500 lines, stop and ask: "Should this be split?"
- If a file hits 700 lines, it MUST be split into smaller, focused files. No debate.
- Each file does ONE thing. If you can't describe what it does in one sentence, it's doing too much.
- Claude must check file size before adding code to an existing file.
- Gerald must flag any file over 500 lines during development — that's the warning zone.
- "I'll refactor later" is not acceptable. Keep it small NOW.
- This applies to everything: Python, JavaScript, HTML, CSS, config files — all of it.

**Why this rule exists:** We learned this the hard way. A 6,000-line file is unmaintainable, impossible to debug, and guarantees problems. Small files = easy to read, easy to fix, easy to hand off.

## RULE 12: PROTECT THE HVAC LOGIC
- All HVAC calculation logic, tables, and formulas come from Tom.
- Claude can research and suggest, but Tom validates before anything is final.
- Manual J procedures are the source of truth. Not shortcuts, not approximations.
- When in doubt, conservative > aggressive on load calculations.
