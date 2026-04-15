// Auth hooks for the SPA. Backed by /api/auth/me (identity) and
// /api/auth/logout (explicit sign-out). Login itself is a full-page
// redirect handled by the browser, not a fetch — see AuthGuard.

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

export interface CurrentUser {
  email:       string;
  name:        string;
  picture:     string;
  hd:          string;
  authEnabled: boolean;
}

const CURRENT_USER_QUERY_KEY = ["auth", "me"] as const;

export function getCurrentUserQueryKey() {
  return CURRENT_USER_QUERY_KEY;
}

// useCurrentUser — returns the signed-in user or null when unauthenticated.
// 401 from the server is treated as "not logged in" (null data) rather than
// an error, so the AuthGuard can render a clean redirect without flashing
// an error boundary.
export function useCurrentUser() {
  return useQuery<CurrentUser | null>({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: async () => {
      const res = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (res.status === 401) return null;
      if (!res.ok) {
        throw new Error(`auth/me failed: ${res.status}`);
      }
      return (await res.json()) as CurrentUser;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: false,
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!res.ok && res.status !== 204) {
        throw new Error(`logout failed: ${res.status}`);
      }
    },
    onSuccess: () => {
      // Invalidate everything — the user is gone, no stale data should
      // survive on the client.
      qc.clear();
      // Full page reload bounces back to Google consent if auth is on,
      // or just re-renders the app if it's off.
      window.location.href = "/";
    },
  });
}
