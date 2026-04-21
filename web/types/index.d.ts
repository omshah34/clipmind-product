/**
 * File: types/index.d.ts
 * Purpose: Extend NextAuth types with custom user fields
 */

import type { DefaultSession } from "next-auth";

/**
 * Extend the NextAuth User type with custom fields
 */
declare module "next-auth" {
  interface User {
    id: string;
    role?: string;
    workspaceId?: string;
  }

  interface Session {
    user: {
      id: string;
      role?: string;
      workspaceId?: string;
    } & DefaultSession["user"];
    token?: string;
  }
}

/**
 * Extend JWT token type with custom fields
 */
declare module "next-auth/jwt" {
  interface JWT {
    id?: string;
    role?: string;
    workspaceId?: string;
    refreshToken?: string;
  }
}
