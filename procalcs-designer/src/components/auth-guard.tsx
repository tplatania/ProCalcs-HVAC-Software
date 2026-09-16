// AuthGuard — blocks rendering of the app until /api/auth/me resolves.
//
//   Loading:        spinner.
//   Not logged in:  redirect the whole page to /api/auth/login, which
//                   302s to Google's consent screen.
//   Logged in:      render the app.
//
// Auth-disabled deploys (dev) return authEnabled: false from /api/auth/me
// with a synthetic dev user, which means AuthGuard is a pass-through
// locally without any extra gating.

import { useCurrentUser } from "@/lib/auth-hooks";
import { Spinner } from "@/components/ui/spinner";
import { LoginScreen } from "@/components/login-screen";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { data, isLoading, isError } = useCurrentUser();

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Spinner className="size-8 text-muted-foreground" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <div className="text-center">
          <p className="text-sm text-destructive">Failed to load your session.</p>
          <p className="text-xs text-muted-foreground mt-1">
            Try refreshing the page.
          </p>
        </div>
      </div>
    );
  }

  // Day-27 — render the login screen (password + optional Google)
  // instead of hard-redirecting to Google consent. Password-only
  // deploys (Richard's team) have no Google flow to redirect to.
  if (data === null) {
    return <LoginScreen />;
  }

  return <>{children}</>;
}
