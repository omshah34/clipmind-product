import type { ReactNode } from "react";


const globalStyles = `
  :root {
    color-scheme: dark;
    --bg: #091119;
    --bg-soft: #111d29;
    --panel: rgba(17, 29, 41, 0.72);
    --panel-strong: rgba(11, 18, 27, 0.9);
    --text: #f4f2ec;
    --muted: #9fa9b7;
    --line: rgba(255,255,255,0.08);
    --accent: #ff6f61;
    --accent-soft: rgba(255,111,97,0.16);
  }

  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: radial-gradient(circle at top, #1b2c3f 0%, var(--bg) 48%, #060b12 100%); color: var(--text); }
  body { font-family: "Space Grotesk", "Segoe UI", sans-serif; min-height: 100vh; }
  a { color: inherit; text-decoration: none; }
  button, input { font: inherit; }
  .shell { min-height: 100vh; position: relative; overflow: hidden; }
  .shell::before {
    content: "";
    position: fixed;
    inset: 0;
    background:
      linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px),
      linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px);
    background-size: 120px 120px;
    mask-image: linear-gradient(to bottom, rgba(0,0,0,0.95), rgba(0,0,0,0.2));
    pointer-events: none;
  }
  .page {
    width: min(1180px, calc(100vw - 40px));
    margin: 0 auto;
    padding: 32px 0 72px;
    position: relative;
    z-index: 1;
  }
  .brand {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    margin-bottom: 44px;
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
    box-shadow: 0 0 24px rgba(255,111,97,0.55);
  }
  .hero {
    display: grid;
    grid-template-columns: minmax(0, 1.2fr) minmax(320px, 420px);
    gap: 28px;
    align-items: stretch;
  }
  .poster {
    min-height: 580px;
    border: 1px solid var(--line);
    background:
      linear-gradient(160deg, rgba(255,111,97,0.14), transparent 30%),
      linear-gradient(180deg, rgba(255,255,255,0.06), transparent 32%),
      var(--panel-strong);
    border-radius: 28px;
    padding: 32px;
    position: relative;
    overflow: hidden;
    animation: rise 520ms ease-out both;
  }
  .poster::after {
    content: "";
    position: absolute;
    inset: auto -10% -20% 40%;
    height: 340px;
    background: radial-gradient(circle, rgba(255,111,97,0.28), transparent 70%);
    filter: blur(24px);
  }
  .kicker {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 8px 14px;
    border-radius: 999px;
    background: var(--accent-soft);
    border: 1px solid rgba(255,111,97,0.2);
    color: #ffd0c9;
    font-size: 13px;
    margin-bottom: 24px;
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
    margin-top: 38px;
  }
  .metric {
    padding: 16px;
    border-radius: 18px;
    background: rgba(255,255,255,0.03);
    border: 1px solid var(--line);
    backdrop-filter: blur(8px);
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
  }
  .panel h2 { margin: 0 0 10px; font-size: 28px; letter-spacing: -0.03em; }
  .panel p { margin: 0 0 18px; color: var(--muted); line-height: 1.6; }
  .upload-form {
    display: grid;
    gap: 14px;
  }
  .field {
    padding: 18px;
    border-radius: 18px;
    border: 1px dashed rgba(255,255,255,0.18);
    background: rgba(255,255,255,0.03);
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
    box-shadow: 0 14px 30px rgba(255,111,97,0.25);
  }
  .button:hover { transform: translateY(-1px); }
  .button:disabled { opacity: 0.55; cursor: not-allowed; box-shadow: none; }
  .subtle-button {
    border: 1px solid var(--line);
    background: transparent;
    color: var(--text);
    padding: 12px 18px;
    border-radius: 999px;
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
    background: rgba(255,255,255,0.08);
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
    background: rgba(255,255,255,0.03);
    transition: transform 180ms ease, border-color 180ms ease, background 180ms ease;
  }
  .clip-tile:hover {
    transform: translateY(-2px);
    border-color: rgba(255,111,97,0.32);
    background: rgba(255,255,255,0.05);
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
    background: #030507;
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
    border: 1px solid rgba(255,111,97,0.24);
    background: rgba(255,111,97,0.09);
    color: #ffd0c9;
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
  }
`;


export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <style dangerouslySetInnerHTML={{ __html: globalStyles }} />
          {children}
        </div>
      </body>
    </html>
  );
}
