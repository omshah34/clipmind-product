/**
 * File: auth-provider.tsx
 * Location: components/
 * Purpose: SessionProvider wrapper for NextAuth
 * Updated from auth-stub implementation to use real NextAuth
 */

"use client";

import { SessionProvider, useSession } from "next-auth/react";
import type { ReactNode } from "react";
import { createContext, useContext } from "react";
import type { Session } from "next-auth";

/**
 * Auth context for easier access to session data
 */
interface AuthContextType {
  user: Session["user"] | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  role?: string;
  token?: string;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: false,
  isAuthenticated: false,
});

/**
 * Hook to access authentication context
 * Usage: const { user, isAuthenticated } = useAuth();
 */
export function useAuth() {
  return useContext(AuthContext);
}

/**
 * Internal hook that uses NextAuth useSession
 */
function AuthContextProvider({ children }: { children: ReactNode }) {
  const { data: session, status } = useSession();

  const value: AuthContextType = {
    user: session?.user || null,
    isLoading: status === "loading",
    isAuthenticated: status === "authenticated",
    role: (session?.user as any)?.role,
    token: (session as any)?.token,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Provider component wrapping application
 * Usage in layout:
 * <AuthProvider>
 *   {children}
 * </AuthProvider>
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <AuthContextProvider>
        {children}
      </AuthContextProvider>
    </SessionProvider>
  );
}

/**
 * Hook to check if user has role
 * Usage: const isOwner = useHasRole("owner");
 */
export function useHasRole(requiredRole: "owner" | "editor" | "viewer") {
  const { role } = useAuth();

  const ROLE_HIERARCHY: Record<string, number> = {
    owner: 3,
    editor: 2,
    viewer: 1,
  };

  const userLevel = ROLE_HIERARCHY[role || "viewer"] || 0;
  const requiredLevel = ROLE_HIERARCHY[requiredRole] || 0;

  return userLevel >= requiredLevel;
}

/**
 * Protected component wrapper
 * Only renders children if user is authenticated
 */
export function Protected({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border border-gray-300 border-t-blue-500 mx-auto mb-2" />
          <p className="text-gray-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-center">
          <p className="text-gray-600 mb-4">Please sign in to access this content</p>
          <a
            href="/auth/signin"
            className="inline-block px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Sign In
          </a>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

/**
 * Role-protected component wrapper
 * Only renders children if user has required role
 */
export function RoleProtected({
  children,
  role,
  fallback,
}: {
  children: ReactNode;
  role: "owner" | "editor" | "viewer";
  fallback?: ReactNode;
}) {
  const hasRole = useHasRole(role);

  if (!hasRole) {
    return (
      fallback || (
        <div className="p-4 bg-red-50 border border-red-200 rounded text-red-700">
          Access denied: {role} role required
        </div>
      )
    );
  }

  return <>{children}</>;
}
