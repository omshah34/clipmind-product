/**
 * File: app/auth/error-content.tsx
 * Purpose: Auth error page content component. Uses useSearchParams for error handling.
 *          Wrapped in Suspense in parent page component.
 */

"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";

function getErrorMessage(error: string | null): string {
  if (!error) return "An unknown error occurred.";

  const errorMessages: Record<string, string> = {
    OAuthAccountNotLinked: "Email already linked with another provider",
    OAuthCallback: "Error during OAuth callback",
    OAuthSignin: "Error signing in with OAuth provider",
    OAuthCreateAccount: "Could not create an account with this provider",
    EmailCreateAccount: "Could not create account with email",
    Callback: "Error in callback handler",
    EmailSignInError: "Could not sign in with that email",
    SessionCallback: "Session callback error",
    CredentialsSignin: "Invalid credentials",
    AccessDenied: "Access denied",
    Verification: "Verification link expired or invalid",
  };

  return errorMessages[error] || "An error occurred during authentication.";
}

export default function AuthErrorContent() {
  const searchParams = useSearchParams();
  const error = searchParams.get("error");

  return (
    <div className="min-h-screen bg-gradient-to-br from-red-50 to-orange-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="text-6xl mb-4">⚠️</div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Authentication Error
          </h1>
          <p className="text-gray-600">
            Something went wrong during sign in
          </p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-lg shadow-lg p-8">
          {/* Error Message */}
          <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
            Authentication Error
          </h2>
          <p className="text-gray-600 text-center mb-6">
            {getErrorMessage(error)}
          </p>

          {/* Error Code */}
          {error && (
            <div className="bg-gray-50 rounded p-3 mb-6 text-sm text-gray-500 font-mono text-center">
              Error code: {error}
            </div>
          )}

          {/* Actions */}
          <div className="space-y-3">
            <Link
              href="/auth/signin"
              className="block w-full px-4 py-2 bg-blue-600 text-white text-center rounded-lg hover:bg-blue-700 transition-colors"
            >
              Try Again
            </Link>
            <Link
              href="/"
              className="block w-full px-4 py-2 bg-gray-200 text-gray-900 text-center rounded-lg hover:bg-gray-300 transition-colors"
            >
              Go Home
            </Link>
          </div>

          {/* Support */}
          <p className="text-center text-sm text-gray-500 mt-6">
            Need help?{" "}
            <a
              href="mailto:support@clipmind.com"
              className="text-blue-600 hover:underline"
            >
              Contact Support
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
