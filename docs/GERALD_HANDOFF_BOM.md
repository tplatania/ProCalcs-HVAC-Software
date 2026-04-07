# Gerald — Developer Handoff
## ProCalcs AI-Powered BOM | Phase 1 Build
### April 7, 2026

---

## GITHUB REPOSITORY

**https://github.com/tplatania/ProCalcs-HVAC-Software**
Branch: `main`
Clone: `git clone https://github.com/tplatania/ProCalcs-HVAC-Software.git`

---

## START HERE — READ THESE FILES IN ORDER

Before writing a single line of code, read these files in the repo:

1. `HANDOFF.md` — Project history and strategic context
2. `docs/ideas/AI_Powered_BOM_Contractor_Profiles.md` — Full BOM concept spec
3. `docs/ideas/Wrightsoft_Default_Template_Parsed.md` — ProCalcs Wrightsoft defaults decoded

---

## WHAT WE ARE BUILDING

An AI-powered Bill of Materials (BOM) module that lives inside the
existing ProCalcs Designer Desktop application.

**The one-sentence version:**
When a designer finishes an HVAC job in Designer Desktop, the AI reads
the completed design and automatically generates a complete, itemized
materials list — customized to that specific client's pricing, part
names, and supplier preferences.

**This is Phase 1. The Validator is shelved for now.**

---

## THE BUSINESS CONTEXT (READ THIS — IT MATTERS)

ProCalcs does HVAC load calculations and duct designs for builder clients
like Beazer, D.R. Horton, and Lennar. Designers use Wrightsoft
Right-Suite Universal to draw the designs.

The problem: after every completed design, someone on the client's team
manually builds a materials list. That takes hours, it's error-prone,
and it happens on every single job.

The solution: ProCalcs sells an AI-generated BOM as an add-on upsell
at $75-$100 per job. The BOM is customized per client using a saved
profile. Richard (Design Manager) and Windell maintain client profiles.
Designers do nothing different — the BOM is automatic.

**We analyzed Wrightsoft's own BOM database (RPRUWSF.mdb):**
38,757 line items. Almost all priced at $0.00. Their system requires
manual setup per contractor. Nobody does it. That's our opening.

---

## HOW THE BOM WORKS — FUNCTIONAL SPEC

### Step 1: Designer Finishes a Job
Designer completes the HVAC design in Designer Desktop as normal.
No new steps. No new screens.

### Step 2: BOM Triggers Automatically
When the job is marked complete (or a "Generate BOM" button is clicked),
the system reads the finished design data.

### Step 3: AI Reads the Design
The AI analyzes:
- Duct run lengths and sizes (rectangular trunk + flex branch)
- Fittings (elbows, collars, boots, transitions)
- Equipment selected (AC unit, furnace, AHU)
- Register/grille types and locations
- Building type and duct location (attic vs. crawlspace vs. conditioned)

### Step 4: AI Generates the Full Materials List
Two layers:

**Layer 1 — Drawn items** (what Wrightsoft already tracks):
- All duct runs with lengths and sizes
- All fittings by type and size
- All registers/grilles by type
- Selected equipment

**Layer 2 — AI-estimated consumables** (what nobody builds):
- Mastic (gallons, based on duct surface area)
- Foil tape (rolls, based on duct linear feet)
- Hanger straps (quantity, based on run lengths)
- Sheet metal screws (boxes, based on connection count)
- Mastic brushes
- Any other job-type-specific consumables

### Step 5: Client Profile Applied
The system looks up which client this job belongs to and applies
their saved profile:
- Their pricing per unit (from their distributor price list)
- Their preferred part names and numbers
- Their markup tier for this job type
- Their preferred brands

### Step 6: Output Generated
BOM outputs as a clean document inside Designer Desktop:
- Printable / exportable to PDF
- Goes out with the standard design deliverable package
- Client-facing version hides cost, shows price

---

## THE CLIENT PROFILE — DATA STRUCTURE NEEDED

Each client (Beazer, D.R. Horton, etc.) needs a saved profile.
This is the core data architecture to design.

A profile contains:

```
ClientProfile {
  client_id
  client_name
  supplier_name          // e.g. "Ferguson"
  
  // Consumable costs (what they pay, not what we charge)
  mastic_cost_per_gallon
  tape_cost_per_roll
  strapping_cost_per_roll
  screws_cost_per_box
  brush_cost_each
  
  // Markup tiers
  markup_equipment_pct
  markup_materials_pct
  markup_consumables_pct
  
  // Custom part name mappings
  part_name_overrides {
    standard_name -> their_name
    standard_sku  -> their_sku
  }
  
  // Brand preferences by category
  brand_preferences {
    category -> preferred_brand_code
  }
  
  // Output preferences
  default_output_mode    // "full" | "materials_only" | "client_proposal"
  
  // Job history (grows over time)
  job_history []
}
```

Richard manages these profiles via an admin interface (to be designed).

---

## WHERE THE BOM LIVES — UI INTEGRATION

The BOM is NOT a standalone tool. It is a panel or tab inside the
existing ProCalcs Designer Desktop application.

**Key questions for Gerald to answer:**
1. What format is the completed design data in when a job is done in
   Designer Desktop? (PDF export? Database record? JSON? Something else?)
   This is what the AI reads. It determines everything.

2. What is the cleanest way to add a BOM tab/panel to the existing
   Designer Desktop UI without disrupting the current layout?

3. Where does client/job data currently live — existing database,
   flat files, cloud? The profile system needs to hook into this.

4. Is Designer Desktop a web app, Electron app, or native Windows app?
   This determines how we call the AI API.

---

## TECHNICAL APPROACH

### AI Layer
We use the Anthropic Claude API (claude-sonnet-4-20250514) to:
- Read the design data
- Reason through consumable quantities
- Apply industry-standard installation knowledge
- Return structured JSON with the full BOM

The AI prompt will include:
- The design data (duct runs, fittings, equipment, registers)
- The client profile (pricing, preferences, markup)
- Instructions to output structured BOM JSON

### Profile Storage
Client profiles live server-side (not per-machine). When a designer
opens a job for Client X, the profile for Client X loads automatically.
No Richard having to push files to individual desktops.

### Output
BOM renders inside Designer Desktop as a formatted table.
Export to PDF for the client deliverable.

---

## WHAT WRIGHTSOFT USES AS DEFAULTS (ProCalcs Standard)

From the parsed ProCalcs Wrightsoft template (see repo doc):

- **Duct method:** Rectangular trunk + flex branch (Equal Friction sizing)
- **Default weather:** Tampa, FL (Tampa Intl AP)
- **Default system:** Split AC + Gas Furnace
- **Default building:** Single level, ducts in attic, vented, R-30
- **Brands already loaded:** Carrier, Bryant, Goodman, Rheem, Mitsubishi,
  LG, Gree, MRCOOL, Daikin, Fujitsu, Unico, and others

The AI BOM needs to understand these defaults so it can reason correctly
about material types and quantities.

---

## WHAT IS NOT IN SCOPE (YET)

- The Manual J Load Calc Validator — shelved, not being built now
- ACCA certification — not relevant to the BOM
- Outside contractor licensing — internal ProCalcs use only for now
- Labor calculation — optional future add-on, not Phase 1

---

## DEPLOY TARGET

Google Cloud Run (existing infrastructure decision).
Designer Desktop connects to cloud-hosted API endpoints.

---

## REPO STRUCTURE (current)

```
ProCalcs-HVAC-Software/
├── HANDOFF.md                        ← Start here
├── PROJECT_RULES.md                  ← Team rules
├── docs/
│   ├── ideas/
│   │   ├── AI_Powered_BOM_Contractor_Profiles.md   ← BOM concept spec
│   │   └── Wrightsoft_Default_Template_Parsed.md   ← WS defaults decoded
│   ├── Build_Plan_v2.docx            ← Original plan (pre-BOM pivot)
│   └── acca/                         ← ACCA protocol docs
├── changelog/                        ← Session history
├── phase1_validator/                 ← Shelved — do not build
└── shared/
    └── plan_reading_guide/           ← AI plan reading reference
```

---

## FIRST QUESTIONS TO ANSWER BEFORE CODING

1. **What format is the design output from Designer Desktop?**
   The AI input format depends entirely on this answer.

2. **Is Designer Desktop web-based or native Windows?**
   Determines API call architecture.

3. **Where does job/client data currently live?**
   Profile system needs to integrate here.

4. **Can we add a tab or panel to the existing Designer Desktop UI?**
   If yes, what's the framework — React, WinForms, Electron, other?

Tom will get these answers from the Designer Desktop team and feed
them back before any coding begins.

---

## CONTACT

Tom Platania — Creative Director
tom@procalcs.net | 772-882-5700

*This handoff prepared April 7, 2026*
