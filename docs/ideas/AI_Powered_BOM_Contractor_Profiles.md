# AI-Powered BOM with Contractor Intelligence Profiles
### ProCalcs Feature Concept | Status: IDEA — Not Yet Scoped

---

## The Problem with Wrightsoft's BOM

Wrightsoft's Bill of Materials has existed for years but never achieved widespread adoption because of three fatal flaws:

1. **Time cost** — Every fitting, material, and consumable had to be manually entered and maintained per contractor. The library never built itself.

2. **Exact-match rigidity** — If the designer selected a part in the drawing that didn't perfectly match the library entry, it didn't register. One wrong selection and the BOM broke.

3. **Pricing variability** — Wrightsoft's database ships with $0.00 on nearly every item. Every contractor pays different prices from different suppliers with different markups. A universal price list is useless. Maintaining a custom one was a part-time job.

**Confirmed via database analysis:** Wrightsoft's RPRUWSF.mdb (their Right-Proposal BOM database) contains 38,757 line items — the vast majority priced at $0.00. The structure is there. The intelligence never was.

---

## What Wrightsoft Does Handle Automatically

To be clear about where WS starts and where ProCalcs wins:

- Auto-calculates duct run lengths as the designer draws in RightDraw
- Auto-adds register/grille type when the correct grill is selected during design
- Auto-populates selected HVAC equipment into the BOM
- Counts drawn fittings (elbows, transitions, boots, collars)

This covers the **drawn, named, visible objects** — roughly 80% of the parts list.

---

## What Nobody Has Ever Solved — Until AI

The remaining 20% is what kills job margins: **the stuff nobody draws.**

No one draws a tube of mastic. No one draws a roll of foil tape. No one draws the mastic brushes, the sheet metal screws, the duct strapping, the wire hangers, the condensate line fittings, the PVC primer. These are field materials — the things every experienced installer knows to pull from the truck but no software has ever captured automatically.

ProCalcs AI reads the completed design and **reasons** its way to the full materials list:

> *"This design has 340 LF of duct across 14 runs. At industry standard application rates, that's approximately 2.1 gallons of mastic, 4 rolls of foil tape, 14 hanger straps, 3 mastic brushes..."*

No library to build. No part numbers to match. Just AI applying field knowledge to a finished design.

---

## The Contractor Intelligence Profile

The core innovation: a **one-time setup per contractor** that makes every future job feel like it was built by someone who works there.

### What the Profile Stores

**Pricing and Supplier Info**
- Supplier name(s) — Ferguson, Winsupply, Johnstone, etc.
- Their cost per unit on consumables (mastic per gallon, tape per roll, strapping per 50-ft roll, screws per box, etc.)
- Equipment markup tiers by category
- Material markup tiers by category
- Labor rates per task type (optional — if they want labor included)

**Custom Part Names and Numbers**
- Their terminology mapped to standard categories — if they call it a "4-inch snap collar" instead of COLLAR1, that's what prints
- Their supplier's part numbers, not Wrightsoft's generic SKUs
- Brand preferences per category (e.g., always Rectorseal mastic, always Nashua tape)

**Markup and Bid Logic**
- Standard markup profile
- Competitive bid profile (reduced margin)
- T&M profile (cost + labor)
- Output can be generated in any mode per job

**Job History (Over Time)**
- As jobs accumulate, AI compares estimated vs. actual consumable usage
- Flags outliers: "This job's mastic estimate is 40% above your historical average for similar square footage — confirm design or adjust"

---

## How It Works at Job Time

1. Designer completes the drawing in ProCalcs
2. AI reads the finished design — duct lengths, sizes, fittings, equipment, registers
3. AI applies the contractor's saved profile
4. BOM outputs in **their language, their part numbers, their prices, their markup**
5. Ready to print, export to PDF, or send to client

The output looks like it was built by someone who has worked at that contracting company for years.

---

## Output Modes

| Mode | What It Shows |
|---|---|
| **Full BOM** | Every item — drawn parts + AI-estimated consumables |
| **Materials Only** | Strips out equipment, just field materials and consumables |
| **Labor + Materials** | Full job cost including labor at their rates |
| **Client Proposal** | Customer-facing version — clean pricing, no cost exposure |
| **Cost Estimate** | Internal cost only, no markup shown |

---

## The Onboarding Play

**First job:** ProCalcs walks the contractor through a guided profile setup — supplier, pricing, preferred parts, markup tiers. Takes 30–45 minutes once.

**Every job after:** Fully automated. The profile runs in the background. The contractor never touches a price list again.

**The more jobs they run:** The smarter the profile gets. AI refines consumable estimates based on real historical data from that contractor's actual jobs.

---

## Why This Is a Moat

Once a contractor has their pricing, their part names, their markup logic, and their historical job data baked into ProCalcs — **leaving means starting over from scratch.**

Wrightsoft offers none of this. Their $0.00 database is the same blank slate for every contractor on earth. There is no memory, no personalization, no learning.

This isn't just a feature. It's a **switching cost that compounds over time** — and it gets stronger the longer a contractor stays.

---

## Competitive Positioning

| Capability | Wrightsoft | ProCalcs AI BOM |
|---|---|---|
| Auto-calculates duct lengths | YES | YES |
| Auto-adds drawn equipment | YES | YES |
| Consumables estimation (mastic, tape, etc.) | NO | YES |
| Per-contractor pricing profiles | NO | YES |
| Custom part names per contractor | NO | YES |
| Supplier-specific part numbers | NO | YES |
| Multiple bid/markup output modes | NO | YES |
| Historical job learning | NO | YES |
| Setup time for new contractor | Hours/days | 30–45 min once |

---

## Phase Placement

This feature is **not Phase 1 (Validator)**. It belongs in **Phase 2 (Experience Layer)** — after ProCalcs has market presence and active contractors on the platform.

However, the **data architecture for contractor profiles should be designed in Phase 1** so it doesn't have to be rebuilt later. Store the profile schema early, even if the BOM feature itself isn't live yet.

---

*Document created: April 2026*
*Origin: Competitive analysis of Wrightsoft Right-Proposal BOM database (RPRUWSF.mdb)*
