/**
 * File: app/integrations/page.tsx
 * Purpose: Lightweight integrations hub for connected social accounts.
 */

"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth-provider";

type Integration = {
  platform: string;
  account_name: string | null;
  is_active: boolean;
  last_error: string | null;
  last_sync: string | null;
};

const PLATFORMS = ["youtube", "tiktok", "instagram", "linkedin"];

function IntegrationsContent() {
  const { token } = useAuth();
  const searchParams = useSearchParams();
  const focusPlatform = (searchParams.get("platform") || "").toLowerCase();

  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchIntegrations();
  }, [token]);

  async function fetchIntegrations() {
    try {
      const response = await fetch("/api/v1/integrations", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        throw new Error("Failed to load integrations");
      }
      const data = await response.json();
      setIntegrations(data.integrations || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations");
    }
  }

  async function connectPlatform(platform: string) {
    try {
      // Phase 1: Native OAuth standard flow for primary channels
      if (platform === "tiktok" || platform === "youtube") {
        window.location.href = `/api/v1/oauth/${platform}/authorize`;
        return;
      }

      // Legacy fallback flow
      const response = await fetch(`/api/v1/integrations/${platform}/connect`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || `Connect flow unavailable for ${platform}`);
      }

      const data = await response.json();
      if (data.url) {
        window.location.href = data.url;
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect platform");
    }
  }

  return (
    <main className="page">
      <div className="brand" style={{ marginBottom: 32 }}>
        <div className="brand-mark">
          <div className="brand-dot" style={{ background: "linear-gradient(135deg, #4facfe, #00f2fe)" }} />
          Integrations
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 20 }}>
        <h2 style={{ marginBottom: 8 }}>Connected Accounts</h2>
        <p style={{ color: "var(--muted)", fontSize: 13 }}>
          Connect publishing accounts here. Publish, autopilot, and billing flows all read from the same integrations state.
        </p>
      </div>

      {error && (
        <div className="alert" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gap: 16 }}>
        {PLATFORMS.map((platform) => {
          const integration = integrations.find((item) => item.platform === platform);
          const isFocused = focusPlatform === platform;

          return (
            <div
              key={platform}
              className="panel"
              style={{
                border: isFocused ? "1px solid var(--accent)" : "1px solid var(--line)",
                boxShadow: isFocused ? "0 0 0 1px rgba(255,111,97,0.15)" : undefined,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center" }}>
                <div>
                  <div style={{ fontWeight: 700, textTransform: "capitalize" }}>{platform}</div>
                  <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 4 }}>
                    {integration
                      ? integration.account_name || "Connected"
                      : "Not connected"}
                  </div>
                  {integration?.last_error ? (
                    <div style={{ fontSize: 12, color: "#ff6666", marginTop: 4 }}>
                      Last error: {integration.last_error}
                    </div>
                  ) : null}
                </div>

                <button
                  className="button"
                  onClick={() => connectPlatform(platform)}
                  style={{ padding: "8px 14px", fontSize: 13 }}
                >
                  {integration ? "Reconnect" : "Connect"}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </main>
  );
}

export default function IntegrationsPage() {
  return (
    <Suspense fallback={<div className="page">Loading integrations...</div>}>
      <IntegrationsContent />
    </Suspense>
  );
}
