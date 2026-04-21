/**
 * File: error/page.tsx
 * Location: app/auth/
 * Purpose: Authentication error page wrapper with Suspense boundary
 */

import { Suspense } from "react";
import AuthErrorContent from "../error-content";

export default function AuthError() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <AuthErrorContent />
    </Suspense>
  );
}
