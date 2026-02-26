import { createContext, useContext, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { api, clearToken, getToken, setToken } from "./api";

export type User = {
  id: string;
  name: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
};

type AuthContextValue = {
  token: string | null;
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(getToken());
  const queryClient = useQueryClient();

  const meQuery = useQuery({
    queryKey: ["auth", "me", token],
    queryFn: async () => {
      try {
        const { data } = await api.get<User>("/auth/me");
        return data;
      } catch (error) {
        clearToken();
        setTokenState(null);
        throw error;
      }
    },
    enabled: Boolean(token),
    retry: false,
  });

  const login = async (email: string, password: string) => {
    const { data } = await api.post<{ access_token: string }>("/auth/login", {
      email,
      password,
    });
    setToken(data.access_token);
    setTokenState(data.access_token);
    await queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
  };

  const register = async (name: string, email: string, password: string) => {
    await api.post("/auth/register", { name, email, password });
    await login(email, password);
  };

  const logout = () => {
    clearToken();
    setTokenState(null);
    queryClient.removeQueries({ queryKey: ["auth"] });
  };

  return (
    <AuthContext.Provider
      value={{
        token,
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
