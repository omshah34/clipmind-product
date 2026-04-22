// DEV ONLY - REVERT BEFORE DEPLOY
"use client";
import { createContext, useContext, ReactNode } from "react";

const AuthContext = createContext({
  user: { id: "00000000-0000-0000-0000-000000000000", email: "dev@clipmind.ai", name: "Dev User" },
  isLoading: false,
  isAuthenticated: true,
  role: "owner",
});

export function useAuth() {
  return useContext(AuthContext);
}

export function useHasRole(role: string) {
  return true;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  return (
    <AuthContext.Provider value={{
      user: { id: "00000000-0000-0000-0000-000000000000", email: "dev@clipmind.ai", name: "Dev User" },
      isLoading: false,
      isAuthenticated: true,
      role: "owner",
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function Protected({ children }: { children: ReactNode }) {
  return <>{children}</>;
}

export function RoleProtected({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
