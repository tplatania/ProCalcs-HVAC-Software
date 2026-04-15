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

import { useEffect } from "react";
import { useCurrentUser } from "@/lib/auth-hooks";
import { Spinner } from "@/components/ui/spinner";

interface AuthGuardProps {
  children: React.ReactNode;
}

export function AuthGuard({ children }: AuthGuardProps) {
  const { data, isLoading, isError } = useCurrentUser();

  // Kick off the redirect in an effect so React doesn't complain about
  // side effects during render.
  useEffect(() => {
    if (!isLoading && data === null) {
      const returnTo = encodeURIComponent(
        window.location.pathname + window.location.search
      );
      window.location.href = `/api/auth/login?return_to=${returnTo}`;
    }
  }, [isLoading, data]);

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

  // Redirect in flight — render the spinner instead of the app to avoid
  // a flash of the unauthenticated state.
  if (data === null) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Spinner className="size-8 text-muted-foreground" />
      </div>
    );
  }

  return <>{children}</>;
}
