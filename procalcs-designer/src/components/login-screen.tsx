// Login screen — Day-27. Rendered by AuthGuard when /api/auth/me says
// the visitor is unauthenticated. Two methods, both server-decided via
// /api/auth/methods:
//   - email + password (seeded accounts — Richard's team onboarding)
//   - Google sign-in (procalcs.net staff), shown only when configured.
//
// Replaces the old behavior of hard-redirecting every 401 straight to
// Google consent, which made password-only deploys unreachable.

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Loader2, LogIn } from "lucide-react";
import { getCurrentUserQueryKey } from "@/lib/auth-hooks";

export function LoginScreen() {
  const qc = useQueryClient();
  const [methods, setMethods] = useState<{ password: boolean; google: boolean } | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/auth/methods", { credentials: "same-origin" })
      .then((r) => (r.ok ? r.json() : null))
      .then((m) => setMethods(m ?? { password: true, google: false }))
      .catch(() => setMethods({ password: true, google: false }));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.error ?? `Sign-in failed (${res.status})`);
      }
      // Cookie is set — refetch identity and let AuthGuard render the app.
      await qc.invalidateQueries({ queryKey: getCurrentUserQueryKey() });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const googleHref = `/api/auth/login?return_to=${encodeURIComponent(
    window.location.pathname + window.location.search)}`;

  return (
    <div className="flex h-screen w-full items-center justify-center bg-muted/20 px-4">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-lg">ProCalcs Designer Desktop</CardTitle>
          <CardDescription>Sign in to continue.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {(methods?.password ?? true) && (
            <form onSubmit={submit} className="space-y-3" data-testid="password-login">
              <Input
                type="email"
                autoComplete="username"
                placeholder="Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <Input
                type="password"
                autoComplete="current-password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
              {error && <p className="text-xs text-destructive">{error}</p>}
              <Button type="submit" className="w-full gap-2" disabled={busy}>
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
                Sign in
              </Button>
            </form>
          )}
          {methods?.google && (
            <Button variant="outline" className="w-full" asChild>
              <a href={googleHref}>Sign in with Google (ProCalcs staff)</a>
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
