# QA UI spec — draft review, not questionnaire

*2026-07-15. Replaces the "Richard answers 31 questions" framing.
Design constraint: Richard has no consolidated rules record, can't
recall rules in the abstract, and has very limited time. The observer
agent was shelved for workflow-intrusiveness — this UI is the
replacement contact surface.*

## Principle

Richard reviews **concrete drafts**, never abstract questions. Each
interaction is ≤1 minute, resumable, and every answer persists as a
rule with provenance in `contractor-rules/reliable/rules.yaml` (or its
DB successor).

## Surfaces

### 1. Draft BOM review (primary)
Route: `/diagnostics/bom-review/:runId` (naming TBD alongside v2 pages)

- Generated BOM for one project, lines grouped by confidence:
  - auto (engine confident — collapsed by default)
  - flagged (low confidence — shown expanded, each with a one-tap
    resolution: ✓ correct / ✗ wrong → "what should it be?" inline)
- Every ✗ answer creates/updates a ledger rule scoped to the narrowest
  matching context (community, plan, system type), status `confirmed`.

### 2. Rule confirmations (secondary, batched)
Route: `/diagnostics/rules-inbox`

- Derived rules awaiting confirmation, one card each, phrased in
  Richard's terms with corpus evidence attached:
  "Your last 200 projects used the Broan B150E75NT on 94% — is that
  your default? [Yes, default] [Depends → on what?] [We've moved on]"
- Max 3–5 cards surfaced at a time; the rest stay queued. No
  completion pressure — the inbox empties over weeks, not sittings.

### 3. Pricing sheet intake (one-off, high value)
- Paste/upload target for the Rheia price sheet and equipment costs.
  Parsed into the catalog supplement; each row becomes a priced-SKU
  rule (source: richard-qa-form).

## Data model

`qa_items` table/collection:
- id, contractor_id, kind (draft_line | rule_confirm | pricing_row)
- context (project path, sku, community, evidence)
- state: pending | answered | dismissed | superseded
- answer payload + answered_at
- resulting_rule_id (ledger back-reference)

## Non-goals

- No login friction beyond existing Designer Desktop auth.
- No free-form "describe your workflow" prompts.
- No blocking flows: every screen is abandonable mid-way without loss.
