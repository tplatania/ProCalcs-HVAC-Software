# Spec — M-Sheet PDF Analysis (queued)

**Status:** scoped, not started. Needs a Richard conversation before
build. Requested by Dana (2026-09-17), who supplied a proof-of-concept:
a full BOM ChatGPT generated from the Rahim II M-sheet PDF alone.

## The opportunity (why this is more than additive)

The mechanical drawings ("M sheets") carry design detail Wrightsoft
does not — and the gaps line up exactly with bugs the review team keeps
hitting:

- **Equipment accessories.** The Rahim II M-5 equipment schedule lists
  the Carrier electric heater **KFFEH2601C10** — the exact heat strip
  our tool missed on that project (Dana feedback #3). The M-sheet has
  it; Wrightsoft's output didn't.
- **Linear diffusers with slot sizing.** The grille schedule specifies
  Titus FL-10 linear diffusers with slot counts and per-room lengths
  (5 ft / 4 ft / 3 ft / …). Wrightsoft carries none of this.
- **Exhaust fans, ERV models, kitchen hoods, make-up air** — scheduled
  on the M sheets, absent from the .rup.

So M-sheet analysis wouldn't just add data — it would **fix the
missing-equipment class of defect** the .rup pipeline structurally
can't solve, because the data isn't in the .rup.

Dana's ChatGPT run is the feasibility proof: from the PDF alone it
produced an equipment BOM (with the heat strip), a linear-diffuser
schedule, a duct-route takeoff, and a "Basis and open items" section
that flags every unresolved assumption — which is exactly the
confidence/materiality review pattern we already built.

## What the M sheets actually contain (Rahim II sample)

- **M-1** general notes (filter MERV, exhaust material, make-up air).
- **M-2 / M-3** floor plans + device tags (S01…S23 supply, R01…R07
  return, T01 transfer) + linear-device schedule.
- **M-4** installation details.
- **M-5** equipment schedules (AHU / CU / heater / mini-split models,
  CFM, capacity, electrical).

The **schedules are tabular** — structured rows, not freehand drawing.
That's the tractable target. Tracing duct runs off the *plan* is the
hard AI-vision problem and is out of scope for v1.

## Proposed phasing

**Phase 1 — Equipment-schedule extraction + reconcile (highest value,
lowest risk).**
Read the M-5 equipment schedule (tabular text) into structured rows
(tag, model, size, CFM, count). Cross-check against the .rup/xlsx BOM
and surface the delta as **review flags** (reusing the confidence
layer): "M-5 lists KFFEH2601C10 — not in the BOM. Add?" Never merge
silently; the designer confirms. This directly fixes the #3-class bug.

**Phase 2 — Air-device schedule → BOM lines.**
Linear diffusers (slot size, length, count), grilles, transfer grilles
from the grille schedule → BOM lines Wrightsoft can't produce. Flag
low-confidence rows (ambiguous tags) via the same review layer.

**Phase 3 — Accessories & systems.**
Exhaust fans, ERV/HRV models, kitchen hood/make-up air, filters. These
are scattered across notes + schedules; more extraction variance.

**Out of scope (v1):** duct-route takeoff from the drawing (the AI
computer-vision problem). The schedules give ~80% of the value without
it.

## Architecture fit

- Upload the M-sheet PDF alongside (or instead of) the .rup, on the
  existing generate flow.
- A `pdf_schedule_reader` service: extract text/tables (vector PDFs
  like Rahim II have selectable text; scanned sets need OCR), then
  LLM-assisted structuring because schedule layouts vary by
  engineer/firm. This is where the **model-switching cost layer**
  (already built) matters — schedule extraction is an LLM cost.
- Reconciliation output rides the **confidence & materiality review
  layer** — M-sheet-vs-BOM deltas become graded review items, not
  silent additions. Honesty stance preserved.

## Open questions for Richard (before build)

1. How consistent are the firms' M-sheet schedule formats? (Determines
   how robust vs. LLM-assisted the reader must be.)
2. Which M-sheet fields are highest value first — equipment accessories
   (heat strips/ERV), linear diffusers, or exhaust?
3. Are the M sheets always vector PDFs, or sometimes scanned (→ OCR)?
4. Should the M-sheet reconciliation be advisory (flag deltas) or
   authoritative (M-sheet wins) when it disagrees with the .rup?

## Risks

- Schedule-format variance across firms → generalization needs several
  real M-sheet samples, not just Rahim II.
- PDF quality (scanned) → OCR dependency.
- Per-PDF LLM cost → the cost-control layer should gate/measure it.

## Recommendation

Build **Phase 1** first — equipment-schedule extraction + reconcile —
after the Richard conversation. It fixes a real defect class (missing
accessories), is the lowest-risk slice, and composes with the
confidence-review layer already built. Diffuser/duct detail (the big
differentiator vs. Wrightsoft) follows once we have more M-sheet
samples to generalize the reader.
