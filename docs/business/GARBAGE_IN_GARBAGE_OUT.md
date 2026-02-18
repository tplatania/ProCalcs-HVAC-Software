# ProCalcs Core Product Insight: Garbage In, Garbage Out
## Date: February 19, 2026
## Author: Tom Platania (concept), Claude Opus 4.6 (documentation)

---

## THE PROBLEM PROCALCS SOLVES

ACCA-approved Manual J software (Wrightsoft, Elite RHVAC, Cool Calc, etc.) are
calculators. They execute the Manual J procedure correctly — the MATH is right.
The ACCA approval stamp means the software follows the procedure. It does NOT
mean the inputs are correct.

Contractors — whether through incompetence, laziness, or intentional manipulation —
can and do enter bad inputs to get the equipment size they want. The software
does not question the inputs. It cannot know if the contractor is lying.

**"Garbage In, Garbage Out" — the report looks official, carries the ACCA stamp,
and is completely wrong because the inputs were manipulated.**

## HOW CONTRACTORS MANIPULATE LOAD CALCULATIONS

These are real, documented practices that ProCalcs must detect:

### Input Padding (Making Loads Bigger Than Reality)
Each of these individually looks defensible. Stacked together, they double the load:

- **Design temperatures**: Using temps more extreme than ASHRAE specifies for the
  location. "It got to 108 that one week" instead of the 1% design temp of 95.
- **Infiltration gaming**: Selecting "Loose" or "Semi-Loose" when the house is
  actually Average or Tight construction. This alone can add 15-25% to the load.
- **Window manipulation**: Entering worse U-factors or SHGC values than the actual
  windows. Claiming single-pane when low-e is installed. Ignoring interior shading.
- **Duct location fraud**: Claiming ducts are in unconditioned attic when they are
  in conditioned space or encapsulated attic. Massive load inflation.
- **Occupant inflation**: Adding more people than the bedrooms + 1 standard.
- **Orientation tricks**: Putting the most glass on the hottest orientation even
  when the plans show otherwise.
- **Insulation downgrading**: Entering lower R-values than what's specified or
  installed. "I couldn't verify so I assumed the worst case."
- **Safety factor stacking**: Adding 10% here, 15% there, rounding up at every
  step. The contractor calls it "being safe." ACCA calls it oversizing.
- **Ignoring thermal mass**: Not crediting concrete/masonry construction for
  thermal mass cooling benefits that Manual J provides.
- **Wrong ventilation rates**: Inflating mechanical ventilation beyond ASHRAE 62.2
  requirements.

### Input Deflation (Making Loads Smaller — Less Common But Happens)
- Claiming tighter construction than reality to justify a smaller, cheaper system
- Using optimistic window specs to reduce solar gain calculations
- Ignoring duct losses to keep the system small

### Why Contractors Do This
- **Upsizing bias**: Bigger system = higher equipment cost = more profit on the job.
  Contractor avoids callbacks because the oversized system always meets demand
  (even though it causes humidity, efficiency, and longevity problems).
- **Inventory matching**: Contractor has a 4-ton unit on the truck. The calc says
  3-ton. Easier to fudge the inputs than make another trip to the supplier.
- **Customer pressure**: Homeowner insists on a bigger system "just to be safe."
  Contractor adjusts inputs to justify what the customer wants.
- **Ignorance**: Some contractors genuinely don't understand the inputs and use
  defaults or guesses rather than measuring or verifying.
- **Time pressure**: Proper input gathering takes hours. Guessing takes minutes.
  Many contractors skip verification because they're juggling 5 jobs.

## WHAT PROCALCS IS (AND ISN'T)

**ProCalcs is NOT a load calculation program.**
We are not competing with Wrightsoft, Elite RHVAC, or Cool Calc.

**ProCalcs IS the quality assurance layer.**
We sit on top of ANY load calc program and verify: "Can we trust what went in?"

The ACCA stamp means the calculator works.
The ProCalcs stamp means the INPUTS are verified.

## WHO NEEDS THIS

| Customer | Why They Need ProCalcs |
|----------|----------------------|
| Permit Offices | Rubber-stamping reports they don't have time to review. ProCalcs does the review. |
| Homeowners | Getting a second opinion on a contractor's recommendation. ProCalcs is that second opinion. |
| Builders | Verifying their HVAC subcontractor did the work right. ProCalcs is QA for the GC. |
| Good Contractors | Proving their calculations are legitimate and not padded. ProCalcs is their credibility stamp. |
| Energy Raters | HERS raters and energy auditors need to verify HVAC designs. ProCalcs streamlines their review. |
| HVAC Companies | QA on their own team's work before submission. ProCalcs catches mistakes before the permit office does. |
| Insurance/Warranty | Verifying proper sizing before covering equipment. ProCalcs provides the documentation. |

## HOW PROCALCS DETECTS MANIPULATION

### Automated Checks (No Human Input Needed)
These run instantly against every submitted report:

1. **Design Temperature Verification**: Cross-reference the reported outdoor design
   temps against ASHRAE data for the project location. If the report uses 100F when
   ASHRAE says 95F for that city, flag it immediately.

2. **Square Footage Cross-Check**: Compare total conditioned area against county
   tax assessor records. If the report says 3,500 sq ft but the county says 2,800,
   something is wrong.

3. **Internal Consistency Math**: Do the room areas add up to the system total? Do
   the system totals add up to the whole-house total? Do the loads per square foot
   fall within reasonable ranges? Math doesn't lie.

4. **Equipment Sizing Limits**: Is the selected equipment within ACCA Manual S
   percentages? Over 115% total cooling for an AC is a red flag. Over 140% heating
   is a red flag.

5. **Code Minimum Cross-Check**: For known year-built, are the insulation values at
   least meeting the energy code minimum for that era and climate zone? R-11 walls
   on a 2020 house in Climate Zone 5 is impossible if it passed inspection.

6. **Load-Per-Square-Foot Reasonableness**: Industry data shows proper Manual J
   calculations average 1,431 sq ft per ton in hot/mixed climates. If a report
   shows 400-600 sq ft per ton, it is almost certainly padded.

7. **Infiltration Reasonableness**: Cross-check the infiltration category against
   the year built and any available blower door data. A 2023 code-built home
   should not be classified as "Loose."

### Comparison Checks (Requires Architectural Plans)
When plans are available, additional verification:

8. **Room-by-Room Area Match**: Compare every room's reported area against the
   measured area from the architectural plans.

9. **Window Schedule Verification**: Match reported U-factors and SHGC against the
   window schedule on the plans.

10. **Wall Assembly Verification**: Match reported R-values against the wall section
    details and insulation specifications on the plans.

11. **Orientation Verification**: Confirm the building orientation in the report
    matches the site plan / north arrow on the architectural drawings.

12. **Duct Location Verification**: Check if the mechanical plans show duct routing
    consistent with the duct location assumptions in the Manual J.

### Mandatory User Confirmations (Always Required)
Regardless of whether plans are provided:

13. **Attic/Ceiling Configuration**: Full mandatory verification of attic type,
    insulation boundary, duct location, and air handler location. This is the #1
    source of oversizing errors. (See Training Guide Part 6.)

14. **Project Type Confirmation**: New construction, renovation, or equipment
    replacement? This determines which verification methods apply.

15. **Blower Door Test Data**: Was a test performed? If yes, what were the results?
    If no, the infiltration values carry lower confidence.

## THE PROCALCS CONFIDENCE STAMP

After validation, ProCalcs produces a confidence report with three possible outcomes:

**VERIFIED** (Green) — Inputs cross-checked against available data sources.
No manipulation patterns detected. Equipment sizing within ACCA limits.
This is the ProCalcs stamp of confidence.

**REVIEW RECOMMENDED** (Yellow) — Some inputs could not be independently verified,
or minor discrepancies were found. The report may be correct, but the flagged items
should be reviewed by a qualified professional.

**CONCERNS IDENTIFIED** (Red) — One or more inputs show patterns consistent with
manipulation, significant discrepancies with available data, or ACCA rule violations.
The load calculation should be revised before proceeding with equipment selection.

---

## THIS IS THE PROCALCS VALUE PROPOSITION

"Wrightsoft tells you the math is right.
ProCalcs tells you the INPUTS are right.
The math doesn't matter if the inputs are garbage."

---

Document Status: v1.0 — February 19, 2026
Requested by: Tom Platania, Creative Director
