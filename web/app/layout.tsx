/**
 * File: app/layout.tsx
 * Purpose: Root layout component. Sets up global styles, metadata,
 *          and app-wide layout structure for all pages.
 */

import type { ReactNode } from "react";
import React from "react";
import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { Providers } from "./providers";
import BodyShell from "./BodyShell";
import AppShell from "../components/AppShell";
import "./globals.css";

// Gap 275: next/font handles preloading + font-display automatically
const inter = Inter({
  subsets: ["latin"],
  display: "swap",           // Prevent invisible text flash
  preload: true,
  fallback: ["system-ui", "arial"], // Reserve identical layout space
  adjustFontFallback: true,  // ← Key: adjusts fallback metrics to match Inter
});

export const metadata: Metadata = {
  title: "ClipMind — AI Video Studio",
  description: "Turn long videos into ready-to-post clips automatically.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={inter.className} suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  const saved = localStorage.getItem('theme');
                  const pref = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
                  const theme = saved || pref;
                  if (theme === 'dark') document.documentElement.classList.add('dark');
                } catch (e) {}
              })();
            `,
          }}
        />
      </head>
      <BodyShell>
        <React.StrictMode>
          <Providers>
            <AppShell>
              {children}
            </AppShell>
          </Providers>
        </React.StrictMode>
      </BodyShell>
    </html>
  );
}