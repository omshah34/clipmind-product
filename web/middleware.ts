/**
 * File: middleware.ts
 * Location: Root middleware.ts
 * Purpose: NextAuth v5 middleware for route protection and RBAC enforcement.
 *
 * NOTE: Middleware runs in the Edge Runtime — Prisma (Node.js native) cannot
 * be imported here. Workspace membership validation is handled inside each
 * API route / Server Component where Node.js is available.
 */

import { NextRequest, NextResponse } from "next/server";
import NextAuth from "next-auth";
import { authConfig } from "@/auth.config";

const { auth } = NextAuth(authConfig);

/**
 * RBAC role hierarchy: owner > editor > viewer
 */
const ROLE_HIERARCHY: Record<string, number> = {
  owner: 3,
  editor: 2,
  viewer: 1,
};

/**
 * Routes that require an authenticated session
 */
const PROTECTED_PREFIXES = [
  "/workspaces",
  "/dashboard",
  "/settings",
  "/api/workspaces",
  "/api/portals",
];

/**
 * Routes that are always publicly accessible (skip auth check)
 */
const PUBLIC_PREFIXES = [
  "/auth",
  "/api/auth",
  "/api/health",
  "/_next",
  "/favicon.ico",
];

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Allow public routes immediately
  if (PUBLIC_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  // Retrieve the session via NextAuth v5 `auth()`
  const session = await auth();

  // Check if this is a protected route
  const isProtected = PROTECTED_PREFIXES.some((p) => pathname.startsWith(p)) || 
                      pathname.startsWith("/jobs") || 
                      pathname.startsWith("/intelligence");

  if (isProtected && !session) {
    const url = new URL("/auth/signin", request.url);
    url.searchParams.set("callbackUrl", pathname);
    return NextResponse.redirect(url);
  }

  // Supply user headers for downstream services
  const requestHeaders = new Headers(request.headers);
  if (session?.user) {
    requestHeaders.set("x-user-id", session.user.id!);
    requestHeaders.set("x-user-role", (session.user as any).role ?? "viewer");
  } else {
    // Only use mock user as a fallback for guest views of public pages if absolutely necessary
    // but for production, we prefer no injection if no session.
    // requestHeaders.set("x-user-id", "guest");
  }

  // For workspace routes, pass workspace ID via request headers
  const workspaceMatch = pathname.match(/\/workspaces\/([^/]+)/);
  if (workspaceMatch) {
    const workspaceId = workspaceMatch[1];
    requestHeaders.set("x-workspace-id", workspaceId);
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

/**
 * Configuration for which routes middleware applies to
 */
export const config = {
  matcher: [
    // Protect pages
    "/workspaces/:path*",
    "/dashboard/:path*",
    "/settings/:path*",
    // Protect API routes
    "/api/workspaces/:path*",
    "/api/portals/:path*",
    // Catch-all except Next.js internals and static assets
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};

// ─── RBAC helpers (re-exported for use in API routes / Server Components) ────

/**
 * Check if userRole satisfies requiredRole in the hierarchy.
 * Usage: hasRole(req.headers.get("x-user-role"), "editor")
 */
export function hasRole(
  userRole: string | null | undefined,
  requiredRole: string
): boolean {
  const userLevel = ROLE_HIERARCHY[userRole ?? "viewer"] ?? 0;
  const requiredLevel = ROLE_HIERARCHY[requiredRole] ?? 0;
  return userLevel >= requiredLevel;
}

/**
 * Return a 403 JSON response if the request header role is insufficient,
 * or null if access is allowed.
 * Usage in a route handler: const deny = requireRole(request, "editor"); if (deny) return deny;
 */
export function requireRole(
  request: NextRequest,
  requiredRole: string
): NextResponse | null {
  const userRole = request.headers.get("x-user-role");
  if (!userRole || !hasRole(userRole, requiredRole)) {
    return NextResponse.json(
      { error: `Access denied: ${requiredRole} role required` },
      { status: 403 }
    );
  }
  return null;
}
