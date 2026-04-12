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

  if (isError || !user) {
    return <Navigate to="/login" replace />;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  return <>{children}</>;
}
