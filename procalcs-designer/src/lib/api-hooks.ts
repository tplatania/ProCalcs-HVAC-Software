// Replacement for the old `@workspace/api-client-react` package.
// Thin React Query hooks calling same-origin `/api/*` endpoints served by
// our own Express adapter in server/. Keeps the page components unchanged.

import {
  useQuery,
  useMutation,
  type UseQueryOptions,
} from "@tanstack/react-query";
import type { ClientProfile, DashboardSummary } from "@/types/procalcs";

// ─── BOM pipeline types ──────────────────────────────────────────────────
// Shape of the design_data returned by /api/bom/parse-rup (Flask envelope
// already unwrapped). Intentionally loose — the SPA only reads a handful
// of fields and doesn't care about the deeper internals.
export interface RupDesignData {
  project: {
    name?: string;
    address?: string;
    city?: string;
    state?: string;
    zip?: string;
    county?: string;
    contractor?: Record<string, string>;
    drafter?: Record<string, string>;
    date?: string;
  };
  building: { type?: string; duct_location?: string };
  equipment: Array<{
    name: string;
    type?: string;
    cfm?: number | null;
    tonnage?: number | null;
    model?: string | null;
  }>;
  duct_runs: any[];
  fittings: any[];
  registers: any[];
  rooms: Array<{ name: string; ahu?: string; cfm?: number | null }>;
  metadata: {
    source_file?: string;
    app?: string;
    version?: string;
    timestamp?: string;
    section_count?: number;
  };
  raw_rup_context?: string;
}

export interface BomLineItem {
  category: string;
  description: string;
  quantity: number;
  unit: string;
  unit_cost?: number;
  unit_price?: number;
  total_cost?: number;
  total_price?: number;
  markup_pct?: number;
  // Provenance fields added by the Python rules engine (see procalcs-bom
  // commit ae5bd2b "Materials rules engine"). Present on rule-emitted lines;
  // missing or "ai" on AI-estimated lines.
  sku?: string;
  supplier?: string;
  section?: string;
  phase?: string;
  source?: "rules" | "ai" | string;
}

export interface BomResponse {
  job_id: string;
  client_id: string;
  client_name: string;
  output_mode: string;
  generated_at: string;
  supplier: string;
  line_items: BomLineItem[];
  totals: { total_cost: number | null; total_price: number | null };
  item_count: number;
  // Per-source counts from the rules-engine merge in Python.
  // Optional because pre-rules-engine clients may not return them.
  rules_engine_item_count?: number;
  ai_item_count?: number;
}

// ─── Query keys ──────────────────────────────────────────────────────────

export const getListClientProfilesQueryKey = () => ["client-profiles"] as const;
export const getGetClientProfileQueryKey = (id: string) =>
  ["client-profiles", id] as const;
export const getGetDashboardSummaryQueryKey = () => ["dashboard", "summary"] as const;

// SKU catalog
export const getListSkuCatalogQueryKey = (
  filter?: { section?: string; supplier?: string; include_disabled?: boolean }
) => ["sku-catalog", filter ?? {}] as const;
export const getGetSkuQueryKey = (sku: string) => ["sku-catalog", sku] as const;
export const getSkuCatalogMetaQueryKey = () => ["sku-catalog", "_meta"] as const;

// ─── Fetch helpers ───────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      if (body?.error) message = body.error;
    } catch {
      /* ignore */
    }
    throw { error: message, status: res.status };
  }
  // 204 No Content
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ─── Dashboard ───────────────────────────────────────────────────────────

export function useGetDashboardSummary() {
  return useQuery({
    queryKey: getGetDashboardSummaryQueryKey(),
    queryFn: () => apiFetch<DashboardSummary>("/api/dashboard/summary"),
  });
}

// ─── Client Profiles (list / get / create / update / delete) ────────────

export function useListClientProfiles() {
  return useQuery({
    queryKey: getListClientProfilesQueryKey(),
    queryFn: () => apiFetch<ClientProfile[]>("/api/client-profiles"),
  });
}

export function useGetClientProfile(
  id: string,
  opts?: { query?: Partial<UseQueryOptions<ClientProfile>> }
) {
  return useQuery({
    queryKey: getGetClientProfileQueryKey(id),
    queryFn: () => apiFetch<ClientProfile>(`/api/client-profiles/${encodeURIComponent(id)}`),
    ...(opts?.query ?? {}),
  });
}

export function useCreateClientProfile() {
  return useMutation({
    mutationFn: ({ data }: { data: Partial<ClientProfile> }) =>
      apiFetch<ClientProfile>("/api/client-profiles", {
        method: "POST",
        body: JSON.stringify(data),
      }),
  });
}

export function useUpdateClientProfile() {
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ClientProfile> }) =>
      apiFetch<ClientProfile>(`/api/client-profiles/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
  });
}

export function useDeleteClientProfile() {
  return useMutation({
    mutationFn: ({ id }: { id: string }) =>
      apiFetch<void>(`/api/client-profiles/${encodeURIComponent(id)}`, {
        method: "DELETE",
      }),
  });
}

// ─── BOM pipeline hooks ──────────────────────────────────────────────────

// POST a .rup file to /api/bom/parse-rup as multipart/form-data.
// Returns the parsed design_data dict on success. The Flask backend wraps
// its response in {success, data, error}; we unwrap `data` here so the
// caller gets the RupDesignData directly.
export function useParseRup() {
  return useMutation<RupDesignData, { error: string; status?: number }, File>({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/bom/parse-rup", {
        method: "POST",
        body: formData,
        // Do NOT set Content-Type — the browser adds the correct
        // multipart boundary automatically.
      });

      let body: any = null;
      try {
        body = await res.json();
      } catch {
        /* fall through */
      }

      if (!res.ok || !body?.success) {
        throw {
          error: body?.error ?? `Parse failed (${res.status})`,
          status: res.status,
        };
      }
      return body.data as RupDesignData;
    },
  });
}

// POST an already-generated BOM dict to /api/bom/render-pdf and trigger
// a browser download of the returned PDF. No new AI call — this is pure
// server-side rendering via Jinja2 + WeasyPrint. Expected latency ~200ms.
export function useRenderBomPdf() {
  return useMutation<
    void,
    { error: string; status?: number },
    { bom: BomResponse }
  >({
    mutationFn: async ({ bom }) => {
      const res = await fetch("/api/bom/render-pdf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bom }),
      });

      if (!res.ok) {
        // Error responses come back as JSON, not PDF.
        let message = res.statusText;
        try {
          const body = await res.json();
          if (body?.error) message = body.error;
        } catch {
          /* ignore */
        }
        throw { error: message, status: res.status };
      }

      // Pull filename out of the Content-Disposition header, or fall
      // back to the job_id.
      const cd = res.headers.get("Content-Disposition") ?? "";
      const match = cd.match(/filename="([^"]+)"/);
      const filename = match?.[1] ?? `${bom.job_id || "bom"}.pdf`;

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
  });
}

// ─── Rules-engine preview ───────────────────────────────────────────────
//
// Diagnostic endpoint that runs ONLY the deterministic materials_rules
// engine — no Anthropic call, no profile, no markup, no totals other
// than rules-engine cost. Designed for designers + Richard's team to
// inspect what the catalog-driven baseline produces against any RUP.
// Backed by procalcs-bom commit ae5bd2b (POST /api/v1/bom/rules-preview).

export interface RulesPreviewScope {
  // Free-form scope flags from compute_scope() (e.g. has_ahu, has_furnace,
  // duct_lf_total, register_count, etc.). Forwarded as-is for visibility.
  [key: string]: unknown;
}

export interface RulesPreviewResponse {
  scope: RulesPreviewScope;
  line_items: BomLineItem[];
  item_count: number;
  totals: { total_cost: number | null };
}

export function useRulesPreview() {
  return useMutation<
    RulesPreviewResponse,
    { error: string; status?: number },
    {
      design_data: RupDesignData | Record<string, any>;
      output_mode?: "full" | "materials_only" | "labor_materials" | "client_proposal" | "cost_estimate";
    }
  >({
    mutationFn: async (payload) => {
      const res = await fetch("/api/bom/rules-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      let body: any = null;
      try {
        body = await res.json();
      } catch {
        /* fall through */
      }

      if (!res.ok || !body?.success) {
        throw {
          error: body?.error ?? `Rules preview failed (${res.status})`,
          status: res.status,
        };
      }
      return body.data as RulesPreviewResponse;
    },
  });
}

// POST structured design_data + client_id to /api/bom/generate.
// The backend calls Claude, applies pricing, and returns the formatted
// BOM. Expected latency is 10–20s on a warm container, longer on cold.
export function useGenerateBom() {
  return useMutation<
    BomResponse,
    { error: string; status?: number },
    {
      client_id: string;
      job_id: string;
      design_data: RupDesignData | Record<string, any>;
      output_mode?: "full" | "materials_only" | "labor_materials" | "client_proposal" | "cost_estimate";
    }
  >({
    mutationFn: async (payload) => {
      const res = await fetch("/api/bom/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      let body: any = null;
      try {
        body = await res.json();
      } catch {
        /* fall through */
      }

      if (!res.ok || !body?.success) {
        throw {
          error: body?.error ?? `Generate failed (${res.status})`,
          status: res.status,
        };
      }
      return body.data as BomResponse;
    },
  });
}

// ─── sessionStorage helpers for routing design_data across pages ────────
//
// wouter has no built-in route state, so we stash the parsed design_data
// (plus the source filename) in sessionStorage between BOM Engine and BOM
// Output. Survives a tab reload; cleared by the BOM Output "Back" button.

const PARSED_KEY = "procalcs:designer:parsedRup";

export interface StoredParseResult {
  designData: RupDesignData;
  sourceFile: string;
  parsedAt: string;
}

export function storeParsedRup(
  designData: RupDesignData,
  sourceFile: string
): void {
  try {
    const payload: StoredParseResult = {
      designData,
      sourceFile,
      parsedAt: new Date().toISOString(),
    };
    sessionStorage.setItem(PARSED_KEY, JSON.stringify(payload));
  } catch {
    /* quota / private mode — silently degrade */
  }
}

export function loadParsedRup(): StoredParseResult | null {
  try {
    const raw = sessionStorage.getItem(PARSED_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredParseResult;
  } catch {
    return null;
  }
}

export function clearParsedRup(): void {
  try {
    sessionStorage.removeItem(PARSED_KEY);
  } catch {
    /* ignore */
  }
}


// ─── SKU Catalog (list / get / create / update / disable / delete) ──────

export interface SKUItem {
  sku: string;
  supplier: string;
  section: string;
  phase: string | null;
  description: string;
  trigger: string;
  quantity: { mode: string; [k: string]: unknown };
  default_unit_price: number;
  notes: string;
  disabled: boolean;
  // Phase 3.5 additions (May 2026) — all optional. Existing SKUs return
  // empty array / null for these. See procalcs-bom services/sku_catalog.py
  // SKUItem dataclass for field semantics.
  wrightsoft_codes?: string[];
  capacity_btu?: number | null;
  capacity_min_btu?: number | null;
  capacity_max_btu?: number | null;
  manufacturer?: string | null;
  contractor_id?: string | null;
}

export interface SKUCatalogMeta {
  sections: string[];
  triggers: string[];
  quantity_modes: string[];
  phases: string[];
  suppliers_seen: string[];
}

interface FlaskEnvelope<T> {
  success: boolean;
  data: T | null;
  error: string | null;
  meta?: Record<string, unknown>;
}

async function apiFetchEnvelope<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (res.status === 204) return undefined as T;
  let body: FlaskEnvelope<T> | null = null;
  try {
    body = (await res.json()) as FlaskEnvelope<T>;
  } catch {
    /* ignore */
  }
  if (!res.ok || !body?.success) {
    throw { error: body?.error ?? res.statusText, status: res.status };
  }
  return body.data as T;
}

export function useListSkuCatalog(
  filter?: { section?: string; supplier?: string; include_disabled?: boolean }
) {
  return useQuery({
    queryKey: getListSkuCatalogQueryKey(filter),
    queryFn: () => {
      const qs = new URLSearchParams();
      if (filter?.section) qs.set("section", filter.section);
      if (filter?.supplier) qs.set("supplier", filter.supplier);
      if (filter?.include_disabled !== undefined) {
        qs.set("include_disabled", String(filter.include_disabled));
      }
      const url = qs.toString() ? `/api/sku-catalog?${qs.toString()}` : "/api/sku-catalog";
      return apiFetchEnvelope<SKUItem[]>(url);
    },
  });
}

export function useGetSku(sku: string, opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: getGetSkuQueryKey(sku),
    queryFn: () => apiFetchEnvelope<SKUItem>(`/api/sku-catalog/${encodeURIComponent(sku)}`),
    enabled: opts?.enabled !== false && !!sku,
  });
}

export function useGetSkuCatalogMeta() {
  return useQuery({
    queryKey: getSkuCatalogMetaQueryKey(),
    queryFn: () => apiFetchEnvelope<SKUCatalogMeta>("/api/sku-catalog/_meta"),
    staleTime: 5 * 60 * 1000, // 5 min — enums dont change often
  });
}

export function useCreateSku() {
  return useMutation({
    mutationFn: (data: Partial<SKUItem>) =>
      apiFetchEnvelope<SKUItem>("/api/sku-catalog", {
        method: "POST",
        body: JSON.stringify(data),
      }),
  });
}

export function useUpdateSku() {
  return useMutation({
    mutationFn: ({ sku, data }: { sku: string; data: Partial<SKUItem> }) =>
      apiFetchEnvelope<SKUItem>(`/api/sku-catalog/${encodeURIComponent(sku)}`, {
        method: "PUT",
        body: JSON.stringify(data),
      }),
  });
}

export function useDisableSku() {
  return useMutation({
    mutationFn: ({ sku, disabled }: { sku: string; disabled: boolean }) =>
      apiFetchEnvelope<SKUItem>(
        `/api/sku-catalog/${encodeURIComponent(sku)}/${disabled ? "disable" : "enable"}`,
        { method: "POST" }
      ),
  });
}

export function useDeleteSku() {
  return useMutation({
    mutationFn: ({ sku }: { sku: string }) =>
      apiFetch<void>(`/api/sku-catalog/${encodeURIComponent(sku)}`, {
        method: "DELETE",
      }),
  });
}


// ─── Billing / subscriptions ───────────────────────────────────────────
//
// Endpoints proxy to procalcs-bom /api/v1/billing/*, which were added
// in the Apr 30 2026 evening session — see _repo-docs/SAAS_BILLING_DESIGN.md.
// All four require an authenticated user (Express requireAuth → user
// identity forwarded as X-Procalcs-User-Email upstream). Webhook is
// not consumed by the SPA — only Stripe calls it.

export type SubscriptionTier = "internal" | "trial" | "starter" | "pro" | "enterprise";

export interface BillingTierConfig {
  label:          string;
  bom_limit:      number;          // -1 = unlimited
  price_monthly:  number | null;
  price_yearly:   number | null;
  features:       string[];
}

export interface BillingConfig {
  publishable_key: string;
  billing_enabled: boolean;
  trial_days:      number;
  tiers:           Record<SubscriptionTier, BillingTierConfig>;
}

export interface BillingMe {
  id:                     number;
  email:                  string;
  name:                   string | null;
  subscription_tier:      SubscriptionTier;
  tier_label:             string;
  subscription_status:    string | null;
  trial_ends_at:          string | null;   // ISO
  current_period_end:     string | null;   // ISO
  cancel_at_period_end:   boolean;
  bom_count_total:        number;
  bom_count_monthly:      number;
  bom_limit:              number;          // -1 = unlimited
  boms_remaining:         number;          // -1 = unlimited
  features:               string[];
  created_at:             string | null;
  last_login:             string | null;
}

export type BillingPlan =
  | "starter_monthly"
  | "starter_yearly"
  | "pro_monthly"
  | "pro_yearly";

export const getBillingConfigQueryKey = () => ["billing", "config"] as const;
export const getBillingMeQueryKey     = () => ["billing", "me"] as const;

export function useBillingConfig() {
  return useQuery({
    queryKey: getBillingConfigQueryKey(),
    queryFn: () => apiFetchEnvelope<BillingConfig>("/api/billing/config"),
    // Tier table is effectively static per deploy — cache aggressively
    // so the pricing page renders without a network round-trip on
    // navigation.
    staleTime: 60 * 60 * 1000, // 1h
  });
}

export function useBillingMe(opts?: { enabled?: boolean }) {
  return useQuery({
    queryKey: getBillingMeQueryKey(),
    queryFn: () => apiFetchEnvelope<BillingMe>("/api/billing/me"),
    enabled: opts?.enabled ?? true,
  });
}

// Open Stripe-hosted checkout. The mutation returns the Stripe URL;
// the caller is responsible for window.location.assign() to it (so
// the redirect happens from a real user gesture, not a hidden iframe).
export function useStartCheckout() {
  return useMutation<
    { session_id: string; url: string },
    { error: string; status?: number },
    { plan: BillingPlan; success_url?: string; cancel_url?: string }
  >({
    mutationFn: (payload) =>
      apiFetchEnvelope<{ session_id: string; url: string }>(
        "/api/billing/checkout",
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      ),
  });
}

// Open the Stripe customer portal so the user can change plan / update
// card / cancel. Like checkout, returns a URL we then assign to.
export function useOpenBillingPortal() {
  return useMutation<
    { url: string },
    { error: string; status?: number },
    { return_url?: string } | undefined
  >({
    mutationFn: (payload) =>
      apiFetchEnvelope<{ url: string }>("/api/billing/portal", {
        method: "POST",
        body: JSON.stringify(payload ?? {}),
      }),
  });
}

// Bulk-import endpoint added in procalcs-bom Phase 3.6 (May 2026).
// POST /api/v1/sku-catalog/bulk-import — proxied via Express. Accepts
// {items: [<sku payload>, ...]}; returns 200 with summary even when
// individual rows failed (per-row errors itemized in summary.errors).

export interface SkuBulkImportSummary {
  created: number;
  updated: number;
  skipped: number;
  errors:  { index: number; sku: string | null; error: string }[];
}

export function useBulkImportSku() {
  return useMutation<
    SkuBulkImportSummary,
    { error: string; status?: number },
    { items: Partial<SKUItem>[] }
  >({
    mutationFn: ({ items }) =>
      apiFetchEnvelope<SkuBulkImportSummary>("/api/sku-catalog/bulk-import", {
        method: "POST",
        body: JSON.stringify({ items }),
      }),
  });
}
