# Correlation report — heat-strip sizing (Q1) and B33DHW trigger (Q2)

Full-corpus run, 2026-07-15. Input: `pairs.jsonl` (1,081 rup↔xls pairs, 12 communities).
Parse failures: **0 rup, 5 xls** → 1,076 clean pairs analyzed (830 unique xls BOMs).
Feature table: `features.jsonl` (this directory). Extraction/analysis scripts ran against
`procalcs-hvac-upstream/procalcs-bom/backend` parsers.

## What was decodable from the .rup files

| Feature | Source | Coverage |
|---|---|---|
| Condenser model, coil model, manufacturer | `utils.rup_equip_parser.parse_equipment` (EQUIP) | 1,076/1,076 |
| **Electric strip model (HK…)** — placed in the design itself | same | 734/1,076 (68%) |
| Condenser tonnage (capacity code 18/24/30/36/42/48 in model) | derived | 1,076/1,076 |
| Register CFMs + register count | `utils.rup_duct_parser.parse_baldict` (BALDICT) | 1,076/1,076 |
| Supply/return path counts, building type, duct location | `utils.rup_parser.parse_rup_bytes` | 1,076/1,076 |
| Path metadata: community, Bldg #, Lot #, CO1/CO2 stage, SEER2 tag, END, FH* plan variant, plan code (T###/V###/E###) | file path regex | varies |

**Not decodable with current parsers:** Manual-J heating/cooling load totals and floor
areas. They live in undecoded binary blocks (ROOMW / SJD / ZEQUIP records); the UTF-16
string layer only carries labels and the CTL disclaimer RTF. `_parse_rooms` returns empty
on this corpus. Register-CFM sum is the only working load proxy.

Regex gotchas fixed during the run (worth folding into the parsers): heat-kit kW must
match `HKS*05XC**` (wildcard `*` inside the SKU), and Goodman capacity codes are
zero-padded mid-string (`GSZ16**024**1B`, `GSZH50**24**10A`) — a naive `\d{2}10A` match
leaves ~30% of tonnage undecoded.

---

## Q1 — Heat strip sizing

xls kW distribution (1,076 pairs): **5 kW: 949, 8 kW: 62, 3 kW: 35, 10 kW: 17, 6 kW: 13.**

### Tonnage is NOT the driver

| RUP tonnage | kW seen (count) | mode-rule correct |
|---|---|---|
| 1.5 t | 5 kW: 560, 3 kW: 5 | 560/565 (99.1%) |
| 2.0 t | 5 kW: 232, 8 kW: 38, 3 kW: 30, 6 kW: 10, 10 kW: 9 | 232/319 (72.7%) |
| 2.5 t | 5 kW: 128, 8 kW: 24, 10 kW: 8, 6 kW: 3 | 128/163 (78.5%) |
| 3.0 t | 5 kW: 28 | 28/28 |
| 3.5 t | 5 kW: 1 | 1/1 |

Best tonnage rule = "always 5 kW" (the mode at every tonnage): **949/1,076 = 88.2%** —
identical to the majority-class baseline, i.e. tonnage adds zero information. The same
condenser (e.g. `GSZ160241B`, 2 t) pairs with 3, 5, 6, 8 and 10 kW kits, so the sizing
input must be the Manual-J heating load (not decodable), not the cooling tonnage.

### The actual rule: the strip is already in the .rup

The EQUIP block carries a placed "Elec strip" record in 734/1,076 pairs. Copying its
model to the BOM is right **725/734 = 98.8%**. The 9 mismatches are all rup↔xls
*revision skew* (Park View `V116 Hampton` 5↔10 kW across the CO Exhaust-Duct overlay;
Pennyroyal `E478 Somerset` lots 52/54/81 5↔8 kW between base and CO1/archive copies) —
the rup and xls being compared are different revisions of the same lot, not rule failures.

Where the rup has **no** strip record (342 pairs — Creekside 180, Pennyroyal 119,
Park View 40, Acuera 3), the kW spread is 5 kW: 258, 8: 34, 3: 33, 6: 9, 10: 8.
Fallbacks tested there: default 5 kW = 75.4%; register-CFM 150-bins = 80.7%;
(community, plan-variant) = 76.0%. Nothing deterministic.

**Combined decision table:**

| Rule step | Accuracy |
|---|---|
| 1. Strip model present in rup EQUIP → copy it | 725/734 = 98.8% |
| 2. Else → default 5 kW | 258/342 = 75.4% |
| **Overall** | **983/1,076 = 91.4%** |

### Q1 verdict — PARTIALLY

The heat strip is deterministic wherever the designer placed it in the .rup (68% of
pairs, 98.8% accurate — copy, don't compute). For the remaining 32% no rup-derivable
feature is deterministic: kW varies 3–10 within identical tonnage/coil, consistent with
Manual-J heating-load sizing, and the load totals are not yet decodable. Two paths to
close the residual: (a) decode the SJD/ZEQUIP binary load records, or (b) show Richard a
draft that defaults to 5 kW and ask, on a concrete Creekside/Pennyroyal lot: "this one
got an 8 kW kit — what number were you reading when you picked it?"

---

## Q2 — B33DHW dehumidifier trigger

Prevalence: 428/1,076 pairs (39.8%); 347/830 unique xls (41.8%). All results below are
xls-level (dedup) unless noted.

### Community gate (deterministic half)

Six communities **never** have it: Acuera Estates (0/38), Estates at Lake Jesup (0/34),
Park View at the Hills (0/69), Pennyroyal (0/161), Vintner Reserve (0/26), Windham Park
(0/6) — 334/334. Creekside almost always does (137/158). Community-majority alone = 681/830 (82.0%).

### Single-feature scan (mixed communities were the puzzle)

Weak/no signal: floor-area proxy `cfm_sum` best threshold <1220 = 76.7%; register count
<29 = 76.0%; tonnage <2.0 = 71.6%; second return (`return_paths>=2`) = 43–60%; ERV
presence = 43% (ERV is on nearly every BOM); lot parity = 49%; END unit = 58%;
building/plan within Aulin = 78% ceiling; plan code = 55–87% by community. None survive.

### The strong predictor: equipment generation + change-order stage (a date effect)

Within the 5 mixed communities (496 xls):

| Condenser family × stage | no dhw | dhw |
|---|---|---|
| Daikin D*6VSA — BASE | 4 | **146** |
| Daikin D*6VSA — CO1 | 1 | **57** |
| Daikin D*6VSA — CO2 | 8 | 19 |
| Daikin DZ17VSA — BASE/CO1/CO2 | 13 | **75** |
| Goodman GZV6 (SEER2-era) — BASE | **64** | 2 |
| Goodman GZV6 — CO1 | 10 | **29** |
| Goodman GZV6 — CO2 | **47** | 19 |

- Rule "Daikin condenser → B33DHW": 420/496 = **84.7%** (mixed comms).
- Rule "Daikin, OR (GZV6 AND CO1)": 439/496 = **88.5%**.
- With the never-community gate: **773/830 = 93.1%** overall (pair-level equivalent 91.4%).
- Ceiling of community × family × stage: 787/830 = 94.8%.

### Why this reads as a code-cycle/date effect, not a lot property

1. **Same lot flips across revisions:** 78 lots in mixed communities have both a
   with-B33DHW and a without-B33DHW BOM for the *same* bldg/lot/plan (26 of 52 Aulin
   lots). A lot-level physical trigger (area, orientation, end-unit) cannot do that.
2. **Stage direction is systematic:** among those conflicted lots, CO1 revisions are
   90% *with* (74 vs 8) and CO2 revisions are 72% *without* (48 vs 19) — a wave that
   added the dehumidifier at CO1 and dropped it again at CO2.
3. **Condenser family is a calendar proxy:** GZV6 is the SEER2-generation Goodman
   spec; D*6VSA/DZ17 are the older Daikin specs. SEER2-tagged folders also skew
   negative (34% vs 42% base). Newer-spec designs mostly drop B33DHW.
4. Vintner Reserve (0/26) is simply entirely in the never-group, consistent with a
   builder/program-level decision rather than plan geometry.

### Q2 verdict — CONTEXTUAL (with a strong stopgap rule)

No rup-derivable *physical* feature explains B33DHW; the best physical proxy (register
CFM total) tops out at 77%. What predicts it (93%) is *when/under which equipment
program the design was specced*: never-communities → no; Daikin-era designs → yes;
SEER2/GZV6-era designs → no except the CO1 change-order wave. That is a builder-program
decision living outside the .rup. Ask Richard one concrete question: "Aulin Bldg 2 Lot 47
has three BOMs — base without B33DHW, CO1 with it, CO2 without it, same plan — what drove
adding it and then dropping it?" (Expected answer: a builder/code-cycle directive, e.g. a
2023 FL energy-code or builder-standard change; his answer converts the stopgap rule into
a dated, deterministic one.) Until then, ship the 93% rule and flag GZV6+CO2 drafts for QA.
