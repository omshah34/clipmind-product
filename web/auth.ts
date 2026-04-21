/**
 * File: auth.ts
 * Location: web/ (project root)
 * Purpose: Single source of truth for NextAuth v5 exports.
 *          Import `auth`, `signIn`, `signOut`, `handlers` from here everywhere.
 *
 * Pattern:
 *   - auth.config.ts  → edge-safe config (no Prisma, used by middleware)
 *   - auth.ts         → full config with Prisma adapter (Node.js only)
 *   - app/api/auth/[...nextauth]/route.ts → re-exports handlers for the API route
 */

import NextAuth from "next-auth";
import type { Session } from "next-auth";
import { PrismaAdapter } from "@auth/prisma-adapter";
import { authConfig } from "@/auth.config";
import { prisma } from "@/lib/prisma";

const nextAuthResult = NextAuth({
  adapter: PrismaAdapter(prisma),
  ...authConfig,
});

const originalHandlers = nextAuthResult.handlers;
export const handlers = {
  GET: async (req: any) => {
    const url = new URL(req.url);
    if (url.pathname.includes("/api/auth/session")) {
      return new Response(JSON.stringify({
        user: {
          id: "00000000-0000-0000-0000-000000000000",
          name: "Local Dev User",
          email: "local@clipmind.com",
          role: "owner",
          workspaceId: "00000000-0000-0000-0000-000000000000",
        },
        expires: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
      }), {
        headers: { "Content-Type": "application/json" }
      });
    }
    return originalHandlers.GET(req);
  },
  POST: originalHandlers.POST,
};

export const { signIn, signOut } = nextAuthResult;

// Override auth for unlaunched development to bypass login
export const auth = async (...args: any[]): Promise<Session | null> => {
  const session = await (nextAuthResult.auth as any)(...args);
  if (session) return session as Session;

  return {
    user: {
      id: "00000000-0000-0000-0000-000000000000",
      name: "Local Dev User",
      email: "local@clipmind.com",
      role: "owner",
      workspaceId: "00000000-0000-0000-0000-000000000000",
    },
    expires: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString(),
  } as Session;
};
