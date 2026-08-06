# BOM Module — BETA definition brief (for Tom / Codex loop)

**From:** Gerald · 2026-08-06
**Purpose:** input document for a Tom + Codex "BETA definition" loop.
Everything here is stated as transparently as we can measure it —
capabilities with numbers, limitations without softening. The loop's
job is to turn this into a signed-off, launch-ready BETA spec (output
contract in §6). The gate table in §2 is a proposal to be edited, not
accepted as-is.

## 0. Current capabilities and limitations — plain inventory

Numbers from the 2026-08-06 scoreboard baseline (full private corpus,
n=1,076 built pairs — corpus-based supporting evidence, not
reproducible outside our environment) and the Reliable pilot
(2 reviewers, ~30 real runs July 24–30).

**What it does today, verified:**
- Reproduces a priced BOM from a Wrightsoft-built `.rup`:
  **precision 0.885, quantity accuracy 0.944, recall 0.696** (medians).
- Read/edit/delete on every run (BREAD canvas): all tables snipeable,
  chat agent with full BOM context, surgical patches, full regenerate
  with corrections + chat + structural tables carried forward.
- Flags instead of guessing on every known unreliability class
  (heat strips, empirical-only equipment, grille-size lumping with
  file-level evidence, unbuilt-file accuracy, auto-sized registers).
- Structural extraction beyond the BOM: per-register CFM, per-piece
  duct runouts, drawing annotations, register-size pre-flight.
- Provenance-clean telemetry (test actors excluded server-side);
  seeded auth (super admin, 2 test admins, 2 Reliable accounts).

**What it does NOT do today, equally verified:**
- **Recall 0.696 means ~30% of reference BOM lines are missed on the
  median historical pair** — mostly content designers left implicit in
  Wrightsoft. This is the single biggest quality number and it will
  not reach 1.0 by engine work alone; the pre-flight/property-capture
  track exists because the data is often not in the file.
- Auto-sized registers: we detect them (62% of records corpus-wide)
  but **cannot recover the true size** — it is not in the file.
- Per-piece flex diameter: not stored in the `.rup`; awaiting
  Windows capture pairs to find or rule out an encoding.
- Dehumidifiers/accessories: canvas text only, no equipment record —
  we surface the note, the user supplies the model.
- Unbuilt `.rup` files: best-effort estimates with a banner telling
  the user to build in Wrightsoft first.
- **The learning loop has zero real data: 0 price/SKU overrides**
  (blocked on the equipment cost sheet). "Gets better with usage" is
  architecture today, not evidence.
- One contractor, two reviewers, staging only, no load testing,
  Rheia-heavy corpus (selection bias documented). Melko gate fix is
  code-verified but awaits the team's fresh-upload confirmation.

## 1. The product thesis (already communicated to Reliable)

One-click perfect BOM is **not possible** from a `.rup` — we have
file-level proof (grille sizes stored as literal 12×12 defaults when
designers don't set them; per-piece duct diameters computed at build
time, not stored; dehumidifiers existing only as canvas text). The
framing the team has accepted:

> **Not perfect — but produces usable output, tells you exactly where
> it's unsure, gives you an AI agent to fill the gaps fast, and gets
> better with every correction.**

BETA = the state where that sentence is *demonstrably true*, per
clause, with evidence Codex can check.

## 2. Proposed BETA gates

Each gate has a binary check and a verification method. "Evidence
now" is where we stand today (2026-08-06).

### Gate A — Produces usable output
| # | Check | Verification | Evidence now |
|---|-------|--------------|--------------|
| A1 | 3 consecutive conventional projects with zero *engine-class* defects (wrong/phantom lines; flagged-for-verify lines don't count as defects) | Run history + reviewer sign-off per project | Counter restarted at Melko; awaiting fresh Melko upload (acceptance criteria committed: `docs/melko-acceptance-criteria.md`) |
| A2 | Rheia/conventional gate holds on every real upload | Staging logs (gate metric line) + zero phantom-Rheia reports | Fixed day-31; synthetic tests + corpus artifact committed; live-verified on 3 projects |
| A3 | Regenerate/patch pipeline preserves user work (corrections, chat, duct tables) | Synthetic tests (13 committed) + tester confirmation | Tim confirmed 5/7 fix classes; carry-forward tests green |

### Gate B — Tells you where it's unsure (flag, never guess)
| # | Check | Verification | Evidence now |
|---|-------|--------------|--------------|
| B1 | Every known unreliability class surfaces a visible flag (verify badge / pre-flight card / hint banner), with zero silent guesses | Code inventory of `verify_reason` sites vs. the defect ledger | 4 classes live: heat strips, empirical-only equipment, grille lumping (now with structural DREGINFO evidence), unbuilt-file accuracy |
| B2 | Flags are *actionable*: each names the fix path (property sheet, rebuild, ask agent) | UI copy review | Pre-flight card names the source fix; expert policy (Richard) encoded in agent prompt |
| B3 | Decode failures are loud in logs, never silent feature omission | Log check (added per Tom's day-31 review) | Shipped in `5c46983` (pending deploy approval) |

### Gate C — Agent fills gaps fast
| # | Check | Verification | Evidence now |
|---|-------|--------------|--------------|
| C1 | Reviewer can complete a full gap-fill session (snipe → correct → regenerate) without losing state | Tester walkthrough (Tim's protocol) | Confirmed by Tim post-fix-wave |
| C2 | Agent never fabricates (provenance rules: drawing objects ≠ BOM rows, no invented models/sizes) | Prompt policy + spot-check of real chats | Policies encoded; Richard's provenance challenge answered; needs periodic sampling |
| C3 | Median correction session shorter than manual re-take-off | Usage telemetry (chat + patch timestamps, test actors excluded) | Not yet measured — **proposed as the one new metric BETA needs** |

### Gate D — Gets better with compounded usage
| # | Check | Verification | Evidence now |
|---|-------|--------------|--------------|
| D1 | Price/SKU corrections persist forever and auto-reapply (contractor overrides) | Override count > 0 and reapplied on ≥2 subsequent BOMs | **Blocked: 0 real overrides — needs the equipment cost sheet** (only open ledger question) |
| D2 | Qty/structure corrections carry through regeneration (run-scoped by design) | Committed tests + Tim's confirmation | Done |
| D3 | Monthly scoreboard shows overlay coverage moving (tripwire: ≥50 real inputs with <1pt movement = strategy alarm) | `monthly_scoreboard.py` history row per month | **Baseline recorded 2026-08-06** (n=1076: recall 0.696 / precision 0.885 / qty-acc 0.944; overlay 0 overrides, 0% of 270 corpus part keys — the D1 blocker in numbers) |
| D4 | Decode walls have a live pipeline (property captures → differ → engine) | Capture protocol committed; DREGINFO decode proved the loop works end-to-end in 1 day | Grille-size wall closed from accumulated data; diameter/dehumidifier walls await Windows captures |

## 3. Deliberately OUT of beta scope

Named so nobody re-litigates them mid-loop:
- Rheia projects (plugin handles them — expert-confirmed, ledger-closed)
- Guessing true sizes for auto-sized registers (flag-only, policy-ratified)
- Per-piece flex diameter until captures land (documented decode gap)
- One-click perfection (the thesis explicitly rejects it)

## 4. What "roster change" makes urgent

The pilot's knowledge currently lives in three durable places —
rules ledger (`contractor-rules/reliable/`), committed docs/tests, and
contractor overrides — plus one fragile place: **Richard's habits**.
Before roster change lands: (a) the cost sheet (converts his pricing
knowledge into D1's compounding store), (b) his review-order
categorization is already encoded in the UI (done, day-30), (c) new
team members get the BETA framing sentence verbatim, not a diluted
"it's automatic" pitch.

## 5. Proposed loop with Codex

1. Tom reviews/edits the gate table (add/strike/re-scope checks).
2. Each agreed check gets its verification method pinned (log line,
   test file, telemetry query) — Codex verifies from evidence, not
   assertions, same as the day-31 review cycle.
3. We ship BETA when all gates green **except** those explicitly
   waived in writing; anything waived is listed on the beta label
   itself ("known limitations" — the honesty is the product).
4. Standing cadence: monthly scoreboard row + gate re-check, manual
   (no automated schedules without Tom's approval — per existing
   agreement).

**Current bottom line:** A2/A3/B1/B2/D2 are green with committed
evidence; A1 waits on the Melko fresh upload; B3 is committed pending
deploy approval; C3 needs one new metric; D1 waits on the cost sheet;
D3 baseline recorded 2026-08-06. That is the whole distance to BETA.

## 6. Output contract for the loop

The loop is done when the Codex produces ONE markdown document
("BETA-spec") containing, at minimum:

1. **BETA definition** — one paragraph, in the "not perfect, but
   usable / honest / assisted / compounding" frame, as Tom ratifies it.
2. **Gate checklist** — final agreed checks, each with: binary
   pass/fail criterion · verification method (log line, test file,
   telemetry query, sign-off record) · **data source and owner**
   (Richard / Tim / Gerald / telemetry — every check must name who
   supplies its data, and nothing may require data the team cannot
   produce) · current status.
3. **Known-limitations label** — the exact text that ships on the
   BETA (the transparent list users see). Anything waived from the
   gates appears here verbatim.
4. **Implementation backlog for Gerald** — every not-yet-green check
   translated into a concrete, ordered action list (code, metric,
   doc, or ask), each item small enough to verify independently.
5. **Sign-off block** — Tom's explicit acceptance line per gate, so
   later "is this BETA?" questions have a single answer document.

Constraints on the loop itself: evidence over assertion (same
standard as the day-31 review); corpus results stay labeled as
supporting evidence; both apps remain staging-only until the spec
says otherwise; no new automated schedules — cadence stays manual.
