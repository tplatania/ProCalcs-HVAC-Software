# Wrightsoft COM surface — documented contract

*Consolidated 2026-07-15 from the Windows/Ghidra sessions' discovery
runs (`com_discovery_*.json`, `com_pricing_*.json`, smoke-test reports
of 2026-07-07/08, machine BAMBINO311, RSU 25.0.05, 2,825 candidates
probed). Source artifacts live outside the repo under
`~/Procalcs/COM Smoke Test Set 5/` and `~/Procalcs/BOM Module/`.*

COM executes only on Windows with a licensed Wrightsoft install. This
doc is the **contract** any future Windows worker implements against —
so the surface never has to be re-discovered. Server-side we do NOT
call COM; the `.rup` structural parsers replicate the read paths.

## Verified working (smoke-tested)

| Interface / call | Result | Notes |
|---|---|---|
| `OpenDocument(path)` | OK | Entry point for a `.rup` |
| Doc values (`CustomerName`, `Date`, `Notes`) | OK | Project metadata |
| `validate_export` | OK | Emits `.xls` (38 KB observed) — the programmatic version of Richard's manual BOM export |
| `IBOMInterface.GetItemCount()` | OK* | 153 items/investment on 79th Ct |
| `IBOMInterface.GetBOM` item fields incl. `Extprice` | OK* | Fully priced duct-side BOM over COM |
| `IInvestment` enumeration (4 investments) | OK | |
| Building values + `eqp_zones` (5 zones) | OK | |

\* **Preconditions discovered the hard way:** `Setup → Options →
Enable automatic takeoffs` must be ON, and the proposal must be
**built and saved** before `GetItemCount`/`GetBOM` return anything.
Without it: 0 items on every investment (the entire v6-run false
negative).

## Known limitations

- **Duct-side only.** The COM BOM contains zero HVAC equipment (no
  condenser/furnace/coil/AH). Equipment pricing requires the local
  catalog (`.mdb`) regardless.
- `IInvestment.inv_totalcost` stays `"0"` even with priced items —
  sum `Extprice` yourself (79th Ct inv0 = $8,323.50).
- ~27% of duct lines returned zero price on the test file — catalog
  supplement still needed for gaps.

## Architecture conclusion (2026-07-08, still holds)

COM alone cannot produce a complete priced BOM: **COM + catalog read,
not COM-only.** And since our `.rup` parsers now decode priced lines,
equipment, registers, and duct geometry directly (no Windows, no
license), COM is relevant only for *write/build actions* (trigger
takeoff build, export) if we ever need them server-side — which would
mean a small licensed Windows VM wrapping these calls behind HTTP.
Not currently planned; the BOM strategy (see `bom-strategy.md`)
requires no live Wrightsoft.
