/**
 * File: app/auth/signin/signin-content.tsx
 * Purpose: SignIn page content component. Uses useSearchParams for handling
 *          OAuth callback parameters and error states. Wrapped in Suspense.
 */

"use client";

import { signIn } from "next-auth/react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

export default function SignInContent() {
  const searchParams = useSearchParams();
  const callbackUrl = searchParams.get("callbackUrl") || "/workspaces";
  const error = searchParams.get("error");
  const [isLoading, setIsLoading] = useState<"github" | "google" | null>(null);

  const handleSignIn = async (provider: "github" | "google") => {
    setIsLoading(provider);
    try {
      await signIn(provider, {
        callbackUrl,
        redirect: true,
      });
    } finally {
      setIsLoading(null);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Welcome to ClipMind
          </h1>
          <p className="text-gray-600">
            Sign in to your account to get started
          </p>
        </div>

        {/* Card */}
        <div className="bg-white rounded-lg shadow-lg p-8">
          {/* Error Message */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-red-700 text-sm">
                {error === "OAuthAccountNotLinked"
                  ? "Email already linked with another provider"
                  : "An error occurred during sign-in. Please try again."}
              </p>
            </div>
          )}

          {/* OAuth Buttons */}
          <div className="space-y-3 mb-6">
            {/* GitHub Sign In */}
            <button
              onClick={() => handleSignIn("github")}
              disabled={isLoading !== null}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-gray-900 text-white rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading === "github" ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border border-white border-t-transparent" />
                  Signing in...
                </>
              ) : (
                <>
                  <GitHubIcon />
                  Sign in with GitHub
                </>
              )}
            </button>

            {/* Google Sign In */}
            <button
              onClick={() => handleSignIn("google")}
              disabled={isLoading !== null}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-white text-gray-700 border-2 border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {isLoading === "google" ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-2 border-blue-500 border-t-transparent" />
                  Signing in...
                </>
              ) : (
                <>
                  <GoogleIcon />
                  Sign in with Google
                </>
              )}
            </button>
          </div>

          {/* Divider */}
          <div className="relative mb-6">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-gray-300" />
            </div>
            <div className="relative flex justify-center text-sm">
              <span className="px-2 bg-white text-gray-500">
                New to ClipMind?
              </span>
            </div>
          </div>

          {/* Sign Up Info */}
          <p className="text-center text-sm text-gray-600 mb-4">
            Sign in with GitHub or Google to create your account
          </p>

          {/* Features List */}
          <div className="space-y-3 text-sm">
            <div className="flex gap-2">
              <CheckIcon />
              <span className="text-gray-700">
                Smart clip detection with AI
              </span>
            </div>
            <div className="flex gap-2">
              <CheckIcon />
              <span className="text-gray-700">
                Multi-platform publishing
              </span>
            </div>
            <div className="flex gap-2">
              <CheckIcon />
              <span className="text-gray-700">
                Team collaboration workspace
              </span>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-8 text-sm text-gray-600">
          <p>
            By signing in, you agree to our{" "}
            <a
              href="#"
              className="text-blue-600 hover:underline"
            >
              Terms of Service
            </a>{" "}
            and{" "}
            <a
              href="#"
              className="text-blue-600 hover:underline"
            >
              Privacy Policy
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}

// Icons
function GitHubIcon() {
  return (
    <svg
      className="w-5 h-5"
      fill="currentColor"
      viewBox="0 0 20 20"
    >
      <path
        fillRule="evenodd"
        d="M10 0C4.477 0 0 4.484 0 10.017c0 4.425 2.865 8.18 6.839 9.49.5.092.682-.217.682-.482 0-.237-.008-.868-.013-1.703-2.782.603-3.369-1.343-3.369-1.343-.454-1.156-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.544 2.914 1.186.092-.923.35-1.544.636-1.9-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.268.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0110 4.817c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.379.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C17.137 18.194 20 14.44 20 10.017 20 4.484 15.522 0 10 0z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function GoogleIcon() {
  return (
    <svg
      className="w-5 h-5"
      viewBox="0 0 24 24"
      fill="currentColor"
    >
      <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      className="w-5 h-5 text-green-500 flex-shrink-0"
      fill="currentColor"
      viewBox="0 0 20 20"
    >
      <path
        fillRule="evenodd"
        d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
        clipRule="evenodd"
      />
    </svg>
  );
}
