import { useEffect } from "react";
import { Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useStore } from "../lib/store";
import { getMe } from "../lib/api";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, logout } = useStore();

  const { isLoading, isError } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: getMe,
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: !!user,
  });

  // If token validation fails, log out (must be in useEffect, not render body)
  useEffect(() => {
    if (isError && user) {
      logout();
    }
  }, [isError, user, logout]);

  // Order: redirect on auth failure → show spinner while re-validating → render.
  // Previously, a slow /me round-trip rendered children immediately, so the
  // first data fetch could fire with a stale-or-missing token before logout.
  if (isError || !user) {
    return <Navigate to="/login" replace />;
  }

  if (user && isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary-600 border-t-transparent" />
      </div>
    );
  }

  return <>{children}</>;
}
