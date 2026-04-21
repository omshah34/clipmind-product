/**
 * File: auth.config.ts
 * Purpose: NextAuth.js configuration with OAuth providers and JWT strategy
 */

import type { NextAuthConfig } from "next-auth";
import GitHub from "next-auth/providers/github";
import Google from "next-auth/providers/google";

// OAuth configuration
const GITHUB_ID = process.env.GITHUB_ID || "";
const GITHUB_SECRET = process.env.GITHUB_SECRET || "";
const GOOGLE_ID = process.env.GOOGLE_ID || "";
const GOOGLE_SECRET = process.env.GOOGLE_SECRET || "";

export const authConfig: NextAuthConfig = {
  providers: [
    GitHub({
      clientId: GITHUB_ID,
      clientSecret: GITHUB_SECRET,
      allowDangerousEmailAccountLinking: true,
    }),
    Google({
      clientId: GOOGLE_ID,
      clientSecret: GOOGLE_SECRET,
      allowDangerousEmailAccountLinking: true,
    }),
  ],
  
  pages: {
    signIn: "/auth/signin",
    error: "/auth/error",
  },
  
  callbacks: {
    /**
     * Called whenever JWT is created or updated
     * Add custom claims (role, workspace, etc.)
     */
    async jwt({ token, user, account }) {
      if (user) {
        token.id = user.id;
        token.role = (user as any).role || "user";
        token.email = user.email;
        token.workspaceId = (user as any).workspaceId;
      }
      
      // Store refresh token if available (OAuth2)
      if (account?.refresh_token) {
        token.refreshToken = account.refresh_token;
      }
      
      return token;
    },
    
    /**
     * Called on each session check
     * Return session with JWT token and user info
     */
    async session({ session, token }) {
      if (session.user) {
        session.user.id = token.id as string;
        (session.user as any).role = token.role;
        (session.user as any).workspaceId = token.workspaceId;
      }
      
      // Add token to session for client-side use
      (session as any).token = token.sub || token.id;
      
      return session;
    },
    
    /**
     * Called when user is trying to sign in
     * Can reject signin or modify user data
     */
    async signIn({ user, account, profile }) {
      // Allow signIn for all authenticated users
      // Later: Add email domain whitelist, etc.
      return true;
    },
    
    /**
     * Called when JWT callback is used on a page/route
     * Redirect to signin if session is invalid
     */
    async redirect({ url, baseUrl }) {
      // Allows relative URLs
      if (url.startsWith("/")) return `${baseUrl}${url}`;
      
      // Allows callback URLs on same origin
      if (new URL(url).origin === baseUrl) return url;
      
      return baseUrl;
    },
  },
  
  events: {
    /**
     * Called when user successfully signs in
     */
    async signIn({ user, account, profile, isNewUser }) {
      console.log(`User signed in: ${user.email} (new: ${isNewUser})`);
    },
    
    /**
     * Called when user signs out
     */
    async signOut(message) {
      if ("token" in message) {
        console.log(`User signed out: ${message.token?.email}`);
      }
    },
  },
  
  // Session configuration
  session: {
    strategy: "jwt",
    maxAge: 30 * 24 * 60 * 60, // 30 days
    updateAge: 24 * 60 * 60, // Update every 24 hours
  },
  
  // JWT configuration
  jwt: {
    maxAge: 30 * 24 * 60 * 60, // 30 days
  },
  
  // Secret for signing tokens — NextAuth v5 reads AUTH_SECRET automatically,
  // but we also accept NEXTAUTH_SECRET for v4 backwards-compatibility.
  secret: process.env.AUTH_SECRET ?? process.env.NEXTAUTH_SECRET,
};
