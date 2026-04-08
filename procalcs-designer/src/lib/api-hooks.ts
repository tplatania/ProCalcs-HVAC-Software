// Replacement for the old `@workspace/api-client-react` package.
// Thin React Query hooks calling same-origin `/api/*` endpoints served by
// our own Express adapter in server/. Keeps the page components unchanged.

import {
  useQuery,
  useMutation,
  type UseQueryOptions,
} from "@tanstack/react-query";
import type { ClientProfile, DashboardSummary } from "@/types/procalcs";

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
