import type { ReactElement } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../lib/auth";

export function ProtectedRoute({ children }: { children: ReactElement }) {
  const { token, isLoading } = useAuth();

  if (isLoading) {
    return <div className="p-6 text-sm text-slate-600 dark:text-slate-300">Loading...</div>;
  }

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return children;
}
