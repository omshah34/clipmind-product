/**
 * File: app/portal/[slug]/page.tsx
 * Purpose: Public client review portal landing page.
 */

import Link from "next/link";

export default async function ClientPortalPage({
  params,
  searchParams,
}: {
  params: { slug: string };
  searchParams?: { token?: string };
}) {
  const { slug } = params;
  const token = searchParams?.token;

  return (
    <main className="page">
      <div className="panel" style={{ maxWidth: 760, margin: "64px auto" }}>
        <div className="brand" style={{ marginBottom: 20 }}>
          <div className="brand-mark">
            <div className="brand-dot" style={{ background: "linear-gradient(135deg, #4facfe, #00f2fe)" }} />
            Client Review Portal
          </div>
        </div>

        <h1 style={{ fontSize: 42, lineHeight: 1.05, marginBottom: 14 }}>
          Review, approve, and request changes without the email chaos.
        </h1>
        <p style={{ color: "var(--muted)", maxWidth: 620, marginBottom: 24 }}>
          This portal is tied to the slug <strong>{slug}</strong>. It is the public entry point for client approvals,
          content notes, and revision requests.
        </p>

        <div className="panel" style={{ marginBottom: 18, background: "rgba(255,255,255,0.03)" }}>
          <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 8 }}>Portal Token</div>
          <div style={{ wordBreak: "break-all", fontSize: 14 }}>
            {token || "No token supplied"}
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Link className="button" href="/team">
            Go to Team
          </Link>
          <Link className="button" href="/campaigns">
            View Campaigns
          </Link>
        </div>
      </div>
    </main>
  );
}
