# Data Sources Contract — ProCalcs BOM Generator

**Status:** Authoritative. Drafted Day-14 (2026-06-01) after 4 rounds of Richard's team testing repeatedly surfaced the same class of issue: us trying to be clever about auto-extraction where a clear human-vs-machine boundary was missing.

**Purpose:** declare, per BOM data domain, where the value comes from and whether it's deterministic, user-encoded, or computed. Every change to the engine should consult this doc *before* introducing a new extraction path. If a domain isn't on the list, it needs a decision before code lands.

The rule that backs every entry below is Tom's framing from Slack: *use what Wrightsoft produced; don't recreate it.* When Wrightsoft produced the data and we can read it, we read it. When Wrightsoft produced it but we can't read it (binary fields we haven't decoded), the user pastes it. When Wrightsoft didn't produce it at all, we compute it from rules or the user enters it.

---

## The contract

| # | Data domain                  | Source of truth          | How                                                                |
|---|------------------------------|--------------------------|--------------------------------------------------------------------|
| 1 | Equipment models             | **Deterministic** (RUP)  | `_extract_equipment_models` walks the `EQUIP` section; per-model line emission via `_expand_equipment_models` |
| 2 | Equipment quantities         | **Deterministic** (RUP)  | `AHU - N` naming pattern in `_parse_equipment`; condenser/heat-kit defaults 1-per-AHU when EQUIP is sparse |
| 3 | Duct sizes present (round)   | **Deterministic** (RUP)  | `_extract_duct_summary` — `cfm N "` branch pattern + explicit `round/vinyl/D=N` patterns |
| 4 | Duct sizes present (rect)    | **Deterministic** (RUP)  | `_extract_duct_summary` — `Duct W " x H "` pattern, normalized larger-first |
| 5 | Duct type counts             | **Deterministic** (RUP)  | `DTYPREF` section count (ShtMetl / VinlFlx / RectFbg) |
| 6 | Supply vs return path counts | **Deterministic** (RUP)  | `_extract_duct_summary` — duct-ID prefix counts (`st`/`sb`/`sr` vs `rb`/`rt`/`rrs`) |
| 7 | **Duct LF per size**         | **User-encoded** + cache | Form on BOM Engine page; paste from Wrightsoft Supply Actual Ln(ft); cached per RUP SHA-256 in `rup_duct_totals` so re-uploads pre-populate |
| 8 | **Return duct LF per size**  | **User-encoded** + cache | Same form, return columns |
| 9 | Fittings count + type        | **AI-estimated** (today) — **deterministic candidate (next)** | AI prompt is constrained to RUP-actual sizes; `FITNG` section has 24 entries waiting to be wired |
| 10 | Registers                   | **Deterministic** (RUP)  | `_parse_rooms` + register-shape heuristics |
| 11 | Consumables quantities      | **Deterministic** (rules) | `per_lf_ratio` rules in `materials_rules` (mastic / foil tape / hanger straps / screws / brushes) |
| 12 | **Consumables prices**      | **User-encoded** (per-contractor) | `contractor_overrides` upsert via the inline edit drawer |
| 13 | Labor hours per task        | **User-encoded** (per-contractor) | `ClientProfile.labor` block (per-AHU / per-condenser / per-duct-LF hours + hourly rate) |
| 14 | Labor prices                | **Computed**             | `generate_labor_lines` — `hours × rate`, markup applied |
| 15 | **Per-SKU unit prices**     | **User-encoded** (per-contractor) | `contractor_overrides`. Tom's explicit decision: "everyone's pricing will be different, even if through the same distributor in the same location — that will be us getting directly from client and putting it." |
| 16 | Catalog → SKU translation   | **Deterministic** (catalog) | Wrightsoft `mapped_parts.csv` + DFUnit equipment library |
| 17 | Discovered Src+Name combos  | **Auto-learned** (cache) | `discovered_mappings` table — first-seen passthrough, second-seen tagged Verified |
| 18 | Equipment brand inference   | **Deterministic** (RUP)  | `_extract_inferred_brand` — overlays "(Trane)" on equipment descriptions |

---

## What the contract forbids

These are anti-patterns we've fallen into before. Don't.

- **Inventing data the RUP didn't carry.** AI duct-size hallucination (Comparison Summary 4.0) was this. Fix: constrain prompt to parser-extracted sizes, then user-encode the LF.
- **Auto-extracting low-confidence numbers and shipping them as deterministic.** The Day-14 binary-cracking experiment yielded 10″ within 7% but 4″/6″/8″ off by 35–80%. Shipping that would have created false confidence. Belongs in **user-encoded** until accuracy ≥95% across all sizes.
- **Mixing strategies on the same domain.** Pick one column from the table above. If you need to change it, change it in the doc first, then in code. Mid-implementation strategy switches are how rounds 1–4 of testing kept finding the same class of issue.
- **AI emission for any "Deterministic" row.** The AI prompt now carries a DUCT SYSTEM CONSTRAINT block and a known-LF suppression. If a deterministic field shows up as AI-sourced on a BOM, that's a regression — investigate the suppression layer, don't add another AI prompt rule.

---

## Workflow consequences

The contract implies a specific contractor workflow:

1. **Upload `.rup`** → parser extracts equipment models, duct sizes, types, paths, registers (deterministic — rows 1–6, 10)
2. **Paste Wrightsoft Supply Actual Ln + Return Actual Ln** into the BOM Engine form (rows 7–8). Cached per-RUP for re-uploads.
3. **Generate** → deterministic + computed lines emit; AI fills only the genuinely-non-deterministic gaps (today: fittings — row 9, until we wire FITNG)
4. **Inline-edit any line** to add a SKU translation correction or unit price (rows 12, 15). Persists per-contractor.
5. **Download PDF or XLSX** for customer delivery

When the contractor has a Wrightsoft `.xls` export instead of just a `.rup`, the path collapses to **deterministic mapping + per-SKU pricing** with no AI involvement at all — that's the `/from-wrightsoft` endpoint and the Wrightsoft BOM page.

---

## Adding a new domain

If a future change introduces a BOM field not on the list:

1. Pick the source of truth column with the most justification (Deterministic > Computed > User-encoded > AI-estimated, in that order)
2. Add a row to the table above with the same shape
3. Then write the code
4. Add at least one test that validates the source-of-truth choice against a real fixture (Richard's 79th Ct RUP is the regression baseline)

Reviewers should reject any change that introduces a new emission path without a corresponding row update here. That's the single discipline that keeps the engine manageable.

---

## Open items at time of writing

- Row 9 (fittings) is the next deterministic conversion candidate. `FITNG` section in 79th Ct has 24 entries; we haven't decoded the per-entry layout yet. Tracked separately from the contract itself — moving fittings from AI to Deterministic doesn't change the contract's shape, just the value in that row.
- Customer-facing PDF/XLSX branding (contractor logo + business address) is product polish, not a data-sources concern.
- Multi-tenant data isolation is an infra/security concern, not a data-sources one.
