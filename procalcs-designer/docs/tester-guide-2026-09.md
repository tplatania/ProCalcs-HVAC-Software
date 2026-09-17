# ProCalcs BOM Module — Tester Guide (September 2026)

A plain-language guide to everything we built recently and how to check
it. No technical background needed — if a step doesn't do what it says
here, that's a bug worth reporting.

## Before you start

- **Where:** the staging BOM tool (Gerald will share the link + your
  login). Sign in with your ProCalcs email.
- **Have ready:** a Wrightsoft `.rup` file that was built inside
  Wrightsoft (Reports → Bill of Materials, then save) — the tool works
  best on a built file.
- **First upload of the day may take ~25 seconds** while the system
  wakes up. That's expected, not a bug. After that it's fast.
- **How to report:** a screenshot + the project/run you were on, and
  what you expected vs. what happened. Same format as your last review
  — those were perfect.

Two parts below: **Part A is live now** — please test it. **Part B** is
built and waiting to be turned on; it's here so you know what's coming
and can test it the day it goes live.

---

# Part A — Live now (please test)

These came out of Dana's first review and are on staging today.

### A1. Cleaner duct-length numbers
- **What:** duct run lengths used to show long decimals like
  `47.23066806793213 ft`.
- **Test:** generate a BOM that has flex or metal duct; look at the
  duct lines.
- **Expect:** lengths show two decimals, e.g. `47.23 ft`.

### A2. Quick Order is organized properly
- **What:** the Quick Order summary used to lump different things
  together.
- **Test:** generate a BOM with equipment, round metal duct, and
  elbows; open the Quick Order summary.
- **Expect:** Equipment sits in its own **"HVAC Equipment"** group;
  round metal duct shows in **feet** (not "ea") under its own **"Round
  metal duct"** group; elbows have their own **"Elbows / fittings"**
  group.

### A3. No more stray "duct runs" count rows
- **What:** some BOMs showed extra "Duct runs (from .rup)" / "Registers
  (from .rup)" rows with a count that looked wrong.
- **Test:** generate a BOM from a **built** `.rup`.
- **Expect:** those extra count rows are gone. (They still appear for an
  **un-built** file, where they're useful.)

### A4. Which file the BOM came from
- **Test:** open any BOM.
- **Expect:** the header shows the source `.rup` filename next to the
  job.

### A5. Better export header (Project / Address / Client, Eastern time)
- **What:** the exported PDF/Excel used to lead with a Job ID and a UTC
  timestamp with lots of digits.
- **Test:** when generating, fill in the optional **Project name**,
  **Address**, and **Client name** fields, then download the PDF and the
  Excel.
- **Expect:** the export leads with the **Project name** in bold, shows
  Address / Client / Contractor below it, and the "Generated" time is in
  **Eastern time**, cleanly formatted (e.g. `Sep 2, 2026 10:05 AM EDT`).
  If you leave the fields blank it falls back to the Job ID.

### A6. "Without pricing" export (for bids)
- **What:** send a parts list to several contractors for competing bids.
- **Test:** on the download row, check **"without pricing"**, then
  download the PDF or Excel.
- **Expect:** the file has no price columns, no subtotals, and no grand
  total — just the parts list. Uncheck it to get pricing back.

### A7. Assistant files added equipment correctly
- **What:** adding an ERV via the assistant used to drop it into "Other".
- **Test:** in the chat assistant, ask to add an ERV (or air handler,
  condenser, heat strip) with a model number; Apply it.
- **Expect:** the new line lands under **Equipment**, with the other
  equipment.

### A8. Regenerate no longer shows a false failure
- **What:** clicking regenerate sometimes said "Regeneration failed" even
  though it worked, and clicking again made duplicate copies.
- **Test:** apply a correction, then regenerate.
- **Expect:** it completes without a false error, and you don't get
  duplicate runs. (The button also ignores a second click while it's
  working.)

### A9. No markup on contractor BOMs
- **What:** confirmed policy — contractor BOMs carry no markup; you price
  with your own supplier numbers.
- **Test:** check any priced contractor BOM.
- **Expect:** unit prices equal cost — nothing is marked up.

---

# Part B — Built, waiting to be turned on

These are finished and tested but not yet switched on in staging. When
each goes live, here's what to check. (Gerald turns these on.)

### B1. Review Workspace — mark a BOM reviewed, see the correction history
- **What it will do:** mark any BOM **Good / Needs fix / Blocked** with a
  note, and see a **correction history** — every change made to the BOM
  (what, why, who, when) — plus, on a regenerated BOM, a **"what changed
  vs the previous run"** summary.
- **How to test when live:**
  1. Open a BOM, set a review status and type a note — reload the page,
     the status/note should stick.
  2. Make a few corrections in the assistant, then look at the
     correction-history list — each correction should appear.
  3. Regenerate, then open the "Changed from run #…" card — it should
     list what was added / removed / changed.

### B2. Review readiness — which lines to check first
- **What it will do:** the tool grades each "verify" flag by how sure it
  is (low / medium confidence) and by dollar value, and shows a **"lines
  to review"** card listing the riskiest items first — low-confidence or
  high-dollar. The verify badge on a line shows its confidence.
- **How to test when live:**
  1. Generate a BOM that has verify flags (e.g. one with grille lumping
     or heat strips).
  2. Look for the **"N lines to review"** card — it should list the
     flagged lines, low-confidence ones first.
  3. Hover a **verify** badge — it should show the confidence level and
     the line's dollar value.

### B3. Cost visibility & model options (internal / Gerald)
- **What it will do:** an internal view of what the AI assistant is
  costing, plus the ability to switch the assistant to a cheaper model
  or route simple questions to a cheaper model — all without changing the
  answers you get on real work.
- **How to test when live:** mostly internal (Gerald watches the cost
  figures). From a tester's seat, the only thing to confirm is that the
  chat assistant still answers correctly and quickly.

---

## Quick report template

> **Feature:** (e.g. A2 Quick Order)
> **Project / run:** …
> **What I did:** …
> **What I expected:** …
> **What happened:** … (screenshot)
