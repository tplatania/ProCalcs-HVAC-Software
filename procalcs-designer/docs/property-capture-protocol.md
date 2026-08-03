# Property-sheet capture protocol (for Richard / designers)

**Day-31. Goal:** decode which Wrightsoft property-sheet fields drive
BOM mapping, by capturing before/after `.rup` saves around single
property changes. Each clean pair ≈ one decoded field. This directly
targets the current decode walls: grille size mapping (the 12×12
lumping), duct piece diameter (per-piece flex), and accessory records
(dehumidifiers).

## Why this works

The `.rup` is a binary snapshot. When exactly ONE property changes
between two saves, the byte difference isolates that property's
encoding. Our differ (`scripts/corpus-analysis/rup_diff.py`) reports
the changed blocks with typed value interpretations — validated on the
79th Ct built/un-built pair (surfaces duct-schedule codes legibly).

## The one rule

**One property change per save.** Two changes in one save = ambiguous
diff = wasted capture.

## Procedure (per property)

1. Open the project in Wrightsoft.
2. **File → Save As** → `<project>-BASE.rup`
3. Change **one** value in the property sheet (one column, one object).
4. **File → Save As** → `<project>-<sheet>-<column>-<newvalue>.rup`
   e.g. `Jappeloup-register-grillesize-10x8.rup`
5. Repeat from step 3 for the next property (each new save becomes the
   next baseline — note the order, or re-save a fresh BASE each time).
6. Zip the batch + a one-line-per-file list of what was changed.

## Priority captures (first session, ~30-60 min)

Ranked by which decode wall they attack:

> **Day-31 update:** the grille-size encoding was decoded from
> accumulated data (see `docs/rup-dreginfo-decode.md`) — DREGINFO
> stores W×H f64s plus an auto/user flag. Captures #1–#2 are now
> confirmation-only; if session time is short, start at #3.

| # | Change | Attacks |
|---|--------|---------|
| 1 | One register's **grille size** property (e.g. blank/default → 10x8) | 12×12 lumping (confirmation-only) |
| 2 | Same register's grille size → a second value (10x8 → 12x6) | confirms encoding (confirmation-only) |
| 3 | One duct run's **diameter/size** property | per-piece flex sizing |
| 4 | One duct run's **material/family** (flex ↔ metal) | flex piece detection |
| 5 | Add a **dehumidifier** via whatever WS flow creates a real record (not a text label) | accessory extraction |
| 6 | One register's **mount type** (ceiling ↔ sidewall) | boot/diffuser split |
| 7 | Rebuild BOM (Reports → Bill of Materials) + save, after 1-6 | how properties land in RPITEM |

After each batch: rebuild the BOM in WS and save one final
`<project>-REBUILT.rup` — that shows how the property flows into the
priced BOM records.

## Scope guardrail

We are NOT mirroring all of Wrightsoft (the dropped autonomous-
assembler framing). Capture only property sheets that affect BOM
output, ranked by the defect classes the review team actually hits.
Stopping rule per sheet: when a captured property changes neither the
saved BOM nor our residual list, stop capturing that sheet.

## Analysis side (Gerald/Claude)

    python3 scripts/corpus-analysis/rup_diff.py BASE.rup CHANGED.rup

Windows COM supplement: targeted recording sessions on Gerald's
laptop against the documented COM surface
(docs/wrightsoft-com-surface.md) — scoped sessions only, not ambient
observation.

## Product payoff (why designers should care)

Once fields are decoded, the app gains a **pre-flight check**: upload
a .rup and get "these N objects have unset properties that will
default in the BOM" — named objects, exact fields. Explicitness
becomes a checklist the tool enforces, not a memo.
