/**
 * File: app/layout.tsx
 * Purpose: Root layout component. Sets up global styles, metadata,
 *          and app-wide layout structure for all pages.
 */

import type { ReactNode } from "react";
import React from "react";
import type { Metadata, Viewport } from "next";
import { Providers } from "./providers";
import BodyShell from "./BodyShell";

export const metadata: Metadata = {
  title: "ClipMind — AI Video Studio",
  description: "Turn long videos into ready-to-post clips automatically.",
};

// ... (rest of metadata/viewport)

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};


const globalStyles = `
  :root {
    color-scheme: light;
    --bg: #f6f8fc;
    --bg-soft: #eef3f9;
    --surface: rgba(255, 255, 255, 0.84);
    --surface-strong: rgba(255, 255, 255, 0.96);
    --panel: rgba(255, 255, 255, 0.86);
    --panel-strong: rgba(255, 255, 255, 0.96);
    --text: #102033;
    --muted: #5f6b7d;
    --line: rgba(16, 32, 51, 0.1);
    --accent: #ff6f61;
    --accent-soft: rgba(255,111,97,0.12);
    --accent-strong: #a53c2f;
    --accent-glow: rgba(255,111,97,0.55);
    --accent-border: rgba(255,111,97,0.18);
    --accent-text: #9f3c2f;
    --shadow: 0 12px 28px rgba(16, 32, 51, 0.06);
    --shadow-lg: 0 24px 54px rgba(16, 32, 51, 0.1);
  }

  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: radial-gradient(circle at top, #ffffff 0%, var(--bg) 44%, #e7edf6 100%); color: var(--text); }
  body { font-family: "Space Grotesk", "Segoe UI", sans-serif; min-height: 100vh; }
  a { color: inherit; text-decoration: none; }
  button, input { font: inherit; }
  .shell { min-height: 100vh; position: relative; overflow: hidden; }
  .shell::before {
    content: "";
    position: fixed;
    inset: 0;
    background:
      linear-gradient(90deg, rgba(16,32,51,0.045) 1px, transparent 1px),
      linear-gradient(rgba(16,32,51,0.03) 1px, transparent 1px);
    background-size: 120px 120px;
    mask-image: linear-gradient(to bottom, rgba(0,0,0,0.75), rgba(0,0,0,0.12));
    pointer-events: none;
  }
  .page {
    width: min(1240px, calc(100vw - 40px));
    margin: 0 auto;
    padding: 28px 0 80px;
    position: relative;
    z-index: 1;
  }
  .brand {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 28px;
  }
  .brand-mark {
    display: inline-flex;
    gap: 12px;
    align-items: center;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-size: 12px;
    color: var(--muted);
  }
  .brand-dot {
    width: 12px;
    height: 12px;
    border-radius: 999px;
    background: linear-gradient(135deg, #ffd4ba, var(--accent));
    box-shadow: 0 0 24px var(--accent-glow);
  }
  .hero {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(320px, 420px);
    gap: 28px;
    align-items: stretch;
  }
  .hero-shell {
    position: relative;
  }
  .hero-copy {
    display: grid;
    align-content: start;
    gap: 18px;
    padding: 42px 0 0;
  }
  .hero-copy h1 {
    font-size: clamp(60px, 8vw, 108px);
    line-height: 0.9;
    margin-bottom: 0;
    max-width: 8ch;
  }
  .hero-copy .lead {
    font-size: 19px;
    max-width: 42ch;
    margin-bottom: 0;
  }
  .hero-actions {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 14px;
  }
  .hero-meta {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-top: 6px;
  }
  .hero-chip {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.82);
    border: 1px solid var(--line);
    color: var(--muted);
    font-size: 13px;
    box-shadow: var(--shadow);
  }
  .poster {
    min-height: 620px;
    border: 1px solid var(--line);
    background:
      radial-gradient(circle at top right, var(--accent-soft), transparent 32%),
      radial-gradient(circle at left center, rgba(78, 144, 226, 0.1), transparent 28%),
      var(--surface-strong);
    border-radius: 32px;
    padding: 30px;
    position: relative;
    overflow: hidden;
    animation: rise 520ms ease-out both;
    box-shadow: var(--shadow-lg);
  }
  .poster::after {
    content: "";
    position: absolute;
    inset: 0;
    background:
      linear-gradient(135deg, rgba(255,255,255,0.9), rgba(255,255,255,0.35)),
      linear-gradient(90deg, var(--line) 1px, transparent 1px),
      linear-gradient(var(--line) 1px, transparent 1px);
    background-size: auto, 72px 72px, 72px 72px;
    opacity: 0.35;
    pointer-events: none;
  }
  .kicker {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 8px 14px;
    border-radius: 999px;
    background: var(--accent-soft);
    border: 1px solid var(--accent-border);
    color: var(--accent-text);
    font-size: 13px;
    margin-bottom: 18px;
  }
  h1 {
    font-size: clamp(48px, 7vw, 98px);
    line-height: 0.92;
    margin: 0 0 18px;
    max-width: 9ch;
    letter-spacing: -0.06em;
  }
  .lead {
    max-width: 40ch;
    font-size: 18px;
    line-height: 1.65;
    color: var(--muted);
    margin: 0 0 28px;
  }
  .metrics {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 14px;
    margin-top: 24px;
  }
  .metric {
    padding: 16px;
    border-radius: 18px;
    background: rgba(255,255,255,0.92);
    border: 1px solid var(--line);
    backdrop-filter: blur(8px);
    box-shadow: var(--shadow);
  }
  .metric strong { display: block; font-size: 28px; margin-bottom: 4px; }
  .metric span { color: var(--muted); font-size: 13px; }
  .panel {
    border-radius: 28px;
    border: 1px solid var(--line);
    background: var(--panel);
    padding: 28px;
    backdrop-filter: blur(16px);
    animation: rise 680ms ease-out both;
    box-shadow: var(--shadow-lg);
  }
  .panel h2 { margin: 0 0 10px; font-size: 28px; letter-spacing: -0.03em; }
  .panel p { margin: 0 0 18px; color: var(--muted); line-height: 1.6; }
  .upload-form {
    display: grid;
    gap: 14px;
  }
  .upload-dropzone {
    display: grid;
    gap: 10px;
    padding: 20px;
    border-radius: 22px;
    border: 1px solid var(--line);
    background:
      linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,250,255,0.96));
    box-shadow: var(--shadow);
    cursor: pointer;
    transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
  }
  .upload-dropzone:hover {
    transform: translateY(-1px);
    border-color: var(--accent-border);
    box-shadow: 0 18px 34px rgba(16, 32, 51, 0.08);
  }
  .upload-dropzone-top {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: flex-start;
  }
  .upload-label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--muted);
    margin-bottom: 4px;
  }
  .upload-title {
    margin: 0;
    font-size: 18px;
    letter-spacing: -0.02em;
  }
  .upload-copy {
    margin: 0;
    color: var(--muted);
    line-height: 1.55;
    font-size: 14px;
  }
  .upload-browse {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 10px 14px;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent-text);
    border: 1px solid var(--accent-border);
    font-weight: 700;
    font-size: 13px;
    white-space: nowrap;
  }
  .upload-file {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    font-size: 13px;
    color: var(--muted);
  }
  .upload-file strong {
    color: var(--text);
    font-weight: 700;
  }
  .upload-input {
    display: none;
  }
  .field {
    padding: 18px;
    border-radius: 18px;
    border: 1px dashed var(--line);
    background: rgba(255,255,255,0.9);
  }
  .upload-row {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
  }
  .button {
    border: 0;
    border-radius: 999px;
    padding: 14px 22px;
    background: linear-gradient(135deg, #ffd3b8, var(--accent));
    color: #140c08;
    font-weight: 700;
    cursor: pointer;
    transition: transform 180ms ease, box-shadow 180ms ease;
    box-shadow: 0 14px 30px rgba(255,111,97,0.22);
  }
  .button:hover { transform: translateY(-1px); }
  .button:disabled { opacity: 0.55; cursor: not-allowed; box-shadow: none; }
  .subtle-button {
    border: 1px solid var(--line);
    background: rgba(255,255,255,0.8);
    color: var(--text);
    padding: 12px 18px;
    border-radius: 999px;
    transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
    box-shadow: var(--shadow);
  }
  .subtle-button:hover { transform: translateY(-1px); border-color: var(--accent-border); box-shadow: 0 16px 28px rgba(16, 32, 51, 0.08); }
  .section-band {
    display: grid;
    gap: 18px;
    margin-top: 28px;
    padding: 26px 0 0;
    border-top: 1px solid var(--line);
  }
  .section-band h2 {
    margin: 0;
    font-size: 24px;
    letter-spacing: -0.03em;
  }
  .section-band p {
    margin: 0;
    color: var(--muted);
    line-height: 1.6;
    max-width: 60ch;
  }
  .feature-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 18px;
  }
  .feature-item {
    padding: 18px 0;
    border-top: 1px solid var(--line);
  }
  .feature-item strong {
    display: block;
    font-size: 16px;
    margin-bottom: 8px;
    letter-spacing: -0.01em;
  }
  .feature-item span {
    color: var(--muted);
    line-height: 1.6;
    font-size: 14px;
  }
  .signal-board {
    display: grid;
    gap: 14px;
  }
  .signal-frame {
    position: relative;
    border-radius: 28px;
    padding: 18px;
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(246,249,253,0.92));
    box-shadow: var(--shadow);
  }
  .signal-frame::before {
    content: "";
    position: absolute;
    inset: 12px;
    border-radius: 20px;
    border: 1px solid var(--accent-border);
    pointer-events: none;
  }
  .signal-header {
    display: flex;
    justify-content: space-between;
    gap: 14px;
    align-items: center;
    margin-bottom: 16px;
  }
  .signal-header strong {
    font-size: 15px;
    letter-spacing: -0.02em;
  }
  .signal-header span {
    color: var(--muted);
    font-size: 13px;
  }
  .signal-steps {
    display: grid;
    gap: 10px;
  }
  .signal-step {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    padding: 14px 16px;
    border-radius: 18px;
    background: rgba(255,255,255,0.96);
    border: 1px solid var(--line);
  }
  .signal-step b {
    display: block;
    font-size: 14px;
    margin-bottom: 2px;
  }
  .signal-step small {
    color: var(--muted);
  }
  .signal-step em {
    font-style: normal;
    font-size: 12px;
    color: var(--accent-text);
    background: var(--accent-soft);
    padding: 6px 10px;
    border-radius: 999px;
    border: 1px solid var(--accent-border);
  }
  .signal-meta {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }
  .signal-meta div {
    padding: 14px;
    border-radius: 18px;
    background: rgba(255,255,255,0.94);
    border: 1px solid var(--line);
  }
  .signal-meta strong {
    display: block;
    font-size: 18px;
    margin-bottom: 4px;
  }
  .signal-meta span {
    color: var(--muted);
    font-size: 13px;
  }
  .stack { display: grid; gap: 18px; margin-top: 34px; }
  .status-strip {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    align-items: center;
    color: var(--muted);
    font-size: 14px;
  }
  .progress {
    height: 8px;
    width: 100%;
    border-radius: 999px;
    background: var(--line);
    overflow: hidden;
  }
  .progress > span {
    display: block;
    height: 100%;
    width: var(--progress, 15%);
    background: linear-gradient(90deg, #ffd5ba, var(--accent));
    transition: width 300ms ease;
  }
  .clip-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 18px;
  }
  .clip-tile {
    padding: 16px;
    border: 1px solid var(--line);
    border-radius: 22px;
    background: rgba(255,255,255,0.92);
    transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
    box-shadow: 0 10px 24px rgba(16, 32, 51, 0.05);
  }
  .clip-tile:hover {
    transform: translateY(-2px);
    border-color: var(--accent-border);
    background: rgba(255,255,255,1);
  }
  .clip-meta {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
    font-size: 13px;
    color: var(--muted);
  }
  .clip-reason {
    margin: 12px 0 16px;
    color: var(--muted);
    line-height: 1.55;
    min-height: 72px;
  }
  .player {
    width: 100%;
    aspect-ratio: 9 / 16;
    border-radius: 18px;
    overflow: hidden;
    border: 1px solid var(--line);
    background: var(--bg-soft);
  }
  .player video {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .note {
    color: var(--muted);
    font-size: 14px;
    line-height: 1.6;
  }
  .alert {
    padding: 14px 16px;
    border-radius: 16px;
    border: 1px solid var(--accent-border);
    background: var(--accent-soft);
    color: var(--accent-text);
  }
  .shell-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    margin-bottom: 14px;
  }
  .shell-subtitle {
    color: var(--muted);
    font-size: 14px;
    line-height: 1.5;
    max-width: 48ch;
  }
  @keyframes rise {
    from { opacity: 0; transform: translateY(14px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @media (max-width: 980px) {
    .page { width: min(100vw - 24px, 1180px); padding: 22px 0 48px; }
    .hero { grid-template-columns: 1fr; }
    .poster { min-height: auto; }
    .metrics { grid-template-columns: 1fr; }
    .feature-grid { grid-template-columns: 1fr; }
    .signal-meta { grid-template-columns: 1fr; }
    .hero-copy { padding-top: 18px; }
    .hero-copy h1 { max-width: none; }
  }
`;


export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
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
            <div className="shell">
              <style dangerouslySetInnerHTML={{ __html: globalStyles }} />
              {children}
            </div>
          </Providers>
        </React.StrictMode>
      </BodyShell>
    </html>
  );
}
