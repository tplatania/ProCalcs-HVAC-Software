# Manual Test Document — BOM Service + Cross-Application Integration

**Scope:** verify the hardened `procalcs-bom` service (shared-secret auth, versioned health, global body limit, CORS parsing) and the cross-application integration into the Designer Dashboard QC Checklist module.

**Prereqs:**
- A `@procalcs.net` Google account with access to staging
- `curl` and a terminal
- Access to the staging shared secret (ask Gerald)

**URLs:**
- BOM staging: `https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app`
- Dashboard staging: `https://procalcs-dashboard-staging-69864992834.us-east1.run.app`
- Dashboard QC page: `https://procalcs-dashboard-staging-69864992834.us-east1.run.app/qc`

---

## Part 1 — BOM Service (procalcs-hvac-bom)

### 1.1 Health probe reachable (no auth required)

**Steps:**
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app/api/v1/health
```

**Expected:** `HTTP 200`

**Also try the unversioned path** (used by Cloud Run):
```bash
curl -s -o /dev/null -w "HTTP %{http_code}\n" \
  https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app/health
```
**Expected:** `HTTP 200`

---

### 1.2 Unauthenticated BOM call is blocked

**Steps:**
```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST \
  -H "Content-Type: application/json" \
  -d '{}' \
  https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app/api/v1/bom/generate
```

**Expected:**
```json
{"data":null,"error":"unauthorized","success":false}
HTTP 401
```

---

### 1.3 Authenticated call passes auth gate

**Steps:**
```bash
export BOM_TOKEN='<paste the staging shared secret>'

curl -s -w "\nHTTP %{http_code}\n" -X POST \
  -H "Content-Type: application/json" \
  -H "X-Procalcs-Service-Token: $BOM_TOKEN" \
  -H "X-Client-Id: manual-test" \
  -d '{"client_id":"test","job_id":"test","design_data":{"project_info":{},"building_type":"residential","equipment":[],"rooms":[]},"output_mode":"cost_estimate"}' \
  https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app/api/v1/bom/generate
```

**Expected:** `HTTP 400` with an error like `"design_data must contain at least one of: duct_runs, equipment, fittings, registers."` — this means auth passed and the app-level validator rejected the empty payload. **`HTTP 200` or `HTTP 400` is a pass; `HTTP 401` is a fail.**

---

### 1.4 Wrong token is rejected

**Steps:**
```bash
curl -s -w "\nHTTP %{http_code}\n" -X POST \
  -H "Content-Type: application/json" \
  -H "X-Procalcs-Service-Token: not-the-real-token" \
  -d '{}' \
  https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app/api/v1/bom/generate
```

**Expected:** `HTTP 401` with `"unauthorized"`.

---

### 1.5 Body size limit (optional)

**Steps:** Post a ~30 MB JSON payload and confirm `HTTP 413`. Quick way:
```bash
python3 -c "import json; print(json.dumps({'data': 'x' * (30_000_000)}))" > /tmp/big.json
curl -s -w "\nHTTP %{http_code}\n" -X POST \
  -H "Content-Type: application/json" \
  -H "X-Procalcs-Service-Token: $BOM_TOKEN" \
  --data-binary @/tmp/big.json \
  https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app/api/v1/bom/generate
```
**Expected:** `HTTP 413` (Request Entity Too Large).

---

### 1.6 Designer Desktop (production) still works

**Steps:**
1. Open the live Designer Desktop (ProCalcs HVAC BOM Engine page).
2. Upload any valid `.rup` file (e.g., `experiments/Enos Residence Load Calcs.rup`).
3. Wait for parse → preview → Generate BOM → Export PDF.

**Expected:** All four steps complete without errors. The Designer Desktop's BFF forwards the shared-secret header transparently — the user should not notice any change.

---

## Part 2 — Designer Dashboard QC Checklist Module

### 2.1 Login gate

**Steps:**
1. Visit `https://procalcs-dashboard-staging-69864992834.us-east1.run.app/qc`.
2. Expect to be redirected to Google sign-in.
3. Sign in with a **non-`@procalcs.net`** account (e.g., personal Gmail).

**Expected:** Access denied — redirected back to login with an error. `@procalcs.net` is the only accepted domain.

4. Repeat with a `@procalcs.net` account.

**Expected:** Redirected to `/qc` and the page loads.

---

### 2.2 QC page renders with BOM card

**Steps:** After successful login, scroll down the QC page.

**Expected:** You should see these panels in order:
1. Project selector
2. Review stage selector
3. **Review History**
4. **QC Self-Check** (purple gradient card — file upload + checklist)
5. **BOM Service Integration Check** ← new purple gradient card with "Run BOM Smoke Test" button
6. Auto QC
7. Full Checklist + Quick Reference

---

### 2.3 Run BOM Smoke Test — happy path

**Steps:**
1. On the "BOM Service Integration Check" card, click **Run BOM Smoke Test**.
2. Wait up to ~20 seconds.

**Expected:** Four status rows update as follows:

| Row | Expected state | Notes |
|---|---|---|
| Health ping | ✅ OK · <few hundred> ms | Just a GET to `/api/v1/health` |
| Parse RUP | ⏸ Skipped | Intentional — there's no sample `.rup` wired yet |
| Generate BOM | ✅ OK · ~10 000–20 000 ms | Calls Anthropic upstream, slow is normal |
| Render PDF | ✅ OK · <few hundred> ms · "<size> KB PDF" | Reuses the generated envelope |

"Last run: <timestamp>" should appear below the card.

---

### 2.4 BOM smoke test — failure mode (optional)

To confirm the failure path renders correctly, you would need to either (a) stop the staging BOM service, or (b) deploy with a wrong `BOM_SERVICE_SHARED_SECRET`. **This is typically done by Gerald; testers don't need to perform it.** If it is exercised, all rows except Parse RUP (skipped) should go red with an error message.

---

### 2.5 Browser DevTools — network verification

**Steps:**
1. Open Chrome DevTools → Network tab.
2. Click **Run BOM Smoke Test** again.

**Expected:** Three `fetch` calls visible:
- `GET /api/bom/health` → `200 OK`
- `POST /api/bom/generate` → `200 OK`
- `POST /api/bom/render-pdf` → `200 OK` with `Content-Type: application/pdf`

No CORS errors, no `401`, no mixed-content warnings.

---

### 2.6 Session expiry behaviour

**Steps:**
1. In DevTools → Application → Cookies, delete the session cookie for the Dashboard domain.
2. Click **Run BOM Smoke Test**.

**Expected:** All rows fail with an authentication error. The Dashboard's session gate is enforced before the BOM service is even reached.

---

### 2.7 QC Self-Check still works (regression)

**Steps:**
1. On the QC Self-Check card, pick a project or use Local upload.
2. Upload a `.rup` or `.pdf` file.
3. Check a few checklist categories and click **Run Self-Check**.

**Expected:** The existing Self-Check flow works exactly as before — the BOM card addition did not break it.

---

## Part 3 — Smoke Test Script (one-shot)

A quick all-in-one verification for BOM service only:

```bash
#!/usr/bin/env bash
set -e
BASE="https://procalcs-hvac-bom-staging-69864992834.us-east1.run.app"
TOKEN="${BOM_TOKEN:?set BOM_TOKEN env var}"

echo "1) /api/v1/health (unauthed, expect 200)"
curl -fsS "$BASE/api/v1/health" | python3 -m json.tool

echo "2) /api/v1/bom/generate (no token, expect 401)"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" -d '{}' \
  "$BASE/api/v1/bom/generate")
[[ "$CODE" == "401" ]] || { echo "FAIL: got $CODE, want 401"; exit 1; }

echo "3) /api/v1/bom/generate (valid token, empty design_data, expect 400)"
CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  -H "Content-Type: application/json" \
  -H "X-Procalcs-Service-Token: $TOKEN" \
  -d '{"client_id":"t","job_id":"t","design_data":{"equipment":[],"rooms":[]},"output_mode":"cost_estimate"}' \
  "$BASE/api/v1/bom/generate")
[[ "$CODE" == "400" || "$CODE" == "200" ]] || { echo "FAIL: got $CODE"; exit 1; }

echo "All BOM checks passed."
```

Save as `bom_smoke.sh`, `chmod +x`, then `BOM_TOKEN='<secret>' ./bom_smoke.sh`.

---

## Failure triage

| Symptom | Likely cause | Action |
|---|---|---|
| `401 unauthorized` from Dashboard BOM card | Dashboard staging env var missing / wrong | Check `gcloud run services describe procalcs-dashboard-staging --region us-east1` for `BOM_SERVICE_SHARED_SECRET` |
| `502 Bad Gateway` from Dashboard | BOM staging service down or wrong `BOM_BASE_URL` | `curl` BOM staging `/api/v1/health` directly |
| All Dashboard calls 401 | User session expired | Re-login at `/auth/login` |
| `Generate BOM` row takes >30 s then times out | Anthropic slow / rate limit | Retry; confirm `ANTHROPIC_API_KEY` is wired in BOM service secrets |
| `Render PDF` row fails with "Unexpected content-type" | BOM service returned JSON error instead of PDF — check the step-3 response shape | Inspect the response body in DevTools Network tab |

---

## Sign-off checklist

- [ ] Part 1 (1.1–1.4) — BOM service auth surface verified
- [ ] Part 1 (1.6) — Designer Desktop prod regression clear
- [ ] Part 2 (2.1–2.3) — QC page loads and smoke test all green
- [ ] Part 2 (2.5) — Network tab shows clean 200s, no CORS
- [ ] Part 2 (2.7) — Self-Check regression clear
- [ ] Part 3 — `bom_smoke.sh` exits 0

Tester: ______________  Date: ______________  Environment: staging
