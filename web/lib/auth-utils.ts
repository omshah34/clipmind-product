/**
 * File: auth-utils.ts
 * Purpose: Authentication helper functions
 */

import { auth, signIn, signOut } from "@/auth";
import type { Session, User } from "next-auth";
import type { JWT } from "next-auth/jwt";

/**
 * Get current session on server
 * Use in Server Components, Route Handlers, Server Actions
 */
export async function getCurrentSession(): Promise<Session | null> {
  const session = await auth();
  return session;
}

/**
 * Get current user on server
 */
export async function getCurrentUser(): Promise<User | null> {
  const session = await getCurrentSession();
  return session?.user || null;
}

/**
 * Sign in with OAuth provider
 */
export async function loginWithProvider(provider: "github" | "google") {
  await signIn(provider, { redirectTo: "/workspaces" });
}

/**
 * Sign out and redirect
 */
export async function logout() {
  await signOut({ redirectTo: "/auth/signin" });
}

/**
 * Check if user has specific role in a workspace
 */
export async function checkWorkspaceRole(
  workspaceId: string,
  requiredRole: "owner" | "editor" | "viewer"
): Promise<boolean> {
  const user = await getCurrentUser();
  if (!user?.id) return false;

  try {
    const { prisma } = await import("@/lib/prisma");

    const ROLE_HIERARCHY: Record<string, number> = {
      owner: 3,
      editor: 2,
      viewer: 1,
    };

    const membership = await prisma.workspaceMember.findUnique({
      where: {
        userId_workspaceId: {
          userId: user.id,
          workspaceId,
        },
      },
      select: {
        role: true,
      },
    });

    if (!membership) return false;

    const userLevel = ROLE_HIERARCHY[membership.role] || 0;
    const requiredLevel = ROLE_HIERARCHY[requiredRole] || 0;

    return userLevel >= requiredLevel;
  } catch (error) {
    console.error("Error checking workspace role:", error);
    return false;
  }
}

/**
 * Get user's workspaces with their role
 */
export async function getUserWorkspaces() {
  const user = await getCurrentUser();
  if (!user?.id) return [];

  try {
    const { prisma } = await import("@/lib/prisma");

    const memberships = await prisma.workspaceMember.findMany({
      where: {
        userId: user.id,
      },
      include: {
        workspace: {
          select: {
            id: true,
            name: true,
            description: true,
          },
        },
      },
      orderBy: {
        workspace: {
          name: "asc",
        },
      },
    });

    return memberships.map((m) => ({
      workspace: m.workspace,
      role: m.role,
    }));
  } catch (error) {
    console.error("Error fetching user workspaces:", error);
    return [];
  }
}

/**
 * Create a new workspace for user
 */
export async function createWorkspace(
  name: string,
  description?: string
): Promise<{ id: string; name: string } | null> {
  const user = await getCurrentUser();
  if (!user?.id) return null;

  try {
    const { prisma } = await import("@/lib/prisma");

    const workspace = await prisma.workspace.create({
      data: {
        name,
        description,
        members: {
          create: {
            userId: user.id,
            role: "owner",
          },
        },
      },
      select: {
        id: true,
        name: true,
      },
    });

    return workspace;
  } catch (error) {
    console.error("Error creating workspace:", error);
    return null;
  }
}

/**
 * Invite user to workspace
 */
export async function inviteUserToWorkspace(
  workspaceId: string,
  email: string,
  role: "editor" | "viewer" = "editor"
): Promise<{ success: boolean; message: string }> {
  const user = await getCurrentUser();
  if (!user?.id) {
    return { success: false, message: "Not authenticated" };
  }

  try {
    const { prisma } = await import("@/lib/prisma");

    // Check if requester is owner
    const membership = await prisma.workspaceMember.findUnique({
      where: {
        userId_workspaceId: {
          userId: user.id,
          workspaceId,
        },
      },
      select: {
        role: true,
      },
    });

    if (membership?.role !== "owner") {
      return { success: false, message: "Only owners can invite members" };
    }

    // Find user by email
    const targetUser = await prisma.user.findUnique({
      where: { email },
      select: { id: true },
    });

    if (!targetUser) {
      return {
        success: false,
        message: "User not found. They must sign up first.",
      };
    }

    // Check if already member
    const existing = await prisma.workspaceMember.findUnique({
      where: {
        userId_workspaceId: {
          userId: targetUser.id,
          workspaceId,
        },
      },
    });

    if (existing) {
      return { success: false, message: "User is already a workspace member" };
    }

    // Add member
    await prisma.workspaceMember.create({
      data: {
        userId: targetUser.id,
        workspaceId,
        role,
      },
    });

    return {
      success: true,
      message: `${email} has been invited as ${role}`,
    };
  } catch (error) {
    console.error("Error inviting user:", error);
    return { success: false, message: "Failed to invite user" };
  }
}

/**
 * Generate portal token for client access
 */
export async function generatePortalToken(
  workspaceId: string,
  clientId?: string,
  expiresIn: number = 24 * 60 * 60 * 1000 // 24 hours default
): Promise<{ token: string } | null> {
  const user = await getCurrentUser();
  if (!user?.id) return null;

  try {
    const { prisma } = await import("@/lib/prisma");

    // Verify user is owner of workspace
    const membership = await prisma.workspaceMember.findUnique({
      where: {
        userId_workspaceId: {
          userId: user.id,
          workspaceId,
        },
      },
      select: {
        role: true,
      },
    });

    if (membership?.role !== "owner") {
      return null;
    }

    // Generate random token
    const token = generateRandomToken(32);
    const expiresAt = new Date(Date.now() + expiresIn);

    await prisma.portalToken.create({
      data: {
        token,
        workspaceId,
        clientId,
        createdByUserId: user.id,
        expiresAt,
      },
    });

    return { token };
  } catch (error) {
    console.error("Error generating portal token:", error);
    return null;
  }
}

/**
 * Verify portal token
 */
export async function verifyPortalToken(token: string) {
  try {
    const { prisma } = await import("@/lib/prisma");

    const portalToken = await prisma.portalToken.findUnique({
      where: { token },
      select: {
        id: true,
        workspaceId: true,
        expiresAt: true,
        isActive: true,
      },
    });

    if (!portalToken || !portalToken.isActive) {
      return null;
    }

    if (portalToken.expiresAt < new Date()) {
      // Token expired
      await prisma.portalToken.update({
        where: { id: portalToken.id },
        data: { isActive: false },
      });
      return null;
    }

    return {
      workspaceId: portalToken.workspaceId,
      expiresAt: portalToken.expiresAt,
    };
  } catch (error) {
    console.error("Error verifying portal token:", error);
    return null;
  }
}

/**
 * Generate cryptographically secure random token
 */
function generateRandomToken(length: number): string {
  const charset =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  let token = "";

  if (typeof window === "undefined") {
    // Node.js environment
    const crypto = require("crypto");
    token = crypto.randomBytes(length).toString("hex").substring(0, length);
  } else {
    // Browser environment (fallback, not ideal)
    for (let i = 0; i < length; i++) {
      token += charset.charAt(Math.floor(Math.random() * charset.length));
    }
  }

  return token;
}
