# Email-mining report — closing 3 provisional questions from Zoho archive emails

Date: 2026-07-16 · Pass: P5 (email documentary pass)
Downloads: 22 `.msg` files → `emails/` (parsed text in `emails/parsed/`, extracted
attachments in `emails/attachments/`). Rate-limited API walk, no bulk export;
quotes below are minimal answering sentences only.

---

## Q1 — q.dehumidifier_trigger: VERDICT **CLOSED-DOCUMENTARY**

**Answer: it was a Beazer (builder) spec revision, bundled with the R-32 Goodman
GZV6SA equipment switch — not a code cycle and not a lot property. The
dehumidifier was a townhome-spec item that Beazer removed from all townhome load
calcs in Feb–Mar 2025.**

Evidence (thread present in every Aulin/Riverwalk CO1/CO2 lot folder,
e.g. `Aulin Square Towns/Lot Specific/Building 2/Lot 14 T331 FHL/Lot 14 T331 CO1|CO2/Emails/`):

1. Charles Pratt (Planning & Design Product Manager, Beazer Homes FL),
   **2025-02-07**, subject "R-32 Goodman GZV6SA Heat Pump Equipment":
   > "A final decision has been made to switch to the Goodman GZV6SA equipment across all communities."
   Priority 2 of the same email:
   > "I'm not 100% sure if the load calcs have the dehumidifier for the townhomes included in the data, but if so, I need a test design for the master files for Aulin Square Towns & Towns at Riverwalk with all of the new specifications and the dehumidifier removed."

2. Charles Pratt, **2025-03-05** (same thread, quoted in the CO2-folder copy
   `RE_ R-32 Goodman GZV6SA Heat Pump Equipment 13-03-2025 15:44:58:562.msg`):
   > "I have another recent change to this priority list for townhome communities only. The dehumidifier will be removed from all load calcs."
   and, per community:
   > "Aulin Square Towns – the master set was recently revised as a test sample that will remain the new standard without a dehumidifier for new lot orders … Building 5, 4, & 2 will have all new specs and the dehumidifier removed"
   Towns at Riverwalk and Towns at Greenleaf get the same instruction;
   ProCalcs' CO estimates sent 2025-03-06, Beazer "Approved" 2025-03-07.

Why this fits the corpus pattern exactly:
- **CO1 vs CO2 flip (Aulin Bldg 2 Lot 14 etc.)**: CO1 revisions were cut against
  the pre-Mar-5 spec (dehumidifier still in); CO2 implements "all new specs and
  the dehumidifier removed" — hence add-at-CO1 (90%), drop-at-CO2 (72%).
- **6 communities never have it**: the Feb 7/Mar 5 emails frame it as "the
  dehumidifier for the townhomes" / "townhome communities only" — single-family
  communities never carried it in spec.
- Confirms the P2 era rule (GZV6/SEER2 era → no dehumidifier) and supplies the
  causal mechanism: builder spec revision, client-side decision.

Engine action: unchanged (93% era rule), but the rule can now be stated as a
dated spec cutover (Beazer townhome spec, dehumidifier removed 2025-03-05) and
the Richard confirmation line can be dropped.

---

## Q2 — q.heat_strip_rule: VERDICT **PARTIAL**

**Finding: no kW band table exists in email. What the emails document is the
mechanism behind the legacy-era variance: heat-strip kW in Creekside/
Pennyroyal/Park View era files was set — and repeatedly corrected — to match
the builder's equipment spec and what was actually field-installed during the
SEER→SEER2 transition, not a stable Manual-J band.**

Evidence:

1. `Pennyroyal/Lot Specifics/Lot 44 E478 Somerset TUN RH N/Emails/RE_ Wrong Heat Strip Specced for PR 44.msg` —
   Bryan Pippin (Area Manager, Beazer), **2023-01-05**:
   > "Looks like ProCalcs specced an 8 KW heat strip for lot 44. Should be a 5 KW. Can you get with them to have this corrected please?"
   Charles Pratt, same day: "This lot was not on my list for SEER2 equipment changes";
   then **2023-01-06**, after field verification of the installed coil (AVPTC29B14):
   > "we need all design reports for these lots to be revised as soon as possible to reflect the correct heat strip, air handler coil, and 16 SEER/ 13 EER"

2. `Pennyroyal/Lot Specifics/Lot 43 E293 Brentwood/Lot 43 Brentwood CO1 SEER2/Emails/…Wrong Heat Strip…` —
   Emily Joiner (HERS rater, SkyeTec), **2023-02-03**: a 15.5 SEER system was
   installed; "The HVAC Design Report does not match and will require correction
   if the current model numbers installed remain in place."

3. Equipment pairing spreadsheets circulated Nov 2022 (Dana Poppell → Charles
   Pratt, "Equipment Pairings", attachments `GSZH5_AMST.xlsx`,
   `DZ6VS_DaikinFIT.xlsx`; later `R32 FIT HP WITH GOODMAN EQUIVALENT.xlsx` in the
   2025 thread) are AHRI condenser/air-handler pairings — **no heat-strip kW
   column**. Sizing authority sat with Beazer/installer per lot.

Implication for the ledger: the legacy-era kW variance (3–10 within one tonnage)
is substantially **revision churn from the SEER2 equipment transition and field
corrections**, which is why no tonnage rule fits. The engine action stays
"copy strip from EQUIP when present; flag needs-input otherwise". The Richard
one-liner remains, but sharpened: "for legacy-era files with no strip in the
design file, kW followed the builder/installer equipment spec of the day —
confirm there is no standing kW band we should encode."

---

## Q3 — q.takeoff_sku_generation: VERDICT **CLOSED-DOCUMENTARY (mechanism); SKU digits remain corpus-inferred**

**Answer: the 040/050 → 041/051 split tracks a dated Rheia design-system
generation cutover — "Phase 2" — effective July 1, 2022. Older-era lot releases
(Creekside/Pennyroyal/Park View phase 1) predate it; later communities/releases
are Phase 2.**

Evidence:

1. `Park View at the Hills/Lot Specs/Lot 2057 V111 Cambridge SCL/Emails/Park View at the Hills 50's - Phase 2 Rheia HVAC Designs Kick-Off.msg` —
   Charles Pratt (Beazer), **2022-08-09**, to ProCalcs, Airflow Designs,
   Builders FirstSource, TSG, A&B Electric:
   > "As of July 1st and going forward, all new lot releases will be under the Phase 2 HVAC Rheia design system."
   (plus new truss-chase requirement per the HVAC duct layout design).

2. Reply, Daniel Henry (Builders FirstSource), **2022-08-10**:
   > "I have revised lots 2-057, 2-058 and 2-068 for the new duct system"
   — third parties re-engineering permitted lots to "the new duct system"
   confirms a physical product/system generation change, not a paperwork rename.

3. Context (earlier, distinct event): `General Documents/1 - General Emails/RE_ Beazer FL - Change in BOM.msg` —
   Charles Pratt, **2022-02-15**, with Rheia VP Chris Edgren on thread: previous
   master designs "were loaded heavily with Rheia parts and accessories based on
   the use of I-Joist floor systems" and were revised. This documents that Rheia
   BOM composition was actively revised by Rheia/Beazer during 2022 — background
   for why early-community BOMs differ structurally.

Caveat: no email literally writes "10-01-040 → 10-01-041". The email gives the
generation change and its cutover date; the mapping of Phase 1 → 040/050 and
Phase 2 → 041/051 rests on the (already-strong) corpus correlation that the
NS-ERV / absent-strip / 040-SKU legacy cluster is exactly the pre-cutover
communities. Combined email + corpus, the confirmation line for Richard can be
reduced to a statement rather than a question, or dropped.

---

## Files retrieved (all under `/Users/geraldvillaran/Procalcs/full-corpus-run-2026-07-15/emails/`)

22 .msg (Aulin Lot 14 CO1/CO2 R-32 thread ×4, Equipment Pairings ×2, Exhaust
Ducts ×1, Wrong Heat Strip PR44 ×2 + PRYL43 ×2, Change in BOM ×2, material
sheets ×2, Creekside Installation Changes ×1, Creekside BOM Sheet ×1, Riverwalk
Rheia Masters ×1, Park View Phase 2 Kick-Off ×2, Creekside Rheia Commissioning
×2); attachments incl. `R32 FIT HP WITH GOODMAN EQUIVALENT.xlsx`,
`GSZH5_AMST.xlsx`, `DZ6VS_DaikinFIT.xlsx` (AHRI pairings, no strip kW),
`HC_PRYL 43_REV11.pdf` (scanned, no text layer).

Nothing committed to git.
