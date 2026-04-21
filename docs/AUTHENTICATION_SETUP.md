# Authentication System Setup Guide

## Overview

ClipMind now uses **NextAuth.js 5.0** with OAuth 2.0 providers (GitHub & Google) for secure authentication. This guide walks through the complete setup process.

## Architecture

```
User (Browser)
    ↓
[NextAuth Sign-In Page] ← OAuth Provider (GitHub/Google)
    ↓
[JWT Session Token] → Stored in HttpOnly Cookie
    ↓
[Middleware] ← Validates token, injects workspace context
    ↓
[Protected Routes/API] ← RBAC enforcement
    ↓
[Backend API] ← FastAPI with authenticated requests
```

## Files Created

### Core Authentication

- **`web/auth.config.ts`** (75 lines)
  - NextAuth configuration with OAuth callbacks
  - JWT strategy with custom claims (role, workspace)
  - Provider setup (GitHub & Google)
  - Session configuration

- **`web/app/api/auth/[...nextauth]/route.ts`** (15 lines)
  - Route handler for all OAuth flow
  - Connects Prisma adapter for database persistence

- **`web/middleware.ts`** (200+ lines)
  - RBAC middleware for route protection
  - Workspace membership validation
  - Role-based access control (owner/editor/viewer)
  - Helper functions: `hasRole()`, `requireRole()`

- **`web/lib/prisma.ts`** (20 lines)
  - Singleton Prisma client
  - Prevents database connection exhaustion in development

- **`web/lib/auth-utils.ts`** (380+ lines)
  - Server-side auth helpers:
    - `getCurrentSession()` — Get current user session
    - `getCurrentUser()` — Get authenticated user
    - `checkWorkspaceRole()` — Check RBAC permissions
    - `getUserWorkspaces()` — List user's workspaces
    - `createWorkspace()` — Create new workspace
    - `inviteUserToWorkspace()` — Add members
    - `generatePortalToken()` — Create client tokens
    - `verifyPortalToken()` — Validate tokens

### UI Components

- **`web/components/auth-provider.tsx`** (UPDATED - 140 lines)
  - Upgraded from stub auth to real NextAuth
  - SessionProvider wrapper for JWT tokens
  - New hooks:
    - `useAuth()` — Access auth context
    - `useHasRole()` — Check role permissions
  - New components:
    - `<Protected>` — Guard sensitive content
    - `<RoleProtected>` — RBAC-protected UI

- **`web/app/auth/signin/page.tsx`** (NEW - 230 lines)
  - OAuth sign-in page with GitHub & Google buttons
  - Error handling for OAuth failures
  - Loading states during sign-in
  - Feature highlights for new users

- **`web/app/auth/error/page.tsx`** (NEW - 80 lines)
  - Error page for authentication failures
  - User-friendly error messages
  - Recovery actions (retry, go home)

### Configuration

- **`web/.env.example`** (NEW)
  - Template for environment variables
  - OAuth provider IDs and secrets
  - Database connection string
  - NextAuth secret

- **`web/prisma/schema.prisma`** (UPDATED - 130 lines)
  - User model (email, role, OAuth accounts)
  - Account model (OAuth provider credentials)
  - Session model (JWT session tracking)
  - Workspace models (RBAC and client access)

## Step-by-Step Setup

### 1. Install Dependencies

Dependencies are already added to `package.json`:
```json
{
  "next-auth": "^5.0.0",
  "@auth/core": "^0.31.0",
  "@auth/nextjs": "^1.6.0",
  "@next-auth/prisma-adapter": "^1.2.0",
  "prisma": "^5.17.0",
  "@prisma/client": "^5.17.0",
  "bcryptjs": "^2.4.3",
  "jsonwebtoken": "^9.1.2"
}
```

Install with:
```bash
cd web
npm install
```

### 2. Set Up OAuth Providers

#### GitHub OAuth

1. Go to https://github.com/settings/developers
2. Click "New OAuth App"
3. Fill in:
   - Application name: `ClipMind` (or your app name)
   - Homepage URL: `http://localhost:3000` (or production URL)
   - Authorization callback URL: `http://localhost:3000/api/auth/callback/github`
4. Copy **Client ID** and **Client Secret**
5. Add to `.env.local`:
   ```
   GITHUB_ID=your_client_id
   GITHUB_SECRET=your_client_secret
   ```

#### Google OAuth

1. Go to https://console.cloud.google.com/
2. Create a new project or select existing
3. Enable "Google+ API"
4. Go to "Credentials" → Create OAuth 2.0 Client ID
5. Choose "Web application"
6. Add authorized redirect URIs:
   - `http://localhost:3000/api/auth/callback/google`
   - `https://yourdomain.com/api/auth/callback/google` (production)
7. Copy **Client ID** and **Client Secret**
8. Add to `.env.local`:
   ```
   GOOGLE_ID=your_client_id
   GOOGLE_SECRET=your_client_secret
   ```

### 3. Configure Environment Variables

Create `web/.env.local` (copy from `.env.example`):

```bash
# Generate a secure random string (32+ chars) for production
NEXTAUTH_SECRET=$(openssl rand -base64 32)

NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_URL_INTERNAL=http://localhost:3000

# Database (must point to running PostgreSQL)
DATABASE_URL=postgresql://user:password@localhost:5432/clipmind

# OAuth (from GitHub/Google setup)
GITHUB_ID=your_github_id
GITHUB_SECRET=your_github_secret
GOOGLE_ID=your_google_id
GOOGLE_SECRET=your_google_secret

# Backend
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE=/api/v1
```

### 4. Set Up Database

```bash
cd web
# Run Prisma migrations
npx prisma migrate deploy

# Or in dev mode for schema changes:
npx prisma migrate dev --name init
```

This creates:
- `User` table with OAuth accounts
- `Account` table for OAuth provider data
- `Session` table for JWT tokens
- `Workspace` tables for team collaboration
- `PortalToken` table for client access

### 5. Start the Application

```bash
cd web
npm run dev
```

Visit `http://localhost:3000`

## Usage

### In Server Components

```typescript
// Get current session
import { auth } from "@/auth.config";

export default async function Dashboard() {
  const session = await auth();
  
  if (!session) {
    redirect("/auth/signin");
  }
  
  return <div>Welcome, {session.user?.name}!</div>;
}
```

### In Client Components

```typescript
"use client";

import { useAuth, Protected, RoleProtected } from "@/components/auth-provider";

export default function Settings() {
  const { user, isAuthenticated } = useAuth();
  
  return (
    <Protected>
      <RoleProtected role="owner">
        {/* Only owners see this */}
        <AdminPanel />
      </RoleProtected>
    </Protected>
  );
}
```

### In API Routes

```typescript
// app/api/workspaces/create/route.ts
import { auth } from "@/auth.config";
import { prisma } from "@/lib/prisma";
import { requireRole } from "@/middleware";

export async function POST(req: NextRequest) {
  const session = await auth();
  
  if (!session?.user) {
    return NextResponse.json(
      { error: "Unauthorized" },
      { status: 401 }
    );
  }
  
  // Create workspace linked to authenticated user
  const workspace = await prisma.workspace.create({
    data: {
      name: "My Workspace",
      members: {
        create: {
          userId: session.user.id,
          role: "owner",
        },
      },
    },
  });
  
  return NextResponse.json(workspace);
}
```

### Server Actions & Auth Utils

```typescript
// Use auth-utils helpers
import { 
  getCurrentUser, 
  checkWorkspaceRole,
  createWorkspace,
  inviteUserToWorkspace,
} from "@/lib/auth-utils";

export async function createTeamWorkspace(name: string) {
  const workspace = await createWorkspace(name);
  return workspace;
}

export async function addTeamMember(
  workspaceId: string, 
  email: string, 
  role: "editor" | "viewer"
) {
  const result = await inviteUserToWorkspace(workspaceId, email, role);
  
  if (result.success) {
    revalidatePath(`/workspaces/${workspaceId}`);
  }
  
  return result;
}
```

## RBAC (Role-Based Access Control)

### Role Hierarchy

```
Owner (3)
  ↓ Can do everything
Editor (2)
  ↓ Can edit content
Viewer (1)
  ↓ Read-only
```

### Check Permissions

```typescript
// In middleware or API routes
import { hasRole, requireRole } from "@/middleware";

// Object way
if (!hasRole(userRole, "owner")) {
  return NextResponse.json({ error: "Forbidden" }, { status: 403 });
}

// Response way (returns error response or null)
const error = requireRole(request, "owner");
if (error) return error;
```

### Protect Routes

Routes matching these patterns are automatically protected:
- `/workspaces/*`
- `/dashboard/*`
- `/settings/*`
- `/api/workspaces/*`
- `/api/portals/*`

Update `web/middleware.ts` to adjust protection patterns.

## Portal Tokens (Client Access)

For clients who don't have accounts, generate time-limited tokens:

```typescript
// Generate token
const { token } = await generatePortalToken(
  workspaceId,
  clientId,
  24 * 60 * 60 * 1000 // 24 hours
);

// Share with client
console.log(`Portal URL: https://clipmind.com/?token=${token}`);

// Client-side: Verify token
const portalData = await verifyPortalToken(token);
if (portalData) {
  // Client has access to portalData.workspaceId
}
```

## Production Deployment

### Environment Variables (Production)

```bash
NEXTAUTH_SECRET=use_a_secure_random_secret
NEXTAUTH_URL=https://yourdomain.com
DATABASE_URL=postgresql://prod_user:prod_pass@prod_db:5432/clipmind
GITHUB_ID=production_github_id
GITHUB_SECRET=production_github_secret
GOOGLE_ID=production_google_id
GOOGLE_SECRET=production_google_secret
```

### OAuth Redirect URIs (Production)

Update GitHub and Google OAuth apps with production callback URLs:
- GitHub: `https://yourdomain.com/api/auth/callback/github`
- Google: `https://yourdomain.com/api/auth/callback/google`

### Build & Deploy

```bash
cd web
npm run build
npm run start
```

## Troubleshooting

### "OAuthAccountNotLinked" Error
- User tried signing in with different provider than their account
- Solution: Use same OAuth provider or contact support to merge accounts

### 403 Forbidden on Workspace Routes
- User is not a member of that workspace
- Solution: Owner must invite user to workspace

### Token Expired
- JWT token expired (default: 30 days)
- Solution: User automatically redirected to sign-in on next request

### Database Connection Error
- `DATABASE_URL` is invalid or DB is not running
- Solution: Check `.env.local` and start PostgreSQL server

## Next Steps

1. ✅ Install dependencies
2. ✅ Set up OAuth providers
3. ✅ Configure environment variables
4. ⏳ Run database migrations
5. ⏳ Start application and test sign-in
6. ⏳ Test workspace creation and member invitation
7. ⏳ Deploy to production

## Key Features Now Enabled

- ✅ Secure OAuth authentication (GitHub, Google)
- ✅ JWT session tokens with custom claims
- ✅ Role-based access control (RBAC)
- ✅ Workspace membership management
- ✅ Portal tokens for client access
- ✅ Automatic session handling
- ✅ Middleware-based route protection
- ✅ Type-safe authentication with TypeScript

## Security Considerations

1. **NEXTAUTH_SECRET**: Must be 32+ characters in production
2. **HttpOnly Cookies**: Session tokens stored securely
3. **CSRF Protection**: Built into NextAuth
4. **OAuth Token Rotation**: Handled automatically
5. **RBAC Enforcement**: All routes validate membership + role
6. **Portal Tokens**: Time-limited, can be revoked

## Support & Next Features

- Contact support for issues
- Coming: Email/password authentication
- Coming: Two-factor authentication
- Coming: Session management dashboard
- Coming: Audit logs with user actions
