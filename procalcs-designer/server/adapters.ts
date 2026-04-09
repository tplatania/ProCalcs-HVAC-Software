// Structural translation between:
//   - Python/Flask ClientProfile  (nested, snake_case, source of truth in Firestore)
//   - SPA ClientProfile           (flat, camelCase, what the UI expects)
//
// Source of truth for the Python shape:
//   procalcs-bom/backend/models/client_profile.py
//
// Fields the SPA cares about that don't exist in Python get synthesized with
// defaults on flatten, and are dropped on unflatten. This is a known loss —
// documented in src/types/procalcs.ts. Acceptable for Richard/Tom user testing;
// can be addressed later by extending the Python model or restoring a
// persistence layer.

export interface PythonClientProfile {
  client_id?: string;
  client_name?: string;
  is_active?: boolean;
  brand_color?: string;
  logo_url?: string;
  supplier?: {
    supplier_name?: string;
    account_number?: string;
    contact_name?: string;
    contact_email?: string;
    mastic_cost_per_gallon?: number;
    tape_cost_per_roll?: number;
    strapping_cost_per_roll?: number;
    screws_cost_per_box?: number;
    brush_cost_each?: number;
    flex_duct_cost_per_foot?: number;
    rect_duct_cost_per_sqft?: number;
  };
  markup?: {
    equipment_pct?: number;
    materials_pct?: number;
    consumables_pct?: number;
    labor_pct?: number;
  };
  markup_tiers?: Array<{
    label?: string;
    min_amount?: number;
    max_amount?: number | null;
    markup_percent?: number;
  }>;
  brands?: Record<string, string>;
  part_name_overrides?: Array<{
    standard_name?: string;
    client_name?: string;
    client_sku?: string;
  }>;
  default_output_mode?: string;
  include_labor?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  created_by?: string;
  notes?: string;
}

export interface SpaClientProfile {
  id: string;
  name: string;
  isActive: boolean;
  supplierName: string;
  supplierContact?: string;
  supplierEmail?: string;
  brandColor?: string;
  logoUrl?: string;
  defaultMarkupPercent: number;
  markupTiers: Array<{
    label: string;
    minAmount: number;
    maxAmount?: number | null;
    markupPercent: number;
  }>;
  partOverrides: Array<{
    standardName: string;
    clientName: string;
    unitCost?: number | null;
    unit?: string;
  }>;
  notes?: string;
  updatedAt: string;
  createdAt?: string;
}

// Python → SPA
export function flattenProfile(py: PythonClientProfile): SpaClientProfile {
  return {
    id: py.client_id ?? "",
    name: py.client_name ?? "",
    isActive: py.is_active ?? true,
    supplierName: py.supplier?.supplier_name ?? "",
    supplierContact: py.supplier?.contact_name ?? "",
    supplierEmail: py.supplier?.contact_email ?? "",
    brandColor: py.brand_color || "#1e293b",
    logoUrl: py.logo_url ?? "",
    defaultMarkupPercent: py.markup?.equipment_pct ?? 0,
    markupTiers: (py.markup_tiers ?? []).map((t) => ({
      label: t.label ?? "",
      minAmount: t.min_amount ?? 0,
      maxAmount: t.max_amount ?? null,
      markupPercent: t.markup_percent ?? 0,
    })),
    partOverrides: (py.part_name_overrides ?? []).map((p) => ({
      standardName: p.standard_name ?? "",
      clientName: p.client_name ?? "",
      unitCost: null,
      unit: "EA",
    })),
    notes: py.notes ?? "",
    updatedAt: py.updated_at ?? new Date().toISOString(),
    createdAt: py.created_at ?? undefined,
  };
}

// SPA → Python
// Threads all SPA-side fields through to the Python model. Previously
// dropped fields (brandColor, logoUrl, supplierContact, supplierEmail,
// markupTiers) are now persisted thanks to the extended Python model in
// procalcs-bom/backend/models/client_profile.py. Fields the SPA doesn't
// touch are preserved from the `existing` record on update.
// client_id is either provided explicitly (update) or derived from name (create).
export function unflattenProfile(
  spa: Partial<SpaClientProfile>,
  existing?: PythonClientProfile
): PythonClientProfile {
  const clientId =
    spa.id ??
    existing?.client_id ??
    slugify(spa.name ?? "");
  return {
    client_id: clientId,
    client_name: spa.name ?? existing?.client_name ?? "",
    is_active: spa.isActive ?? existing?.is_active ?? true,
    brand_color: spa.brandColor ?? existing?.brand_color ?? "",
    logo_url: spa.logoUrl ?? existing?.logo_url ?? "",
    supplier: {
      ...(existing?.supplier ?? {}),
      supplier_name: spa.supplierName ?? existing?.supplier?.supplier_name ?? "",
      contact_name: spa.supplierContact ?? existing?.supplier?.contact_name ?? "",
      contact_email: spa.supplierEmail ?? existing?.supplier?.contact_email ?? "",
    },
    markup: {
      equipment_pct: spa.defaultMarkupPercent ?? existing?.markup?.equipment_pct ?? 0,
      materials_pct: existing?.markup?.materials_pct ?? 0,
      consumables_pct: existing?.markup?.consumables_pct ?? 0,
      labor_pct: existing?.markup?.labor_pct ?? 0,
    },
    markup_tiers: (spa.markupTiers ?? existing?.markup_tiers?.map((t) => ({
      label: t.label ?? "",
      minAmount: t.min_amount ?? 0,
      maxAmount: t.max_amount ?? null,
      markupPercent: t.markup_percent ?? 0,
    })) ?? []).map((t) => ({
      label: t.label ?? "",
      min_amount: t.minAmount ?? 0,
      max_amount: t.maxAmount ?? null,
      markup_percent: t.markupPercent ?? 0,
    })),
    brands: existing?.brands ?? {},
    part_name_overrides: (spa.partOverrides ?? []).map((p) => ({
      standard_name: p.standardName,
      client_name: p.clientName,
      client_sku: "",
    })),
    default_output_mode: existing?.default_output_mode ?? "full",
    include_labor: existing?.include_labor ?? false,
    created_at: existing?.created_at ?? null,
    updated_at: new Date().toISOString(),
    created_by: existing?.created_by ?? "designer-desktop",
    notes: spa.notes ?? existing?.notes ?? "",
  };
}

function slugify(name: string): string {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || `client-${Date.now()}`
  );
}

// Summary derived from the list — since Flask has no /dashboard/summary endpoint,
// the adapter computes it client-side from a GET /api/v1/client-profiles/ call.
export function summarizeProfiles(profiles: SpaClientProfile[]) {
  const suppliers = new Set(profiles.map((p) => p.supplierName).filter(Boolean));
  const totalPartOverrides = profiles.reduce(
    (acc, p) => acc + (p.partOverrides?.length ?? 0),
    0
  );
  return {
    totalProfiles: profiles.length,
    activeProfiles: profiles.filter((p) => p.isActive).length,
    inactiveProfiles: profiles.filter((p) => !p.isActive).length,
    totalPartOverrides,
    suppliersCount: suppliers.size,
    recentProfiles: [...profiles]
      .sort((a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""))
      .slice(0, 5),
  };
}
