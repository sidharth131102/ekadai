import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { apiRequest, clearToken, getToken, setToken } from "../api/client";
import type { LoginRequest, RegisterRequest, TokenResponse, UserOut } from "../api/types";

interface AuthContextValue {
  user: UserOut | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (payload: LoginRequest) => Promise<void>;
  register: (payload: RegisterRequest) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setIsLoading(false);
      return;
    }
    apiRequest<UserOut>("/users/me")
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setIsLoading(false));
  }, []);

  const applySession = useCallback((data: TokenResponse) => {
    setToken(data.access_token);
    setUser(data.user);
  }, []);

  const login = useCallback(
    async (payload: LoginRequest) => {
      const data = await apiRequest<TokenResponse>("/auth/login", {
        method: "POST",
        body: payload,
        skipAuth: true,
      });
      applySession(data);
    },
    [applySession],
  );

  const register = useCallback(
    async (payload: RegisterRequest) => {
      const data = await apiRequest<TokenResponse>("/auth/register", {
        method: "POST",
        body: payload,
        skipAuth: true,
      });
      applySession(data);
    },
    [applySession],
  );

  const logout = useCallback(() => {
    clearToken();
    setUser(null);
    apiRequest("/auth/logout", { method: "POST" }).catch(() => {
      /* stateless logout — nothing to reconcile on failure */
    });
  }, []);

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
