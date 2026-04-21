/**
 * File: signin/page.tsx
 * Location: app/auth/
 * Purpose: OAuth sign-in page with provider buttons
 */

import { Suspense } from "react";
import SignInContent from "./signin-content";

export default function SignIn() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center">Loading...</div>}>
      <SignInContent />
    </Suspense>
  );
}
