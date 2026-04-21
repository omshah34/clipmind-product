# OAuth Providers Setup Guide

This guide walks through configuring GitHub and Google OAuth 2.0 for use with ClipMind's NextAuth authentication system.

## Overview

ClipMind supports two OAuth 2.0 providers:
- **GitHub** — For developers and technical users
- **Google** — For general users and agency teams

Both providers securely delegate authentication to their servers, then return a JWT token for use across ClipMind.

## GitHub OAuth Setup

### Step 1: Create GitHub OAuth App

1. Go to [https://github.com/settings/developers](https://github.com/settings/developers)
2. Click **"New OAuth App"** (or "Register a new application")
3. Fill in the form:
   - **Application name**: `ClipMind` (or your deployment name)
   - **Homepage URL**: 
     - Development: `http://localhost:3000`
     - Production: `https://yourdomain.com`
   - **Application description**: `AI-powered short-form video processing platform`
   - **Authorization callback URL**:
     - Development: `http://localhost:3000/api/auth/callback/github`
     - Production: `https://yourdomain.com/api/auth/callback/github`

4. Click **"Register application"**

### Step 2: Copy Credentials

After registration, you'll see:
- **Client ID** — Copy this
- **Client Secret** — Click "Generate a new client secret" and copy it

⚠️ **IMPORTANT**: Never commit Client Secret to version control. Store it in `.env.local` only.

### Step 3: Add to Environment

In `web/.env.local`:
```bash
GITHUB_ID=your_github_client_id_here
GITHUB_SECRET=your_github_client_secret_here
```

### Step 4: Verify Configuration

Test OAuth flow at `http://localhost:3000/auth/signin`

---

## Google OAuth Setup

### Step 1: Create Google Cloud Project

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Click the project dropdown at the top
3. Click **"NEW PROJECT"**
4. Enter:
   - **Project name**: `ClipMind` (or your app name)
   - Leave Organization as default
5. Click **"CREATE"**
6. Wait for the project to be created (this takes ~1-2 minutes, watch the notifications bell)

### Step 2: Enable Google+ API

1. In the project, go to **"APIs & Services"** → **"Library"**
2. Search for **"Google+ API"** (Note: This is Google's user profile API)
3. Click on it
4. Click **"ENABLE"**

### Step 3: Create OAuth 2.0 Credentials

1. Go back to **"APIs & Services"** → **"Credentials"**
2. Click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. If prompted to configure the OAuth consent screen, click **"CONFIGURE CONSENT SCREEN"**

### Step 4: Configure OAuth Consent Screen

1. Choose **"External"** user type (unless you're in a Google Workspace organization)
2. Click **"CREATE"**
3. Fill in the form:
   - **App name**: `ClipMind`
   - **User support email**: Your email address
   - **Developer contact information**: Your email address
4. Click **"SAVE AND CONTINUE"**
5. Skip "Scopes" section, click **"SAVE AND CONTINUE"**
6. Skip "Test users" section, click **"SAVE AND CONTINUE"**
7. Review and click **"BACK TO DASHBOARD"**

### Step 5: Create OAuth Client

1. Go to **"APIs & Services"** → **"Credentials"** again
2. Click **"+ CREATE CREDENTIALS"** → **"OAuth client ID"**
3. Select **"Web application"**
4. Under **"Authorized JavaScript origins"**, add:
   - Development: `http://localhost:3000`
   - Production: `https://yourdomain.com`
5. Under **"Authorized redirect URIs"**, add:
   - Development: `http://localhost:3000/api/auth/callback/google`
   - Production: `https://yourdomain.com/api/auth/callback/google`
6. Click **"CREATE"**
7. Copy the credentials:
   - **Client ID**
   - **Client Secret**

### Step 6: Add to Environment

In `web/.env.local`:
```bash
GOOGLE_ID=your_google_client_id_here
GOOGLE_SECRET=your_google_client_secret_here
```

### Step 7: Verify Configuration

Test OAuth flow at `http://localhost:3000/auth/signin`

---

## Environment Variables Summary

After completing both setups, your `web/.env.local` should contain:

```bash
# NextAuth
NEXTAUTH_SECRET=your_random_secret_here_min_32_chars
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_URL_INTERNAL=http://localhost:3000

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/clipmind

# GitHub OAuth
GITHUB_ID=your_github_client_id
GITHUB_SECRET=your_github_client_secret

# Google OAuth
GOOGLE_ID=your_google_client_id
GOOGLE_SECRET=your_google_client_secret

# Backend API
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_API_BASE=/api/v1

# Backend Auth Settings (so backend can validate tokens)
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=same_secret_as_above
```

---

## Testing OAuth Flow

### Development Environment

1. Start the application: `npm run dev`
2. Visit `http://localhost:3000/auth/signin`
3. Click "Sign in with GitHub" or "Sign in with Google"
4. You should be redirected to the OAuth provider
5. Grant permissions (if first time)
6. You should be redirected back to ClipMind with a session
7. You should see your name/email displayed

### Troubleshooting

#### "Invalid redirect URI"
- **Cause**: The callback URL in environment doesn't match the provider setup
- **Fix**: Double-check GITHUB_ID/GOOGLE_ID redirect URIs match exactly:
  - `http://localhost:3000/api/auth/callback/github`
  - `http://localhost:3000/api/auth/callback/google`

#### "Client ID or Secret is invalid"
- **Cause**: Wrong credentials copied from provider console
- **Fix**: Re-copy credentials from GitHub Settings or Google Cloud Console

#### OAuth page shows error immediately
- **Cause**: `NEXTAUTH_SECRET` not set or NEXTAUTH_URL incorrect
- **Fix**: Make sure `.env.local` has both variables set

#### "OAuthAccountNotLinked" error
- **Cause**: User has accounts linked with different providers
- **Fix**: Use the same provider, or contact support to merge accounts

---

## Production Deployment

When deploying to production, update OAuth configurations:

### Update GitHub OAuth App

1. Go to [https://github.com/settings/developers](https://github.com/settings/developers)
2. Click your app
3. Update **Homepage URL** to production domain
4. Update **Authorization callback URL** to:
   ```
   https://yourdomain.com/api/auth/callback/github
   ```

### Update Google OAuth

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. In **"Credentials"**, click your OAuth 2.0 Web application
3. Add production domain to **"Authorized JavaScript origins"**:
   ```
   https://yourdomain.com
   ```
4. Add production callback to **"Authorized redirect URIs"**:
   ```
   https://yourdomain.com/api/auth/callback/google
   ```
5. Click **"SAVE"**

### Production Environment Variables

Update `web/.env.production` (or your hosting platform's env vars):

```bash
NEXTAUTH_URL=https://yourdomain.com
NEXTAUTH_SECRET=use_a_secure_random_generated_secret_32_chars_min
GITHUB_ID=your_prod_github_id
GITHUB_SECRET=your_prod_github_secret
GOOGLE_ID=your_prod_google_id
GOOGLE_SECRET=your_prod_google_secret
DATABASE_URL=postgresql://prod_user:prod_password@prod_database:5432/clipmind
```

Generate NEXTAUTH_SECRET with:
```bash
openssl rand -base64 32
```

---

## Security Best Practices

1. **Never commit secrets** — Use `.env.local` (in .gitignore) for development
2. **Rotate secrets regularly** — If leaked, regenerate immediately
3. **Use HTTPS in production** — OAuth requires secure connections
4. **Validate tokens on backend** — The backend must verify tokens from NextAuth
5. **Set appropriate scopes** — OAuth requests only necessary permissions
6. **Revoke unused apps** — Clean up old OAuth apps in provider dashboards

---

## Support

If you encounter issues:
1. Check `.env.local` has all required variables
2. Verify OAuth app redirect URIs match exactly (no trailing slashes, case-sensitive)
3. Make sure NEXTAUTH_URL matches your deployment URL
4. Check browser dev tools (F12) for actual error messages
5. See backend logs for token validation errors

---

## Next Steps

✅ OAuth providers configured
✅ Environment variables set
⏳ Database migrations running
⏳ Application deployment
⏳ Team member invitations
