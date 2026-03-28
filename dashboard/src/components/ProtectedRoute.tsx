import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useStore } from "../lib/store";
import { getMe } from "../lib/api";

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, setUser, logout } = useStore();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    if (!user) {
      setChecking(false);
      return;
    }
    // Validate token on mount
    getMe()
      .then(() => setChecking(false))
      .catch(() => {
        logout();
        setChecking(false);
      });
  }, [user, logout]);

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
