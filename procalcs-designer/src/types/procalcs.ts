// SPA-facing types for ProCalcs Designer.
//
// These are the *flattened* shapes the React components expect. The server
// adapter in server/adapters.ts translates between these and the nested
// Python ClientProfile schema (see procalcs-bom/backend/models/client_profile.py).
//
// Fields marked "adapter-synthesized" don't exist on the Python side and are
// generated/defaulted by server/adapters.ts. On round-trip they may be lost.
// This is a known tradeoff of the standalone recovery — the prior api-server
// persisted extras via a separate Drizzle/Postgres cache that we intentionally
// did not recover.

export interface ClientProfile {
  id: string;                    // maps to Python client_id
  name: string;                  // maps to Python client_name
  isActive: boolean;             // maps to Python is_active

  supplierName: string;          // maps to Python supplier.supplier_name
  supplierContact?: string;      // adapter-synthesized (not persisted)
  supplierEmail?: string;        // adapter-synthesized (not persisted)

  brandColor?: string;           // adapter-synthesized (not persisted)
  logoUrl?: string;              // adapter-synthesized (not persisted)

  defaultMarkupPercent: number;  // maps to Python markup.equipment_pct

  markupTiers: Array<{
    label: string;
    minAmount: number;
    maxAmount?: number | null;
    markupPercent: number;
  }>;                            // adapter-synthesized (not persisted)

  partOverrides: Array<{
    standardName: string;        // maps to Python part_name_overrides[].standard_name
    clientName: string;          // maps to Python part_name_overrides[].client_name
    unitCost?: number | null;    // adapter-synthesized (not persisted)
    unit: string;                // adapter-synthesized (not persisted), defaults to "EA"
  }>;

  notes?: string;                // maps to Python notes
  updatedAt: string;             // maps to Python updated_at (ISO string)
  createdAt?: string;            // maps to Python created_at
}

export interface DashboardSummary {
  totalProfiles: number;
  activeProfiles: number;
  inactiveProfiles: number;
  totalPartOverrides: number;
  suppliersCount: number;
  recentProfiles: ClientProfile[];
}

export interface ApiError {
  error: string;
}
