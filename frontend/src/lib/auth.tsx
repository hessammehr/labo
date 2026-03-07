import { createContext, useContext, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";

export type User = {
  id: string;
  name: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
};

type AuthContextValue = {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const { data } = await api.get<User>("/auth/me");
      return data;
    },
    retry: false,
  });

  const login = async (email: string, password: string) => {
    await api.post("/auth/login", { email, password });
    // Cookie is set by the server; just refetch /me
    await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
  };

  const register = async (name: string, email: string, password: string) => {
    await api.post("/auth/register", { name, email, password });
    // Cookie is set by the server; just refetch /me
    await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // Ignore errors — we're logging out anyway
    }
    // Immediately clear the user so ProtectedRoute redirects to /login,
    // then wipe all other cached data.
    queryClient.setQueryData(["auth", "me"], null);
    queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "auth" });
  };

  return (
    <AuthContext.Provider
      value={{
        user: meQuery.data ?? null,
        isLoading: meQuery.isLoading,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }

  return ctx;
}
