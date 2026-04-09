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
}

// ─── Query keys ──────────────────────────────────────────────────────────

export const getListClientProfilesQueryKey = () => ["client-profiles"] as const;
export const getGetClientProfileQueryKey = (id: string) =>
  ["client-profiles", id] as const;
export const getGetDashboardSummaryQueryKey = () => ["dashboard", "summary"] as const;

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
