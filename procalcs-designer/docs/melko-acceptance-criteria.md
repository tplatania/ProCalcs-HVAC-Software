# Melko fresh-upload acceptance criteria (day-31 Rheia-gate fix)

Tim's Melko test exposed the day-28 gate false-negative (phantom Rheia
lines + phantom ERV on a small sheet-metal conventional home). The
broadened gate is live on staging. Existing runs 409/410 have the
phantoms **baked into stored data** — re-opening them proves nothing.
Acceptance requires ONE fresh upload.

## Procedure

Richard or Tim (their own accounts — not gerald@/dev@/admin*, which
are test-tagged and excluded from metrics): **Generate New BOM →
upload the Melko `.rup` fresh.** Not from Browse, not Regenerate.

## Pass criteria (all four)

1. **Zero Rheia lines** — no line items with Rheia part numbers
   (`10-…` generic IDs / RHEA source). Previously: 7 phantom lines.
2. **Zero phantom ERV** — no `B150E…` ERV line (it rode inside the
   Rheia block).
3. **Gate metric on record** — staging logs show
   `rup: N conventional duct-system SKUs in priced BOM — conventional
   project, suppressing Rheia takeoff` with **N ≥ 15** for this upload
   (calibration measured Melko at 27 from its stored-run listing; the
   fresh upload re-measures end-to-end). Gerald verifies the log line.
4. **Nothing else regresses** — the conventional content Tim already
   reconciled (grille counts per her Test-2 corrections, duct cuts,
   summaries) matches her doc; her prior patch corrections do NOT
   auto-apply to the fresh run (patches are run-scoped by design — the
   fresh run shows engine output only).

## Fail handling

Any criterion failing → screenshot + run ID to Gerald; the run stays
in place (do not delete) as the diagnostic record.

## Sign-off

Tim (tester) confirms 1, 2, 4 in the UI; Gerald confirms 3 from logs
and replies on the thread. Only after sign-off does the Melko item
close in the readiness tracker ("3 consecutive clean conventional
projects" counter).
