# Handoff Addendum #02 — Path A + B Both, Licensing Green Light
## From: macOS BOM Module session → To: Windows Ghidra / Cowork session
### 2026-07-08

Read `HANDOFF_WRIGHTSOFT_REVERSE_ENGINEERING.md` (2026-07-03) and `_ADDENDUM_01.md` (2026-07-07) first for context. This addendum picks up after your COM smoke test result (`COM_smoke_test_2026-07-07.md`) landed and Gerald digested it with me.

Your previous deliverable was excellent — well-structured, honest about the empty `IBOMInterface.GetBOM` finding, clean sample outputs. The `ValidateProject` path is already shipped in production on our side (`POST /api/v1/bom/from-wrightsoft-bundle` + `/diagnostics/wrightsoft-bom-v2` SPA page). Real live users can build BOMs today from the JSON you produced. Nice work.

---

## 1. TL;DR — what changed

**Gerald secured licensing permission to host `RPRUWSF.mdb`** on our infrastructure. That unblocks a fundamentally simpler v2 architecture we couldn't consider before.

**v2 direction is now Path A + Path B, in that order:**

- **Path A — hosted catalog, zero-touch web upload.** Ingest `RPRUWSF.mdb` into Cloud SQL, deepen our `.rup` parser structurally using your MFC CArchive findings, and produce a fully priced BOM from a `.rup` alone. Contractor drops one file on the web page. Zero install. Fastest path to Richard's "minimize effort" ask.

- **Path B — Windows agent, install-once workflow.** Small agent on the contractor's box drives Wrightsoft via COM (`ValidateProject` + `IBOMInterface.GetBOMItem`), reads their **local** `.mdb` for their own pricing overrides, uploads a bundle. Kept as a premium tier for shops with custom pricing that a hosted standard catalog can't match.

The two paths share ~60% of the code — that shared foundation is where you can help most now.

---

## 2. Three focused asks that unblock everything downstream

Ranked by impact. Do them in order; each one has a natural "produce this artifact, ping back" boundary.

### 2.1 — `RPRUWSF.mdb` schema dump + safe transfer of the file itself

Deliverable: `procalcs-hvac-upstream/procalcs-bom/docs/wrightsoft-catalog-schema.md` + the actual `.mdb` transferred to us via GCS.

**Schema doc structure (per table):**

```
### <table_name>
- Row count: <n>
- Description: <one line — what this table represents in Wrightsoft>
- Columns: <name> <type> [PK] [FK→othertable.col] [NOT NULL] [INDEX]
- Sample rows: 5–10 representative rows in ```sql-ish``` code block
- Relationship notes: which tables this joins to
```

**Priority tables (from your `BOM_v2_Implementation_Handoff.md` §1.5 catalog quick-reference):**

| Table       | Why we need it                                     |
|-------------|----------------------------------------------------|
| `ActItem`   | 38,757 parts master (`Category, PSrc, PN, LinkPSrc, LinkPN, Description, PkgCount`). Core lookup for every duct/fitting SKU. |
| `ActCateg`  | 436 pricing rules (`Discount, Margin, CostTax` per Category+PartSource). Drives all pricing math. |
| `DFUnit`    | 1,035 equipment catalog (`Manufacturer, Model, ClgCap, HtgCap`, dims, `SysType, UnitType`). We have partial DFUnit already from Wrightsoft's exported DFUnit.csv — this is the authoritative version. |
| Any table with >5 reads in your Process Monitor trace | Give us the full picture — some pricing math may pull from tables you didn't spot in Section 1 |

**Prefer `mdbtools` for the dump script**, per your prior handoff — cross-platform, scriptable, doesn't need Windows. Avoid the pure-Python `access-parser` (you flagged its overflow-page undercount).

**Transfer of the actual `.mdb` file:** we have licensing permission to host it. Two-step:

1. You upload the raw `.mdb` to a GCS bucket I'll create at `gs://procalcs-wrightsoft-catalog/incoming/<yourdate>/` (I'll grant you a write-scoped service account credential separately once you confirm you're ready).
2. On my side, I run an importer that reads the `.mdb` via mdbtools and populates our Cloud SQL Postgres using the same batch_id + is_current versioning pattern as `import_catalog.py`.

**Do NOT commit the `.mdb` to git.** 276 MB binary blob, licensed content, doesn't belong in a code repo. GCS is the transfer channel.

### 2.2 — COM smoke test #2: does `IBOMInterface.GetBOMItem` return pricing?

Deliverable: `COM_smoke_test_pricing_2026-07-<n>.md` + one sample JSON dump.

Your first smoke test proved `GetBOM` is empty on load-calc `.rup` files. The follow-up question we need answered before scoping Path B: **on a `.rup` file where the contractor has actually built a priced proposal in RightSuite, does `IBOMInterface` return priced items?**

Concrete test:

1. Open Wrightsoft on your box. Load `79th Ct Residence Load Calcs.rup`.
2. In the UI, actually build a proposal (File → Bill of Materials → build/save/whatever the RSU flow calls it). This should transition the project from "load calc only" to "priced proposal" state.
3. Save. Close.
4. Re-open the saved `.rup` and run the COM chain from your first smoke test:
   ```
   IRRXInterface.OpenDocument(rup)
     → IRRXDocument.GetInvestment(i)
     → IInvestment.GetBOM()
     → IBOMInterface.GetItemCount()
   ```
5. If `GetItemCount() > 0`, iterate `GetBOMItem(i)` and dump the full field shape.

Three questions to answer:

- Does `GetItemCount()` populate for a priced-proposal `.rup`? Yes / No.
- If yes, does each `GetBOMItem` return **priced** items (unit price, total price, supplier code)?
- What's the field shape of a single `GetBOMItem` return value? Verbatim, don't normalize.

**Why this matters:** if COM returns priced items on priced-proposal files, Path B doesn't need to touch the local `.mdb` at all — the agent just calls COM and forwards the result. That simplifies the agent dramatically. If COM doesn't return pricing, the agent needs to read the local `.mdb` alongside COM to reconstruct prices, which is 3× the work.

Estimated effort: ~1–2 hours on a licensed WS box, including the proposal-build step in the UI.

### 2.3 — Wrightsoft version detection heuristic

Deliverable: `procalcs-hvac-upstream/procalcs-bom/docs/wrightsoft-version-detection.md` — a short doc describing:

- **How to detect the Wrightsoft version that generated a given `.rup`.** Is there a version tag in the binary header? A schema version in the catalog? A registry key on Windows? Give us the most reliable signal.
- **How to detect the catalog version** — is `RPRUWSF.mdb` self-versioned (a schema version column somewhere), or do we need to hash it, or check the file's mtime?
- **The version we're targeting today.** Your smoke test ran on RSU.EXE 25.0.05 — is that the version our importer should pin against? Give us a "if version differs from X, log a warning and continue" boundary condition.

**Why this matters:** future Wrightsoft updates will silently ship catalog schema changes. Without version pinning, our importer will break in strange ways ~6 months from now when a customer upgrades. A simple runtime check that logs "this catalog is version Y, we tested against X, proceed with caution" is 5 lines of code but saves a real incident.

Estimated effort: 30–60 minutes of investigation.

---

## 3. What NOT to do

Same guardrails as prior addenda, plus one addition:

- **No implementation of Path A or Path B on your side.** The Access-DB importer, the deepened `.rup` parser, the SPA changes — all shipped by the macOS session. You produce the intelligence + artifacts; I consume them.
- **Do NOT ship a Windows agent scaffold yet.** Path B design should wait for the COM smoke test #2 result. Different answer, different agent architecture.
- **No refactor of `rup_parser.py`.** Empirical parser stays stable while we build the structural replacement. When Path A's deepened parser ships, we retire the empirical one in one clean PR.
- **No `.mdb` in git.** GCS transfer channel only. If for some reason GCS isn't reachable from your side, ping me and we'll set up an SFTP alternative.
- **No production customer data.** Test files are still 79th Ct + Ally. Anything with a real contractor's pricing should be redacted or sanitized before transfer.

---

## 4. Timeline expectation

No hard deadlines, but suggested priority queue:

1. **Schema dump + `.mdb` transfer** (§2.1) — highest impact. Blocks Path A entirely.
2. **COM smoke test #2** (§2.2) — determines Path B's shape. Don't scope the agent before this.
3. **Version-detection heuristic** (§2.3) — smallest artifact, easiest polish, but genuinely important for long-term stability.

Ping when §2.1 lands. That's the trigger for me to start writing the Access → Postgres importer + the structurally-deepened parser stubs.

---

## 5. What I'm doing on macOS while you work

- **v1 stays production-supported.** Bugs get fixed, small features ship.
- **v2 web-only path (bundle upload) stays production-supported.** The COM `ValidateProject` bundle path you shipped equipment for is live and users are hitting it.
- **Preparing the Access-DB importer skeleton.** `import_catalog.py` scaffolding to read from `.mdb` via mdbtools, batch_id versioning, new Cloud SQL tables for `wrightsoft_actitem`, `wrightsoft_actcateg`, `wrightsoft_dfunit`. All inert until your schema dump lands.
- **Preparing the REST layer stub.** New endpoints in `procalcs-catalog` — `/api/v1/catalog/actitem/<pn>`, `/api/v1/catalog/pricing-for-part`, `/api/v1/catalog/dfunit-full`. Contract-only, no implementation until we know your table shape.

---

## 6. GCS bucket + credential provisioning (once you're ready)

When you confirm you're ready to transfer the `.mdb`, I'll:

1. Create `gs://procalcs-wrightsoft-catalog/` on our GCP project with:
   - `incoming/<yourdate>/` — write-only for you, versioned (retain 5 versions in case a corrupt upload needs redo).
   - `current/` — post-ingest snapshot the importer reads.
   - `archive/` — historical versions once we rotate quarterly catalog refreshes.
2. Grant your account (email TBD from your side) a service account credential scoped to `storage.objectAdmin` on `incoming/` only. No permission to touch `current/` or `archive/` — that's my side's job.
3. Send you a signed URL if that's simpler than dealing with the service account credential.

Ping me with your GCP-facing email address + preferred transfer channel (service account key vs signed URL) and I'll spin the bucket up.

---

## 7. Cross-references

- **Original handoff:** `HANDOFF_WRIGHTSOFT_REVERSE_ENGINEERING.md` (2026-07-03).
- **Addendum #01:** `HANDOFF_WRIGHTSOFT_REVERSE_ENGINEERING_ADDENDUM_01.md` (2026-07-07) — set the collaboration model.
- **Your COM smoke test:** `COM Smoke Test Set 5/COM_smoke_test_2026-07-07.md` — the deliverable that unblocked what's now shipped in production.
- **Your prior handoff back to us:** `BOM_v2_Implementation_Handoff.md` (2026-07-07) — RE findings this addendum builds on.
- **Test files:** unchanged. `~/Procalcs/RUPs/79th Ct Residence Load Calcs.rup`, `~/Procalcs/RUPs/Ally Residence (Main House).rup`, `~/Procalcs/RUPs/BOM.xls`, `~/Procalcs/RUPs/BOM - Ally.xls`.

---

## 8. One-line summary of this addendum

> *"Licensing green light on hosting `RPRUWSF.mdb`. v2 is now Path A (hosted catalog, zero-touch web upload) + Path B (Windows agent for custom pricing). Three focused asks in priority order: (1) schema dump + `.mdb` transfer via GCS, (2) COM smoke test #2 for pricing on priced-proposal files, (3) version-detection heuristic. No implementation, no agent scaffold yet — produce artifacts, we consume."*
