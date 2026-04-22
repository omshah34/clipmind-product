// DEV ONLY - REVERT BEFORE DEPLOY
import { NextRequest, NextResponse } from "next/server";

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  
  const requestHeaders = new Headers(request.headers);
  // Always inject dummy headers for development
  requestHeaders.set("x-user-id", "00000000-0000-0000-0000-000000000000");
  requestHeaders.set("x-user-role", "owner");

  // Keep workspace header logic if helpful
  const workspaceMatch = pathname.match(/\/workspaces\/([^/]+)/);
  if (workspaceMatch) {
    const workspaceId = workspaceMatch[1];
    requestHeaders.set("x-workspace-id", workspaceId);
  }

  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    // Catch-all except Next.js internals and static assets
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
