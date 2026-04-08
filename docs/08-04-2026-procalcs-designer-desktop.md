08-04-2026 Updates

🔧 In Progress:
Preparing Designer Desktop staging build for initial user testing with Richard and Tom — walking through contractor profile creation, AI BOM generation, and PDF-to-CAD cleanup end-to-end.

✅ Done Today

Project: ProCalcs Designer Desktop (Mockups Monorepo)

1. Mockups Monorepo Wiring (`feat/mockups-backend-wiring`)

Problem: The `procalcs-bom` and `procalcs-pdf-cleaner` sister repos each shipped their own throwaway React frontend. Two separate UIs, two codebases, no shared design language — stakeholders saw three different "ProCalcs" apps depending on which feature they were touching.

Solution: Disregarded both Flask frontends and surfaced their features through the polished `bom-dashboard` shadcn/ui SPA. `api-server` became a thin Express adapter that validates with Zod, translates camelCase ↔ snake_case, and proxies to the Flask services. All new routes live under `artifacts/api-server/src/routes/{clientProfiles,bom,pdfCleanup}.ts`. OpenAPI is the source of truth — Orval regenerates the React Query hooks and Zod schemas on every spec change.

2. Drizzle Schema Rewrite (`feat/mockups-backend-wiring`)

Problem: The local `client_profiles` table used a flat schema (`name`, `supplierName`, `defaultMarkupPercent`) that didn't match the Python `ClientProfile` dataclass (nested `supplier`, `markup`, `brands`, `partNameOverrides`). Every request would need runtime translation and the wire formats would drift.

Solution: Rewrote `lib/db/src/schema/clientProfiles.ts` to mirror the Python model exactly — `clientId` string primary key, JSONB nested objects, `defaultOutputMode`, `includeLabor`. Added a new `pdf_cleanup_jobs` cache table. Firestore stays the source of truth for profiles; the local Postgres caches PDF cleanup results so the dashboard can refresh stats without re-uploading.

3. Python Backends Deployment (`procalcs-hvac-bom`, `procalcs-hvac-cleaner`)

Problem: Neither Flask service had a working Cloud Run deployment. `procalcs-bom` had a Dockerfile that would have crashed at startup (WORKDIR `/app` + `backend.app:create_app()` while `app.py` does `from config import ...` — Python can't resolve that). `procalcs-pdf-cleaner` had no Dockerfile at all and pinned `ezdxf==0.19.0` which doesn't exist on PyPI.

Solution: Fixed the `procalcs-bom` Dockerfile to run from inside `/app/backend` with a flat `app:create_app()`. Created a new Dockerfile for `procalcs-pdf-cleaner` and bumped `ezdxf` to `~=1.4`. Relaxed the `ODA_CONVERTER_PATH` check from a fatal config error to a warning so DXF-only staging works today while DWG roundtrip waits for Phase 2. Both deployed to Cloud Run `us-east1` as `procalcs-hvac-bom` and `procalcs-hvac-cleaner`.

4. API-Server Deployment (`procalcs-hvac-api`)

Problem: The api-server uses `pnpm` catalog protocol (`"drizzle-orm": "catalog:"`) which npm doesn't understand, so the naive "copy package.json + `npm install`" approach in the runtime stage blew up with `EUNSUPPORTEDPROTOCOL`. Plus the api-server needs Postgres + secrets + cross-service URLs wired up at deploy time.

Solution: Built a multi-stage Node 20 Dockerfile that runs `pnpm deploy --filter @workspace/api-server --prod --legacy` to materialize a clean `node_modules` with all catalog/workspace references resolved. Provisioned Cloud SQL Postgres 16 (`procalcs-hvac-pg`, db-f1-micro) with a unix-socket DSN mounted via `--add-cloudsql-instances`. Pushed `procalcs-hvac-anthropic-key`, `procalcs-hvac-flask-secret`, and `procalcs-hvac-database-url` to Secret Manager. Granted the default Compute SA `secretAccessor`, `cloudsql.client`, and `datastore.user` roles.

5. Designer Desktop UI Live (`feat/spa-bundled`)

Problem: The React/Vite SPA had no deployment target. Stakeholders could hit the JSON API with curl but there was no UI in staging. The Vite config also required a `BASE_PATH` env var that threw on missing, and unconditionally loaded `@replit/vite-plugin-runtime-error-modal` which crashes Cloud Build.

Solution: Bundled the SPA into the same `procalcs-hvac-api` container via a new Vite build stage in the Dockerfile — single Cloud Run service, single origin, zero CORS. `express.static` serves the hashed assets, and a negative-lookahead regex fallback (`^(?!\/api(?:\/|$)).*` — Express 5 no longer accepts `*` strings) returns `index.html` for every other route so wouter can do client-side routing. `customFetch` already defaulted to same-origin, so no `setBaseUrl` call was needed. Stripped all `@replit/*` plugins from `vite.config.ts` and regenerated the lockfile.

6. End-to-End Staging Live (`procalcs-hvac-api-00002-l57`)

Problem: Nothing tied the pieces together yet. Each service was a black box.

Solution: `https://procalcs-hvac-api-69864992834.us-east1.run.app/` now serves the full Designer Desktop. The dashboard loads, the sidebar renders, and profile CRUD flows to Firestore via `procalcs-hvac-bom` while DXF uploads stream through `procalcs-hvac-cleaner`. Smoke tested: `/api/healthz` 200, `/api/client-profiles` 200, `/api/dashboard/summary` 200, the 600 KB JS bundle and 113 KB CSS serve with correct MIME types, client-side routes fall back to `index.html`, and unmatched `/api/*` paths still return JSON 404 (not the SPA shell).

7. Comprehensive README + Deploy Docs (`mockups/README.md`)

Problem: No onboarding doc existed. A new dev or a returning Claude session would have to reverse-engineer the stack from the code.

Solution: New `mockups/README.md` covering prerequisites, first-time setup, per-package commands, secrets reference, Cloud Run URLs, per-service deploy commands, `drizzle-kit push` workflow against Cloud SQL (with temporary IP allowlisting + revoke), and a from-scratch provisioning script for the entire staging environment. Anyone can redeploy or spin up a clean staging from the README alone.

Deployed revision `procalcs-hvac-api-00002-l57` to Cloud Run, serving 100% of traffic.

Latest branches:
main

Project: Cloud Infrastructure

Provisioned Cloud SQL Postgres 16 instance `procalcs-hvac-pg` in `us-east1-b`. Pushed Drizzle schema via temporary IP allowlist. Granted `datastore.user` to the Compute SA so `procalcs-hvac-bom` can write to Firestore.

Research

Compared bundled-SPA vs standalone-static-container vs GCS+LB for serving the React dashboard. Picked bundled for staging (fewest moving parts, zero CORS, single URL). Documented the trade-offs in the README so the decision can be revisited when traffic grows.

📅 ETA / Next Steps:
- **Initial user testing with Richard and Tom** — walk through contractor profile creation, AI BOM generation, and PDF-to-CAD cleanup end-to-end on staging. Capture feedback on copy, layout, missing fields (2 hours)
- Seed staging Firestore with 1-2 sample contractor profiles so stakeholders don't hit an empty dashboard (30 minutes)
- Wire ODA File Converter into `procalcs-hvac-cleaner` so DWG input works (currently DXF-only) (3 hours)
- Point a custom staging domain at `procalcs-hvac-api` (`staging.designer.procalcs.com` or similar) (1 hour)
- Fix the Windows `pnpm-workspace.yaml` rollup-native overrides so `pnpm run build` is green locally for Windows devs (1 hour)
- Add a `favicon.svg` to `artifacts/bom-dashboard/public/` — currently 404s in the browser console (cosmetic, 10 minutes)

⚠️ Blockers: None

---

## ⚰️ Retired — 08-04-2026 (later same day)

The `mockups/` monorepo was retired from the `ProCalcs-HVAC-Software` parent repo. It had grown beyond its "bucket for UI mockups" scope into a fully wired Node/Express adapter + React/Vite dashboard, and we decided to keep the actual apps (`procalcs-bom`, `procalcs-pdf-cleaner`) standalone instead.

**What was removed:**
1. `mockups/` directory contents — 125 files deleted locally. The user has a local backup snapshot; no GitHub archive was needed.
2. `procalcs-hvac-api` Cloud Run service (us-east1) — torn down via `gcloud run services delete`.
3. `procalcs-hvac-pg` Cloud SQL Postgres instance — torn down via `gcloud sql instances delete` (30-day soft-delete window in case of regret).
4. `procalcs-hvac-database-url` + `procalcs-hvac-database-url-tcp` Secret Manager entries — torn down.

**What stayed live and healthy:**
- `procalcs-hvac-bom` Cloud Run service — still serving `GET /health` 200 from `https://procalcs-hvac-bom-69864992834.us-east1.run.app`
- `procalcs-hvac-cleaner` Cloud Run service — still serving `GET /health` 200 from `https://procalcs-hvac-cleaner-69864992834.us-east1.run.app`
- `procalcs-hvac-anthropic-key` secret (consumed by procalcs-hvac-bom)
- `procalcs-hvac-flask-secret` secret (consumed by procalcs-hvac-cleaner)

**Dependency audit before deletion:** exhaustive grep across the parent repo confirmed that `procalcs-bom`, `procalcs-pdf-cleaner`, `experiments/`, `shared/`, `phase1_validator/`, `changelog/`, `HANDOFF.md`, `README.md`, and `PROJECT_RULES.md` had **zero code references** to anything inside `mockups/`. The only non-code hits were this doc (narrative history) and the `.gitignore` rule keeping git quiet about the nested repo. Nothing broke.

**Next steps (superseding the list above):**
- Initial user testing on the Flask frontends directly at `procalcs-hvac-bom` / `procalcs-hvac-cleaner` URLs, rather than via the (now retired) Designer Desktop shell
- `.rup` parsing experiments on the new `experiments/rup-parsing` branch — Wrightsoft Right-Suite Universal load data extraction

---

## 🔄 Recovered — 08-04-2026 (Session 3)

The earlier retirement killed the Designer Desktop staging by accident. The prior session had built the `procalcs-hvac-api` Cloud Run image from *inside* `mockups/`, which was supposed to be UI-component-reference-only. Deleting the directory took the demo surface with it.

Recovered as a standalone app inside the parent repo: **`procalcs-designer/`** (parallel to `procalcs-bom/` and `procalcs-pdf-cleaner/`).

**Architecture** — decoupled from `mockups/` entirely:
- React 19 + Vite 7 + wouter + TanStack Query SPA, copy-assembled from the pristine mockups snapshot at `C:\Users\ermil\projects\mockups\` (HEAD `cdb8509`) — pages, components (55 shadcn/ui), hooks, and styles copied verbatim once; no build-time dependency on `mockups/`.
- Thin Express 5 adapter (`server/`) that flattens/unflattens the nested Python `ClientProfile` schema to the flat camelCase shape the SPA expects, and computes a dashboard summary on the fly (there is no `/dashboard/summary` endpoint on Flask — the prior session persisted it in Cloud SQL, which we dropped).
- Multi-stage `Dockerfile`: Node 20 builder → Vite SPA build + esbuild server bundle → Alpine runtime serving both from a single process on `:8080`.
- **No Cloud SQL, no Drizzle, no Secret Manager entries, no pnpm workspace/catalog protocols**. Straight `npm install`. Windows-friendly.
- Hardcoded upstream URLs in `server/config.ts` default to the two surviving Cloud Run services; env vars override for local dev.

**Decoupling verified:** ran `mv C:\Users\ermil\projects\mockups C:\Users\ermil\projects\mockups.hidden && rm -rf dist dist-server && npm run build` — build succeeded with identical 599 KB JS output. `mockups/` can now be deleted safely at any time without breaking the parent repo.

**Deployed:** `gcloud run deploy procalcs-hvac-api --source . --region us-east1 --project psychic-medley-469413-r3 --allow-unauthenticated --port 8080`. Cloud Run reused the original project-number hash on re-create — the URL is bit-for-bit the same as the deleted one: `https://procalcs-hvac-api-69864992834.us-east1.run.app`.

**Smoke tests (all 200 / expected shape):**
- `GET /` — SPA shell
- `GET /api/healthz` — returns upstream URLs + `status: healthy`
- `GET /api/client-profiles` — proxies to Flask `/api/v1/profiles/`, unwraps envelope, flattens; returns `[]` currently (empty Firestore)
- `GET /api/dashboard/summary` — computed client-side, returns `{totalProfiles: 0, ...}`
- `GET /profiles` — SPA client-side fallback to `index.html` via Express 5 regex route (`^(?!\/api(?:\/|$)).*$`)
- `GET /api/nonsense` — returns `{"error":"API route not found"}`, does NOT fall through to SPA
- Survivor checks: `procalcs-hvac-bom` and `procalcs-hvac-cleaner` `/health` both still 200

**Known limitations (documented in `src/types/procalcs.ts`):** the SPA's `brandColor`, `logoUrl`, `supplierContact`, `supplierEmail`, and `markupTiers` fields don't exist on the Python side and are dropped on save. `defaultMarkupPercent` maps only to `markup.equipment_pct`. Acceptable for the Richard/Tom demo; revisit later by extending the Python `ClientProfile` or adding a persistence layer.


