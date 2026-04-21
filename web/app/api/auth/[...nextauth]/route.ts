/**
 * File: route.ts
 * Location: app/api/auth/[...nextauth]/
 * Purpose: NextAuth.js v5 route handler — re-exports GET/POST handlers from root auth.ts
 */

import { handlers } from "@/auth";

export const { GET, POST } = handlers;
