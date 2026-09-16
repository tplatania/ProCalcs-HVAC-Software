# Reviewer Workspace + BETA-readiness kit (branch: feature/reviewer-workspace)

Two bundles on one isolated branch (per repo). Additive and defaults-
safe: no change to BOM generation or the deterministic path; new UI is
opt-in, new tests just lock current behavior. Same pull-when-needed
model as `feature/ai-cost-control`.

## Done (built + tested)

**Reviewer Workspace (UI)**
- **Mark-reviewed control + notes** — set `good`/`needs_fix`/`blocked`
  + a note on any persisted BOM, wired to the existing
  `POST /bom-runs/:id/review`. (`review-panel.tsx`)
- **Correction-history timeline** — the run's `patch_ops` rendered as a
  readable audit trail (what changed, reason, who, when). (`review-panel.tsx`)
- **Regenerate diff card** — "what changed vs run #N" on a regenerated
  BOM, via the existing `diffBoms()` engine. (`regen-diff-card.tsx`)

**BETA-readiness kit (infra)**
- **Golden-signature regression lock** (gate A2) — snapshots a
  structural signature of the `.rup` engine output per fixture and
  fails on drift; the automated catch that was missing when the 79th Ct
  tests went stale. Signatures only (no customer BOM content).
  (`procalcs-bom/backend/tests/test_bom_regression.py`)
- **Anti-fabrication contract tests** (gate C2) — lock the chat agent's
  no-fabrication policies + human-in-the-loop tool contracts so they
  can't be silently removed. (`server/routes/bomChat.provenance.test.ts`)

## Remaining (scoped, not yet built)

- **C3 — correction-session telemetry** (gate C3). Measure median
  correction-session time (chat + patch timestamps) vs a manual
  re-take-off baseline. NOTE two open dependencies before building:
  (1) confirm patch/correction applications emit a usage event to
  measure against; (2) the "session start/end" definition is a Tom
  tightening still open — don't hard-code it. Foundation: group a run's
  `usage_events` by time; the manual baseline is a team-supplied
  constant.
- **Export appendix** — include review status + correction history in
  the PDF/XLS export so the handoff artifact carries its provenance.
  Small backend touch in `pdf_service` / `bom_xls_service`.

## Safety

- Additive UI; the review control writes only via the existing
  reviewed endpoint. BOM generation and the deterministic path are
  untouched. Regression + provenance tests only assert current
  behavior. Nothing auto-changes.
