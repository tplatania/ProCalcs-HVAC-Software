# ProCalcs Market Strategy: Building Departments
## Date: February 19, 2026
## Author: Tom Platania (concept), Claude Opus 4.6 (documentation)
## Status: STRATEGIC — Share with Richard

---

## THE INSIGHT

Building department plan reviewers are rubber-stamping Manual J reports because
they lack the time and specialized HVAC knowledge to verify them. They see the
ACCA software stamp and approve. They know this is a problem. They don't have
a solution.

ProCalcs IS that solution.

## THE BUILDING DEPARTMENT PROBLEM

A typical plan reviewer:
- Is a generalist covering plumbing, electrical, structural, AND mechanical
- Has 15-30 permit applications to review per day
- Spends maybe 2-3 minutes looking at the Manual J report
- Checks that it exists, looks professional, has an ACCA stamp
- Checks that the tonnage "seems reasonable" for the house size
- Approves it and moves to the next one

What they DON'T check (because they can't in 2-3 minutes):
- Whether the design temperatures match ASHRAE data for the location
- Whether infiltration values are reasonable for the construction type
- Whether room areas match the architectural plans they're also reviewing
- Whether equipment sizing falls within ACCA Manual S limits
- Whether the attic/duct configuration is correctly represented
- Whether inputs show patterns of manipulation or padding
- Whether insulation values meet current energy code minimums

**Result: Manipulated and incorrect load calculations pass through unchallenged.
Homeowners get oversized or undersized systems. Problems don't surface until
the homeowner has humidity issues, comfort complaints, or mold — months later.**

## THE PROCALCS SOLUTION FOR BUILDING DEPARTMENTS

### How It Works
1. Plan reviewer receives permit application with Manual J report
2. Reviewer uploads the Manual J PDF to ProCalcs (30 seconds)
3. ProCalcs runs all automated checks instantly (design temps, math consistency,
   equipment sizing, code minimums, manipulation patterns)
4. ProCalcs returns a confidence report in under 60 seconds

### What the Reviewer Sees

**GREEN — VERIFIED**: All automated checks pass. No manipulation patterns detected.
Equipment sizing within ACCA limits. Design conditions match ASHRAE data for the
location. Reviewer can approve with confidence.

**YELLOW — REVIEW RECOMMENDED**: Most checks pass but specific items flagged.
Report clearly identifies what to look at: "Infiltration set to Loose on new
construction — verify with contractor" or "Cooling equipment at 123% of load —
within heat pump limits but verify this is a heat pump not AC." Reviewer asks
contractor to clarify the flagged items only.

**RED — CONCERNS IDENTIFIED**: Significant issues found. "Design temperature 12F
higher than ASHRAE data for this location" or "Sum of room areas does not equal
system total" or "Equipment oversized at 145% — exceeds ACCA Manual S limits."
Reviewer rejects and sends back for correction with specific reasons.

### What This Changes
- Review time goes from "2 minutes of rubber-stamping" to "90 seconds of actual
  verification" — it's actually FASTER than the current process
- Reviewer doesn't need to become an HVAC expert — ProCalcs IS the expert
- Rejections come with specific, documented reasons (not "it doesn't look right")
- Creates an audit trail for the department
- Protects the jurisdiction from liability

## THE FLYWHEEL EFFECT

This is the beautiful part. Once building departments adopt ProCalcs, it creates
a self-reinforcing cycle:

1. **Building department starts using ProCalcs** → bad calculations get rejected
   with specific reasons

2. **Contractors learn they can't slip bad calcs through** → they start being
   more careful with their inputs (behavior change)

3. **Smart contractors start running ProCalcs themselves BEFORE submitting** →
   they catch their own mistakes and avoid rejection delays (now they're
   paying customers too)

4. **Homeowners hear about ProCalcs** → they request ProCalcs validation as a
   second opinion before approving an HVAC install (consumer market opens)

5. **Other building departments hear about it** → building officials talk to
   each other at ICC conferences, state code councils, and regional meetings.
   Adoption spreads jurisdiction by jurisdiction.

6. **HVAC companies adopt it for internal QA** → companies that want to
   differentiate on quality use ProCalcs to verify their own team's work
   before submission

**End state: ProCalcs becomes the industry-standard verification layer between
the load calculation software and the permit approval. Everyone uses it.**

## BUSINESS MODEL FOR BUILDING DEPARTMENTS

### Pricing Approach (to be refined)
Building departments operate on tight budgets, but they process volume.
Potential models:

- **Per-review fee**: $X per Manual J report validated. Simple, scales with volume.
  Department passes cost to permit applicant as part of permit fee.

- **Annual subscription**: Flat annual fee based on department size / permit volume.
  Predictable budget item for the department.

- **Tiered plans**: Basic (automated checks only) vs. Premium (automated + plan
  comparison when architectural plans are also uploaded).

### Key Selling Points for Building Officials
- Reduces liability — documented verification process
- Saves time — faster than manual review
- Catches real problems — specific, technical flags not just gut feelings
- Creates audit trail — every review is documented
- No HVAC expertise required — the tool IS the expert
- Revenue neutral — cost can be passed to permit applicant

## GO-TO-MARKET STRATEGY

### Phase 1: Prove It Works (Where We Are Now)
- Build the validator
- Test against real Manual J reports (Scott Residence is our first)
- Get Richard's input on what building departments actually need
- Identify 2-3 friendly building departments to pilot

### Phase 2: Pilot Program
- Offer free pilot to 2-3 building departments (3-6 month trial)
- Collect data on how many reports get flagged and what the flags are
- Refine the system based on real-world usage
- Get testimonials from building officials

### Phase 3: Regional Expansion
- Present at state code council meetings
- Attend ICC conferences (International Code Council)
- Partner with state HVAC licensing boards
- Target states with strong energy code enforcement first:
  California, Washington, Oregon, Massachusetts, Vermont, etc.

### Phase 4: National Standard
- Seek ACCA endorsement or partnership
- Integrate with existing permit management software
  (Accela, OpenGov, CivicPlus, etc.)
- Become the de facto standard for HVAC permit verification

## COMPETITIVE LANDSCAPE

**Who else is doing this? Almost nobody.**

- Wrightsoft, Elite RHVAC, Cool Calc — they MAKE the reports, they don't verify them
- Conduit Tech — focused on making load calcs easier with iPad LiDAR, not verification
- AutoHVAC — AI-based load calcs from blueprints, but also a calculator not a verifier
- HERS raters — do some verification but it's manual, expensive, and focused on
  whole-house energy, not HVAC-specific input validation

**ProCalcs would be the FIRST dedicated verification tool for Manual J reports.**
This is a blue ocean opportunity.

## THE BIGGER PICTURE

If ProCalcs becomes the standard verification layer:
- Every Manual J report in the country passes through our system
- We accumulate the largest dataset of HVAC load calculations ever assembled
- We can identify regional patterns, common errors, contractor quality metrics
- We can provide industry benchmarking data
- We become indispensable infrastructure for the HVAC industry

---

## ACTION ITEMS
1. Ask Richard about his building department contacts and relationships
2. Research permit management software APIs (Accela, OpenGov) for future integration
3. Identify 2-3 building departments in NC that might pilot
4. Research ICC conference schedule for presentation opportunities
5. Draft a one-page pitch specifically for building officials

---

Document Status: v1.0 — February 19, 2026
Originated by: Tom Platania, Creative Director (from a cruise ship — best ideas
come when you're relaxed and looking at the ocean)
