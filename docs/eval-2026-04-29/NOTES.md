# Edge RUP Eval — Materials Rules Engine impact

**Date:** 2026-04-29
**Sample:** Enos Residence Load Calcs.rup (8 AHUs, 32 rooms, 6.6 MB)
**Staging:** `procalcs-hvac-bom-staging-00004-czd`
**Baseline:** `before-rules-engine/gen_EDGE.json` (revision before commit `ae5bd2b`)

## Headline

The rules engine recovers the equipment enumeration that the
AI-only path was silently dropping. On the same Enos RUP the AI
returned a single aggregate `equipment` line; the deterministic
layer now emits one row per AHU / condenser / heat kit / plenum
take-off, indexed to a catalog SKU.

| Metric                        | Before (AI only) | After (rules + AI) |
| :---------------------------- | ---------------: | -----------------: |
| Total line items              |               46 |                 54 |
| Rules-engine items            |                — |                  4 |
| AI items                      |               46 |                 50 |
| Equipment lines (rules + AI)  |                1 | **4 SKUs × 8 qty** |
| `total_cost`                  |       $23,162.75 |         $16,090.80 |
| `total_price`                 |       $29,267.12 |         $20,261.11 |

The cost / price drop is **expected and honest**: the rules-engine
SKUs ship with catalog `default_unit_price = 0` until Richard's
team encodes real prices. The AI-only path hallucinated quantities
*and* prices for items it had no business pricing — the new
behavior surfaces the gap rather than papering over it. As Richard
populates the catalog those zeros become real costs.

## Rules-engine attribution (from `gen_EDGE.json`)

```
[  AHVE24BP1300A]  8.0 ea   $    0.00  AHU
[      FPLJ-1712]  8.0 ea   $  180.80  Plenum round take off, 17" x 12"
[    GZV6SA1810A]  8.0 ea   $    0.00  Condenser
[      HKTSD05X1]  8.0 ea   $    0.00  ELECTRIC HEAT KIT, 5 KW
```

Scope flags (from `rules_preview_EDGE.json`):
`ahu_count=8, condenser_count=8, heat_kit_count=8` — Rheia not in
scope (raw_rup_context lacks 3-in narrative; structural duct_runs
empty), and registers were also empty in the parsed envelope, so
the Rheia and register-derived rules correctly stayed silent.

## Bug found and fixed mid-eval

The first /rules-preview run returned 0 lines for the Enos RUP.
Root cause: the parser canonicalizes equipment type to
`"air_handler"` (underscore) but `compute_scope` matched only
`"ahu"` or `"air handler"` (space). Fix in
`services/materials_rules.py::_equipment_type` normalizes underscore
to space; regression test added in
`tests/test_materials_rules.py::test_parser_canonical_air_handler_type_detected`.

Without the fix the rules engine would have been a no-op on every
Wrightsoft-parsed RUP — the exact regression this eval was designed
to catch.

## Files in this directory

| File                                       | Source                                  |
| :----------------------------------------- | :-------------------------------------- |
| `parse_EDGE.json`                          | `/api/v1/bom/parse-rup` on Enos.rup     |
| `parse_AVG.json`, `parse_EASY.json`        | Earlier RUP samples (parser unchanged)  |
| `rules_preview_EDGE.json`                  | `/api/v1/bom/rules-preview` on Enos     |
| `gen_EDGE.json`                            | `/api/v1/bom/generate` on Enos (NEW)    |
| `before-rules-engine/gen_EDGE.json`        | Same /generate call, pre-rules baseline |

## Next eval

Re-run after Richard's team encodes a meaningful subset of the
21 starter SKUs — the dollar deltas should converge as catalog
prices replace the placeholder zeros.
