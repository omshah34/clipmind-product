/**
 * File: lib/auth-stub.ts
 * Purpose: Stub authentication for development/prototyping.
 *          Replace with NextAuth.js when moving to production.
 */

export interface User {
  id: string;
  email: string;
  name: string;
  workspaceId?: string;
  role: "user" | "admin" | "workspace_owner";
}

interface AuthSession {
  user: User | null;
  token: string | null;
}

// Mock user data for development
const STUB_USER: User = {
  id: "user-stub-001",
  email: "demo@clipmind.app",
  name: "Demo User",
  workspaceId: "ws-stub-001",
  role: "workspace_owner",
};

const STUB_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.stub.token";

/**
 * Get current session (stub implementation)
 * In production: Validate JWT token from cookies
 */
export function getStubSession(): AuthSession {
  // Simulate checking localStorage for session
  if (typeof window !== "undefined") {
    const stored = localStorage.getItem("auth-session");
    if (stored) {
      return JSON.parse(stored);
    }
  }
  
  return {
    user: null,
    token: null,
  };
}

/**
 * Create a stub session for development
 * In production: Exchange credentials for JWT token via OAuth provider
 */
export function createStubSession(user: Partial<User> = {}): AuthSession {
  const session: AuthSession = {
    user: { ...STUB_USER, ...user },
    token: STUB_TOKEN,
  };
  
  if (typeof window !== "undefined") {
    localStorage.setItem("auth-session", JSON.stringify(session));
  }
  
  return session;
}

/**
 * Clear authentication session
 */
export function clearSession(): void {
  if (typeof window !== "undefined") {
    localStorage.removeItem("auth-session");
  }
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  const session = getStubSession();
  return !!session.user && !!session.token;
}

/**
 * Get current user (null if not authenticated)
 */
export function getCurrentUser(): User | null {
  const session = getStubSession();
  return session.user;
}
