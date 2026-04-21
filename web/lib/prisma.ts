/**
 * File: prisma.ts
 * Purpose: Singleton Prisma client instance for database access
 * Note: In development, Next.js hot-reloads can create multiple instances
 *       This pattern prevents database connection exhaustion
 */

import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as {
  prisma: PrismaClient | undefined;
};

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === "development" ? ["info"] : ["error"],
  });

if (process.env.NODE_ENV !== "production") {
  globalForPrisma.prisma = prisma;
}
