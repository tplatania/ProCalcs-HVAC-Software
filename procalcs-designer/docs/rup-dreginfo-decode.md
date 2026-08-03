# DREGINFO decode — grille size + auto/user flag (day-31)

**Result of mining accumulated data (no Windows captures used).** The
register grille-size property is already encoded in every `.rup` we
hold, including whether the designer set it or left it at default.
This makes the pre-flight check implementable today for grille sizes.

## The record

`DREGINFO` blocks (one family of register-schedule records; a file has
more DREGINFO blocks than physical registers — supply + return +
schedule replicas). Fixed header, offsets relative to the parser's
block position (body start, same position `RupReader.find_all_tags`
returns):

| offset | type | meaning | evidence |
|--------|------|---------|----------|
| +0  | u32 | constant 5 (record version?) | 152/152 on Jappeloup |
| +4  | u32 | object id (monotonic-ish, clustered) | 358, 362, 374… |
| +8  | u32 | **size mode: 1 = auto/default, 2 = user-specified** | see below |
| +12 | f64 | **grille width (inches)** | histogram matches plan |
| +20 | f64 | **grille height (inches)** | histogram matches plan |
| +36 | f32 | design limit (400.0 — face velocity?) | near-constant |
| +40 | f32 | design limit (80.0) | near-constant |

## Evidence

**Jappeloup** (Richard's plan count is the ground truth): 152 blocks =
126 auto + 26 user-set. Auto blocks carry only the defaults
(12×12: 120, 24×24: 6). User-set blocks carry exactly the sizes
Richard counted on the plan: 14×14 ×4, 30×20 ×2, 16×16 ×1, 20×20 ×1,
plus hand-set 12×12s and 10×6 returns. The 42-unit FRGRMFT-1212 lump
is these auto records flowing into the built BOM as literal 12×12.

**Cross-validation** (offsets identical in all): SW55, Irvine, 79th Ct,
Clarke, Enos. In every file the auto population is exclusively default
sizes and the user-set population matches the priced FRGR spread
(Irvine near-exact: 8×4:6↔FRGR-0804:6, 10×10:6↔1010:6, 20×14:2↔2014:2).
Files the review team called clean are majority user-set; the lumping
files are majority auto.

**Corpus prevalence** (120-file random sample, seed 31): 62% of all
DREGINFO records auto-sized; 75/120 files majority-auto; **0/120 files
fully user-set**. Default-sizing is the norm, not a Jappeloup quirk.
(Corpus is Rheia-heavy — standard-project rate may differ, direction
won't.)

## What this unlocks

- **Pre-flight check (grille sizes): buildable now.** "N register
  records are auto-sized and will land in the BOM as 12×12" — per
  upload, before the designer builds. The true size is genuinely NOT
  in the file (auto means Wrightsoft never resolved it), so we flag,
  never guess — consistent with the expert-ratified policy.
- The existing grille-lump verify badge gains a second, independent
  signal (structural, not statistical).
- Windows captures #1–#2 in the protocol (grille size) are now
  **confirmation-only**, not discovery.

## What still needs Windows captures

- **Per-piece flex diameter**: probed DUCTRUN/BALDUCT/DUCT
  exhaustively (fixed-offset + floating f64/f32/u32 scans). DUCTRUN
  f32@+16 is a constant 6.0 (default), u32@+8 a supply/return flag;
  BALDUCT is `id | room-name | CFM`. Piece diameter is computed at
  build time, not stored per run → capture #3 still required.
- Duct material/family per piece (capture #4), dehumidifier real
  record (#5), mount type (#6) — untested here, captures stand.

Repro scripts: histogram DREGINFO (+8, +12, +20) with
`utils/rup_reader.RupReader.find_all_tags("DREGINFO")`.
