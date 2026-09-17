# BETA evidence index (read-only) — 2026-08-06

Prepared for Tom's Codex loop per his 2026-08-06 request. Maps every
gate status claimed in `beta-definition-brief.md` §2 to its exact
evidence location. **Nothing was deployed, no cadence started, no new
customer files touched, no staging change made to produce this
document** — the only action taken was pushing already-committed local
docs/tooling to GitHub so this index can cite real SHAs.

## Evidence classes

- **[R]** — independently reproducible from GitHub alone (synthetic
  tests, code inspection).
- **[S-corpus]** — measured against the private corpus / local
  ground-truth `.rup` files; committed run logs are the artifact, the
  inputs cannot be redistributed.
- **[S-reviewer]** — reviewer-reported (Richard/Tim documents and
  in-app activity); primary documents held by Gerald, referenceable
  on request.
- **[S-staging]** — staging database rows / Cloud Run logs;
  inspectable read-only, not reproducible offline.

## Repositories and deployed revisions

| Item | Value |
|---|---|
| Repository | `github.com/tplatania/ProCalcs-HVAC-Software` |
| Branch | `dev/gerald-designer` (tip at index time: `5e33c43`) |
| BOM staging | Cloud Run `procalcs-hvac-bom-staging`, revision `00142-6tc` — source matches GitHub **through `4d15ddf`** (Tom-verified). Commits `5c46983`/`5210822` are committed, **not deployed**. |
| Designer staging | Cloud Run `procalcs-designer-desktop-staging`, revision `00097-f7n` — 147 runtime files byte-match `e28133f` (Tom-verified). Later designer syncs (`30e233a`, `5e33c43`) are docs/scripts/type-noise only, **not deployed**. |
| GCP project | `psychic-medley-469413-r3`, region `us-east1` |

Key commits referenced below: `337bd45` (day-30 flag classes),
`d2f8a5a` (day-31 gate), `4d15ddf` (pre-flight engine + regenerate
carry), `e28133f` (designer staging match), `5c46983` (synthetic tests
+ B3 logging), `7954b7c` (validation artifact + Melko criteria),
`5210822`/`30e233a` (calibration-statement corrections),
`5e33c43` (brief §0/§6 + scoreboard baseline row).

## Gate-by-gate index

### A1 — 3 consecutive clean projects · claimed: NOT green (in progress)
| Evidence | Location | Class |
|---|---|---|
| Acceptance criteria for the pending Melko confirmation | `procalcs-designer/docs/melko-acceptance-criteria.md` @ `7954b7c` | [R] (criteria) |
| Run history establishing the counter restart | staging DB runs 409/410 (Melko, phantoms baked) via `GET /api/v1/bom-runs/` | [S-staging] |

*Tom's tightening (predeclared diverse evaluation set) acknowledged —
to be defined in the loop; no current evidence claimed.*

### A2 — Rheia/conventional gate holds · claimed: green with caveat
| Evidence | Location | Class |
|---|---|---|
| Gate implementation (17 families, threshold 15) | `procalcs-bom/backend/services/bom_from_rup.py` (`CONV_DUCT_FAMILIES`, `count_conventional_duct_skus`) @ `5210822` | [R] |
| Synthetic threshold tests (both sides, boundary, margin guard) | `procalcs-bom/backend/tests/test_day31_gate_and_preflight.py` @ `5210822` — 13/13 pass | [R] |
| Calibration separation (50 Rheia max 7 vs 5 built conventional min 37) | committed run log `procalcs-designer/docs/validation-2026-07-31-rheia-gate.md` @ `30e233a`; script `procalcs-designer/scripts/corpus-analysis/validate_day28_engine_fixes.py` @ `30e233a` | [S-corpus] |
| Gate metric log line per upload | Cloud Run logs, service `procalcs-hvac-bom-staging`, logger `procalcs_bom`, pattern `"conventional duct-system SKUs in priced BOM — conventional project, suppressing Rheia takeoff"` | [S-staging] |
| Live post-fix verification (3 projects, runs deleted after) | Cloud Run request logs 2026-07-31, job_ids `verify-*` | [S-staging] |
| End-to-end tester confirmation | **PENDING — Melko fresh upload** (criterion 3 of the acceptance doc) | — |

*Caveat: "every real upload" is asserted only for the calibration
populations; Tom's reproducible-test-set tightening goes to the loop.*

### A3 — Regenerate/patch preserves user work · claimed: green
| Evidence | Location | Class |
|---|---|---|
| Carry-forward implementation | `procalcs-bom/backend/services/bom_patches.py` (`STRUCTURAL_EXTRA_KEYS`, `carry_structural_extras`), `routes/bom_runs_routes.py` (patch_ops copy, chat lineage walk) @ `5c46983` | [R] |
| Synthetic tests (copy-all, never-overwrite, bad parent) | `test_day31_gate_and_preflight.py` @ `5210822` | [R] |
| Live regenerate carrying preflight + 42 runout pieces + 50 CFM rows + 3 annotations | verification runs 415→416, 2026-07-31 (deleted after; Cloud Run logs retain) | [S-staging] |
| Tester confirmation of the fix wave (summary-sync, carry-forward, lineage chat) | Tim's comprehensive Melko document, 2026-07-30 (held by Gerald); corresponding runs 384–410 | [S-reviewer] |

### B1 — Every unreliability class flags, never guesses · claimed: green with caveat
| Evidence | Location | Class |
|---|---|---|
| Flag implementations: heat strips, empirical-only equipment, grille lumping | `bom_from_rup.py` verify_reason sites @ `337bd45`..`5210822`; passthrough in `bom_from_wrightsoft.py` @ `337bd45` | [R] |
| Structural lump evidence (DREGINFO auto/user decode) | `procalcs-bom/backend/utils/rup_register_preflight.py` @ `4d15ddf`; method doc `procalcs-designer/docs/rup-dreginfo-decode.md` @ `e28133f` | [R] + [S-corpus] |
| Unbuilt-file banner (rup_unbuilt_hint) | `bom_from_rup.py` + SPA banner @ `e28133f` | [R] |
| Expert ratification of flag-don't-guess (heat strips, Rheia scope-out) | `procalcs-designer/contractor-rules/reliable/questions.yaml` @ `e28133f` (`q.heat_strip_rule`, `q.rheia_unit_prices`, closed-expert with Richard's verbatim answers) | [S-reviewer] |

*Caveat: the class ledger is the questions/rules YAML — not yet
versioned/frozen as Tom requires, and no detector for unknown silent
guesses exists. Both go to the loop.*

### B2 — Flags are actionable · claimed: green
| Evidence | Location | Class |
|---|---|---|
| Pre-flight card naming the source fix (property sheet → rebuild → re-upload) | `procalcs-designer/src/pages/diagnostics/wrightsoft-bom-v2.tsx` @ `e28133f` | [R] |
| Verify badge with reason tooltip; drawing-notes card offering agent add | same file @ `e28133f` | [R] |
| Agent policies (no invented models/sizes, fix-path guidance) | `procalcs-designer/server/routes/bomChat.ts` system prompt @ `e28133f` | [R] |

### B3 — Loud decode failures · claimed: committed, NOT deployed
| Evidence | Location | Class |
|---|---|---|
| logger.warning with traceback + source file name on preflight decode failure | `bom_from_rup.py` @ `5c46983` | [R] |
| Deployment status | **not in revision `00142-6tc`** — held per Tom's instruction | — |

*Tom's tightening accepted: logging alone is insufficient; a visible
safe-degrade behavior for the user is loop work, currently absent.*

### C1 — Full gap-fill session without losing state · claimed: green (reviewer-reported)
| Evidence | Location | Class |
|---|---|---|
| Snipe→correct→regenerate flow implementation | `wrightsoft-bom-v2.tsx` (applyPatchOps, server-summary adoption) @ `e28133f`; `bom_runs_routes.py` @ `5c46983` | [R] (code) |
| Session completion in practice | Tim's reconciliation sessions (runs 384→389, 399→402: 26-op patch set surviving three regenerates); her 2026-07-30 document | [S-reviewer] + [S-staging] |

### C2 — Agent never fabricates · claimed: policies in place, NOT proven
| Evidence | Location | Class |
|---|---|---|
| Provenance policies (drawing objects ≠ BOM rows; no models/sizes invented; heat-strip expert policy; preflight no-estimate rule) | `bomChat.ts` system prompt @ `e28133f` | [R] (policy text) |
| One documented provenance failure + fix (Supply Duct17 hallucination → prompt correction) | prompt diff in day-29 sync (`e28133f` history); Richard's report 2026-07-28 | [S-reviewer] |
| Persisted chat transcripts for sampling | staging DB `chat_messages` via `GET /api/v1/bom-runs/<id>/chat` (14 crew/richard threads, runs 363–410) | [S-staging] |

*Per Tom: "never" is not provable from spot-checks — claimed status
downgraded here to "policies in place"; reproducible provenance test
set is loop work.*

### C3 — Correction faster than manual · claimed: NOT measured
No evidence exists. Proposed metric definition (session boundaries,
manual baseline) is loop work. Raw material available: `usage_events`
+ `chat_messages` timestamps (test actors excluded), staging DB.

### D1 — Overrides persist and reapply · claimed: architecture only
| Evidence | Location | Class |
|---|---|---|
| Override store + reapplication path | `procalcs-bom/backend` contractor-overrides service/routes; re-applied on wrightsoft rebuild (`build_bom_from_wrightsoft_lines`) @ `4d15ddf` | [R] (code) |
| Real data | **0 overrides** — telemetry query below, 2026-08-06 | [S-staging] |

Telemetry query definition: `GET /api/v1/usage-events/impact?client_id=reliable-heating-and-cooling`
on `procalcs-hvac-bom-staging` (header `X-Procalcs-Service-Token`).
Server-side exclusion of `TEST_ACTOR_EMAILS`
(gerald@procalcs.net, dev@procalcs.net, dev, admin1@, admin2@);
`include_test=1` reveals test traffic for audit.
*Tom's scoping tightening ("forever" → scoped, dated, reversible
supersession) accepted as loop work.*

### D2 — Qty/structure corrections carry through regenerate · claimed: green
Same evidence set as A3 (implementation + synthetic tests +
Tim's carry-forward confirmation after the day-29 loss incidents).

### D3 — Scoreboard movement · claimed: baseline only, supporting evidence
| Evidence | Location | Class |
|---|---|---|
| Baseline row (base n=1076: recall .696 / precision .885 / qty-acc .944; overlay 0 overrides / 0% of 270 keys) | `procalcs-designer/scripts/corpus-analysis/scoreboard_history.jsonl` @ `5e33c43`; method `monthly_scoreboard.py` @ `5e33c43` (provenance note in the row: base pass and impact fetch run separately on 2026-08-06) | [S-corpus] + [S-staging] |

*Accepted: D3 stays supporting evidence, not an independent shipping
gate.*

### D4 — Decode-wall pipeline is live · claimed: green (one full cycle proven)
| Evidence | Location | Class |
|---|---|---|
| Method + protocol | `procalcs-designer/docs/property-capture-protocol.md`, `scripts/corpus-analysis/rup_diff.py` @ `e28133f` | [R] |
| Completed cycle (grille-size wall → decoded → shipped as pre-flight) | `docs/rup-dreginfo-decode.md` @ `e28133f` → `rup_register_preflight.py` @ `4d15ddf` → card @ `e28133f` | [R] + [S-corpus] |
| Ruled-out encoding (per-piece diameter not in DUCTRUN/BALDUCT/DUCT) | negative-result scan documented in `rup-dreginfo-decode.md` §"What still needs Windows captures" | [S-corpus] |

## Reviewer sign-off records ([S-reviewer] primary documents)

Held by Gerald, available to Tom on request (contain customer project
content, so not committed): Richard — SW 55th review doc (2026-07-27),
"BOM Review notes 2026.07.30.docx" (review-order grouping, adopted in
UI); expert policy answers via Slack (heat strips, Rheia scope-out,
transcribed verbatim into `questions.yaml`). Tim — Test-2 results
table (2026-07-29), comprehensive Melko document (2026-07-30,
5/7 items dispositioned Matched).

## Summary of claim adjustments made while indexing

Producing this index against Tom's evidence standard forced three
honest downgrades vs. the brief's §2 wording: **A2** "every real
upload" → verified on calibration populations + per-upload log line,
end-to-end confirmation pending Melko; **C2** "never fabricates" →
policies in place, one documented failure fixed, not proven;
**B1** ledger exists but is not yet versioned/frozen. The brief is
the proposal; this index is the ground truth.
