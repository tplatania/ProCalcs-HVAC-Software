# Validation checklist — everything shipped since corpus ingestion

For Gerald's end-to-end review. Each item says **what to check, how,
and what you should see**. Anything that doesn't match is a finding —
note it and move on, don't debug mid-walk.

Your inputs are test-provenance (`gerald@procalcs.net`), so you can
exercise every step below — including saving prices and chatting —
without polluting adoption or impact metrics.

Staging URLs:
- Designer: https://procalcs-designer-desktop-staging-69864992834.us-east1.run.app
- BOM API:  https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app

---

## 1 · The corpus (foundation)

- [ ] **Coverage** — `ls ~/Procalcs/RUPs-from-zoho/` shows 12 community
      folders; **Canopy (Mustang Way) must NOT be present**.
- [ ] **Finals-only, non-RE preference** — spot-check any community:
      files come from Finals folders; where both `X.rup` and `X RE.rup`
      existed in Zoho, only the non-RE variant is local.
- [ ] **Size sanity** — corpus totals ~9.7 GB
      (`du -sh ~/Procalcs/RUPs-from-zoho/`).
- [ ] **Drift awareness** — the archive gains ~12 files/day upstream.
      A re-walk on 2026-07-17 confirmed the 20 "new" files were
      active-work drift, not sync gaps. Nightly incremental re-sync is
      recommended but **not yet scheduled** — open decision for you.

## 2 · Analysis artifacts (what we learned from)

All under `~/Procalcs/full-corpus-run-2026-07-15/`:

- [ ] `pairs.jsonl` — RUP↔BOM pairs (Rheia projects only — remember
      the selection bias: BOM exists ⇒ Rheia).
- [ ] `plan_memo.json` — per-plan fitting memos, keyed
      `community::plan`, ≥90% agreement gate. Also mirrored to GCS
      (the engine reads it via `PLAN_MEMO_PATH`).
- [ ] `summary.json`, `p6_results.json` — pass results; P6 shows the
      formal zero-zero convergence (0 opened, 0 closed).
- [ ] Scripts that produced all of this are committed in
      `scripts/corpus-analysis/` — reproducibility check: pick one
      (e.g. `v6_final_score.py`) and confirm it runs.

## 3 · Engine rules (v7) — the deterministic core

Generate a BOM from any Finals `.rup` (Wrightsoft BOM v2 page) and
check the output against these promoted rules:

- [ ] **Boots/diffusers = home-run count** (not registers−1; that was
      v1, corrected by corpus evidence).
- [ ] **10-00-190 footage = ceil(Σ per-run routed lengths)** from the
      DUCT drawing blocks.
- [ ] **Takeoffs = run count** — was exact 762/762 across the corpus.
- [ ] **Generation pairs** (040↔041, 050↔051, 090↔091) — never both
      of a pair on one BOM; plan memo wins over rule.
- [ ] **Rheia takeoff block only on Rheia-profile projects** — run a
      standard project and confirm no Rheia SKUs appear.
- [ ] **Boot SKUs from DREGPERF** (10-01-220/200/210 per register
      mount) — spot-check against the drawing.
- [ ] **Scoreboard** (the honest numbers to hold us to): corpus-wide
      recall 0.75–0.78, precision ~0.86, qty accuracy 0.96–1.0.
      Re-run: `python3 scripts/corpus-analysis/v6_final_score.py`.
- [ ] **Standard projects** (the actual mission): sales-office
      reproduction at **recall 1.0** via RPITEM — this is the claim
      that matters most; re-verify on one standard `.rup`.
- [ ] **Edge case discipline** — 79th Ct (Trane, P99 outlier) is
      labeled Edge Case; confirm nothing generalizes from it.

## 4 · Smoke suite (regression net)

- [ ] `scripts/corpus-analysis/smoke_suite.py` runs green (v3).
- [ ] It covers the two classes of bugs it already caught once:
      generation-pair duplicate lines, and junk files returning empty
      200s (header sanity + empty-lines 400 now enforced).

## 5 · Question ledger (the no-Richard loop)

- [ ] `contractor-rules/reliable/questions.yaml` — 11 closed with
      evidence tiers, P6 convergence block appended. Every closed item
      cites its evidence (e.g. dehumidifier B33DHW = Beazer spec
      revision 2025-03-05, Pratt emails; SKU generations = Phase-2
      cutover 2022-07-01).
- [ ] **Only 3 asks remain for Richard's team**, all visible in-app:
      heat-strip kW one-liner + two attach-a-sheet asks (Rheia price
      sheet, equipment cost sheet).
- [ ] UI: open the Review Assistant on any BOM → amber banner shows
      "Open questions for your team (3) — 11 already answered from
      your project history". Each has an **answer** button that
      prefills the chat.

## 6 · Review Assistant (chat)

On a loaded BOM (e.g. `/diagnostics/wrightsoft-bom-v2?run=350`):

- [ ] Launcher button bottom-right; opens a 380px right panel;
      **content reflows to full-width-minus-panel** (no dead margins,
      nothing covered); closing restores the centered layout.
- [ ] Ask "What is SKU 10-01-041?" → grounded answer via catalog
      tools (server-side; better-sqlite3).
- [ ] Paste "the 3-in duct is $1.42/ft" → returns a **proposal card**;
      Apply writes a contractor override (visible on the line
      immediately, remembered on future BOMs).
- [ ] **Attachments**: paperclip accepts common types + `.rup`
      (extraction at upload: xls/csv→CSV, pdf/docx→text, images→
      vision). Attach a price sheet and say "apply these" — expect
      one proposal per line.
- [ ] **Sniping**: crosshairs on every table AND row (line items incl.
      section headers, Quick Order, Register Air Balance, both Duct
      Cuts variants incl. per-cut rows, Equipment Specs). Sniping
      auto-opens the chat with a colored short-name chip. The
      surgical test: snipe exactly 2 rows, ask "price these" —
      proposals must reference **only** those 2 SKUs.
- [ ] Crosshair columns aligned (header and rows share one vertical
      line — measured 0px diff on all tables).

## 7 · Pricing / override loop

- [ ] Inline price edit on a line → saves; `$0 OK` distinguishes
      "confirmed free" from "needs price" (rose).
- [ ] Supplier keying is prefix-tolerant (the DAIKIN vs DAIK bug is
      fixed — save under one, applies under both).
- [ ] Regenerate the same job → override auto-applies (line carries
      the edited badge, price persists).

## 8 · Telemetry + learning-loop monitoring (Day-25)

- [ ] **Provenance**: send any chat message, then check
      `/api/usage/summary?days=1` → **0 events** (you're a test
      actor); `&include_test=1` → your event appears. This is the
      "my inputs don't count" guarantee.
- [ ] **Loop closure works retroactively**:
      `/api/usage/impact?client_id=reliable-heating-and-cooling&include_test=1`
      → your 2 test overrides show ~51 re-applications across ~107
      historical runs. Default (no flag) → zeros, because no *real*
      team input exists yet. The day Richard's team saves their first
      correction, these counters start moving on their own.
- [ ] **Transparency strip**: appears in the sidebar only when real
      team corrections exist — currently absent (correct).
- [ ] **Monthly ritual**:
      `python3 scripts/corpus-analysis/monthly_scoreboard.py --skip-base`
      runs, appends to history, and knows the tripwire (≥50 inputs +
      flat coverage → exit 2).
- [ ] Thresholds documented in `docs/learning-loop-monitoring.md` —
      confirm you agree with: 10–15 loop closures / ≥3 plans / ≥2
      people = mechanism proven.

## 9 · Guardrails that must still hold

- [ ] No `.mdb`, credentials, tokens, or corpus files in either repo:
      `git log --all --stat | grep -iE "\.mdb|token|secret"` → nothing.
- [ ] `crm.mdb` never ingested beyond table names (PII).
- [ ] Zoho/OAuth creds only in `~/Procalcs/envs/`.
- [ ] `.rup` parsers live only upstream
      (`procalcs-bom/backend/utils/`) — designer repo imports, no
      forked copies.

## 10 · Deploys

- [ ] Designer staging serving (rev ≥79), BOM staging serving
      (rev ≥121, migration `a7e2c9d4b1f6` self-applied at boot).
- [ ] Env-var discipline: `--update-env-vars` only (the `--set-env-vars`
      wipe of 07-16 is documented and must not recur).

---

## The two questions to end the review with

1. **Would Richard's team catch a wrong BOM?** Walk one BOM end to
   end pretending you're them: is every number either traceable
   (rule, memo, override) or visibly flagged (unmapped, needs
   price)?
2. **If they use it for a month and it's not working, will we know?**
   That's §8 — the summary/impact endpoints and the tripwire are the
   answer; confirm you believe them.
