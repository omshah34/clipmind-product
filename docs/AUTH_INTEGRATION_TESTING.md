# Authentication System - Integration Testing Guide

## Overview

This guide provides step-by-step instructions for testing the complete authentication system including OAuth flows, RBAC, workspaces, and portal tokens.

## Prerequisites

- ClipMind backend running (`python -m uvicorn api.main:app --reload`)
- ClipMind frontend running (`npm run dev`)
- PostgreSQL database with migrations applied
- OAuth apps registered (GitHub & Google)
- Environment variables configured (`.env.local` for frontend, backend config)

## Test Scenarios

### Scenario 1: Complete OAuth Flow (GitHub)

**Objective**: Verify user can sign in with GitHub and create a session

**Steps**:
1. Start application: `npm run dev` in web/
2. Navigate to `http://localhost:3000/auth/signin`
3. Click "Sign in with GitHub"
4. Authorize ClipMind on GitHub
5. Should redirect to `/workspaces`
6. Should see user name in header

**Expected Result**: ✅ Session created, user authenticated

**Commands to verify**:
```bash
# Check browser console for JWT token
console.log(localStorage.getItem('__Secure-next-auth.session-token'))

# Check NextAuth session endpoint
curl -H "Authorization: Bearer <token>" http://localhost:3000/api/auth/session
```

---

### Scenario 2: Complete OAuth Flow (Google)

**Objective**: Verify user can sign in with Google

**Steps**:
1. From login page, click "Sign in with Google"
2. Authorize ClipMind on Google
3. Should redirect to `/workspaces`

**Expected Result**: ✅ Session created with Google account

---

### Scenario 3: Create Workspace

**Objective**: Verify authenticated user can create a workspace

**Steps**:
1. Sign in with OAuth
2. Click "Create Workspace" on workspaces page
3. Enter workspace name and description
4. Submit form
5. Should see workspace created with user as owner

**API Call**:
```bash
curl -X POST http://localhost:8000/api/v1/teams \
  -H "Authorization: Bearer $(get-jwt-token)" \
  -H "Content-Type: application/json" \
  -d '{"name": "My Team", "slug": "my-team", "plan": "pro"}'

# Should return 201 Created with workspace details
```

**Expected Result**: ✅ Workspace created, user added as owner

---

### Scenario 4: Invite Team Member

**Objective**: Verify owner can invite members with specific roles

**Steps**:
1. In workspace, click "Members"
2. Click "Invite Member"
3. Enter email address
4. Select role (editor, viewer)
5. Send invite
6. Invited user should receive email with join link

**API Call**:
```bash
curl -X POST http://localhost:8000/api/v1/teams/{workspace_id}/members \
  -H "Authorization: Bearer $(get-jwt-token)" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user-123", "role": "editor"}'
```

**Expected Result**: ✅ Member invited, can join workspace with assigned role

---

### Scenario 5: RBAC - Viewer Cannot Edit

**Objective**: Verify viewer role cannot edit content

**Steps**:
1. Invite user as "viewer"
2. Have viewer sign in
3. Try to edit a clip or publish
4. Should get "Access Denied" message

**Expected Result**: ✅ Viewer cannot edit, gets 403 Forbidden

---

### Scenario 6: RBAC - Editor Cannot Delete Members

**Objective**: Verify editor cannot remove team members

**Steps**:
1. Invite user as "editor"
2. Have editor sign in
3. Go to Members page
4. Try to remove a member
5. Should not see delete button or get error

**Expected Result**: ✅ Editor cannot delete members

---

### Scenario 7: RBAC - Owner Can Do All

**Objective**: Verify owner has all permissions

**Steps**:
1. Owner signs in
2. Owner can:
   - Edit workspace settings ✓
   - Invite members ✓
   - Change member roles ✓
   - Remove members ✓
   - Delete workspace ✓

**Expected Result**: ✅ Owner has full permissions

---

### Scenario 8: Session Persistence

**Objective**: Verify session persists across page reloads

**Steps**:
1. Sign in with OAuth
2. Refresh page (F5)
3. Should still be authenticated
4. Close tab, reopen site
5. Should still be authenticated

**Expected Result**: ✅ Session persists in JWT cookie

---

### Scenario 9: Token Expiration

**Objective**: Verify user is logged out when token expires

**Steps**:
1. Sign in
2. Wait for token to expire (default 30 days, can set to 1 minute for testing)
3. Try to access protected route
4. Should redirect to login

**Expected Result**: ✅ User forced to re-authenticate

---

### Scenario 10: Generate Portal Token

**Objective**: Verify owner can generate client portal access token

**Steps**:
1. Owner signs in
2. Go to workspace → Clients
3. Click "Create Client"
4. Enter client details
5. Click "Generate Portal Token"
6. Copy token
7. Share URL: `http://localhost:3000/?token={token}`

**API Call**:
```bash
curl -X POST http://localhost:8000/api/v1/teams/{workspace_id}/portal-tokens \
  -H "Authorization: Bearer $(get-jwt-token)" \
  -H "Content-Type: application/json" \
  -d '{"client_id": "client-123", "expiresIn": 86400}'
```

**Expected Result**: ✅ Token generated, client can access portal

---

### Scenario 11: Portal Token Access

**Objective**: Verify client can access workspace with portal token

**Steps**:
1. Visit workspace with portal token: `?token=portal_token_xyz`
2. Should gain access without signing in
3. Should see workspace and shared clips
4. Should see "Client Portal" mode (limited features)

**API Validation**:
```python
# Backend should verify token:
# 1. Check token exists in database
# 2. Check token is_active = true
# 3. Check token has not expired
# 4. Return workspace_id for access
```

**Expected Result**: ✅ Client can access without account

---

### Scenario 12: Portal Token Expiration

**Objective**: Verify expired portal token denies access

**Steps**:
1. Create portal token with 1-second expiration
2. Wait 2 seconds
3. Try to access with token
4. Should show "Access Denied" message

**Expected Result**: ✅ Expired token rejected

---

### Scenario 13: Backend API Authentication

**Objective**: Verify backend API requires valid JWT token

**Steps**:

**Test 1: No token**:
```bash
curl http://localhost:8000/api/v1/teams
# Should return 401 Unauthorized
```

**Test 2: Invalid token**:
```bash
curl -H "Authorization: Bearer invalid_token_xyz" \
  http://localhost:8000/api/v1/teams
# Should return 401 Unauthorized
```

**Test 3: Valid token**:
```bash
curl -H "Authorization: Bearer $(get-jwt-token)" \
  http://localhost:8000/api/v1/teams
# Should return 200 OK with user's workspaces
```

**Expected Result**: ✅ API enforces authentication

---

### Scenario 14: Cross-Workspace Access Prevention

**Objective**: Verify user cannot access workspaces they're not members of

**Steps**:

**Test 1: User tries to access non-member workspace**:
```bash
curl -H "Authorization: Bearer $(user-token)" \
  http://localhost:8000/api/v1/teams/workspace-they-dont-own
# Should return 403 Forbidden
```

**Test 2: User lists only their workspaces**:
```bash
curl -H "Authorization: Bearer $(user-token)" \
  http://localhost:8000/api/v1/teams
# Should return only workspaces they're member of
```

**Expected Result**: ✅ Workspace isolation enforced

---

### Scenario 15: Middleware Route Protection

**Objective**: Verify middleware protects routes

**Steps**:
1. Clear session (sign out)
2. Try to access `/workspaces`
3. Should redirect to `/auth/signin`
4. Sign in
5. Should redirect back to `/workspaces`

**Expected Result**: ✅ Middleware redirects unauthenticated users

---

## Test Automation

### Run Unit Tests

```bash
# Frontend authentication tests
cd web
npm test -- tests/auth.test.ts --watch

# Backend authentication tests
cd ..
pytest tests/test_auth_backend.py -v
```

### Run Integration Tests

```bash
# Install Playwright for E2E testing
npm install -D @playwright/test

# Run E2E auth flow tests
npx playwright test tests/e2e/auth-flow.spec.ts
```

### Example E2E Test

```typescript
// tests/e2e/auth-flow.spec.ts
import { test, expect } from '@playwright/test';

test('Complete GitHub OAuth flow', async ({ page }) => {
  // Start at login page
  await page.goto('http://localhost:3000/auth/signin');
  
  // Click GitHub button
  await page.click('text=Sign in with GitHub');
  
  // Wait for redirect to GitHub
  await page.waitForURL(/github\.com.*oauth/);
  
  // Simulate GitHub auth (mocked in test environment)
  await page.goto('http://localhost:3000/workspaces');
  
  // Verify logged in
  expect(await page.getByText('My Workspaces')).toBeVisible();
});
```

---

## API Testing with cURL

### Get JWT Token

```bash
# After signing in, extract from browser cookies or session:
TOKEN=$(curl -s http://localhost:3000/api/auth/session | jq -r '.token')
export TOKEN
```

### Test Workspace Endpoints

```bash
# Create workspace
curl -X POST http://localhost:8000/api/v1/teams \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Workspace",
    "slug": "test-workspace",
    "plan": "professional"
  }'

# List workspaces
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/teams

# Get workspace details
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/teams/{workspace_id}

# Invite member
curl -X POST http://localhost:8000/api/v1/teams/{workspace_id}/members \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-uuid",
    "role": "editor"
  }'

# Create client
curl -X POST http://localhost:8000/api/v1/teams/{workspace_id}/clients \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example Agency",
    "contact_email": "client@example.com",
    "description": "Client workspace"
  }'
```

---

## Database Verification

### Check User Created

```sql
-- PostgreSQL
SELECT * FROM "User" WHERE email = 'user@example.com';
```

### Check Workspace Membership

```sql
SELECT * FROM "WorkspaceMember" 
WHERE "userId" = 'user-uuid' AND role = 'owner';
```

### Check Portal Token

```sql
SELECT * FROM "PortalToken" 
WHERE "isActive" = true AND "expiresAt" > NOW();
```

---

## Troubleshooting Test Failures

### OAuth Provider Not Responding

- **Issue**: "Error connecting to GitHub/Google"
- **Solution**: 
  - Check internet connection
  - Verify OAuth app credentials in provider console
  - Check callback URL matches exactly

### Token Validation Fails

- **Issue**: "Invalid or expired token"
- **Solution**:
  - Verify NEXTAUTH_SECRET is set
  - Check token hasn't expired
  - Verify NextAuth session endpoint is accessible

### Workspace Access Denied

- **Issue**: 403 Forbidden on workspace endpoints
- **Solution**:
  - Verify user is member of workspace
  - Check user role has permission
  - Verify JWT token includes role claim

### Database Errors

- **Issue**: "Database connection failed"
- **Solution**:
  - Verify PostgreSQL is running
  - Check DATABASE_URL is correct
  - Run migrations: `npx prisma migrate deploy`

---

## Success Criteria

All tests pass when:

- ✅ OAuth flows work (GitHub, Google)
- ✅ Sessions persist across reloads
- ✅ Tokens expire and force re-login
- ✅ Workspaces can be created
- ✅ Members can be invited with roles
- ✅ RBAC is enforced (owner > editor > viewer)
- ✅ Portal tokens work for client access
- ✅ API requires valid authentication
- ✅ Cross-workspace access is prevented
- ✅ Middleware protects routes

---

## Next Steps After Testing

1. ✅ Run full integration test suite
2. ✅ Deploy to staging environment
3. ✅ Run smoke tests on staging
4. ⏳ Deploy to production
5. ⏳ Monitor auth logs for errors
6. ⏳ Gather user feedback

---

## Reference

- NextAuth.js Docs: https://next-auth.js.org
- Prisma Docs: https://www.prisma.io/docs
- OAuth 2.0 RFC: https://tools.ietf.org/html/rfc6749
- ClipMind Docs: See AUTHENTICATION_SETUP.md and OAUTH_SETUP.md
