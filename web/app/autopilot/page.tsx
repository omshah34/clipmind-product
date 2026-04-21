/**
 * File: app/autopilot/page.tsx
 * Purpose: Autopilot Dashboard - Manage automated ingestion and publishing.
 */

"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/components/auth-provider";

interface Source {
  id: string;
  name: string;
  source_type: string;
  is_active: boolean;
  last_polled_at: string | null;
}

interface QueueItem {
  id: string;
  job_id: string;
  clip_index: number;
  platform: string;
  status: string;
  scheduled_for: string;
}

export default function AutopilotPage() {
  const { token } = useAuth();
  const [sources, setSources] = useState<Source[]>([]);
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isAutoEnabled, setIsAutoEnabled] = useState(true);

  useEffect(() => {
    fetchData();
  }, [token]);

  const fetchData = async () => {
    try {
      const [sourcesRes, queueRes] = await Promise.all([
        fetch("/api/v1/autopilot/sources", {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch("/api/v1/autopilot/queue", {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      if (sourcesRes.ok) {
        const data = await sourcesRes.json();
        setSources(data.sources);
      }
      if (queueRes.ok) {
        const data = await queueRes.json();
        setQueue(data.queue);
      }
    } catch (error) {
      console.error("Failed to fetch autopilot data:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddSource = async () => {
    const channelUrl = prompt("Enter YouTube Channel URL:");
    if (!channelUrl) return;

    try {
      const response = await fetch("/api/v1/autopilot/sources", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          name: channelUrl.split("/").pop() || "YouTube Channel",
          source_type: "youtube_channel",
          config_json: { channel_url: channelUrl },
        }),
      });

      if (response.ok) {
        fetchData();
      }
    } catch (error) {
      console.error("Failed to add source:", error);
    }
  };

  if (isLoading) {
    return (
      <div className="page" style={{ textAlign: "center", paddingTop: 100 }}>
        Loading Autopilot...
      </div>
    );
  }

  return (
    <div className="page">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 32 }}>
        <div className="brand">
          <div className="brand-mark">
            <div className="brand-dot" style={{ background: "linear-gradient(135deg, #00f2fe, #4facfe)" }} />
            Clip Autopilot
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 13, color: "var(--muted)" }}>
            System Status: 
            <strong style={{ color: isAutoEnabled ? "#00ff00" : "#ff4500", marginLeft: 4 }}>
              {isAutoEnabled ? "ACTIVE" : "PAUSED"}
            </strong>
          </span>
          <button 
            className="button" 
            onClick={() => setIsAutoEnabled(!isAutoEnabled)}
            style={{ padding: "8px 16px", fontSize: 13 }}
          >
            {isAutoEnabled ? "Pause Automation" : "Resume Automation"}
          </button>
        </div>
      </div>

      {/* Hero Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 20, marginBottom: 32 }}>
        <div className="panel" style={{ textAlign: "center", padding: "24px 16px" }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: "var(--accent)" }}>{sources.length}</div>
          <div style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 1 }}>Active Sources</div>
        </div>
        <div className="panel" style={{ textAlign: "center", padding: "24px 16px" }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: "#f093fb" }}>{queue.length}</div>
          <div style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 1 }}>In Queue</div>
        </div>
        <div className="panel" style={{ textAlign: "center", padding: "24px 16px" }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: "#5eead4" }}>124</div>
          <div style={{ fontSize: 12, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 1 }}>Total Published</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.5fr", gap: 24 }}>
        {/* Connected Sources */}
        <div className="panel">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <h2 style={{ margin: 0 }}>Connected Channels</h2>
            <button 
              className="button" 
              style={{ padding: "6px 12px", fontSize: 12, background: "rgba(255,255,255,0.1)" }}
              onClick={handleAddSource}
            >
              + Link Channel
            </button>
          </div>

          {sources.length === 0 ? (
            <div style={{ padding: 40, textAlign: "center", color: "var(--muted)", background: "rgba(0,0,0,0.2)", borderRadius: 12 }}>
              No channels linked yet.
            </div>
          ) : (
            <div style={{ display: "grid", gap: 12 }}>
              {sources.map(source => (
                <div key={source.id} style={{ 
                  padding: 16, 
                  background: "rgba(255,255,255,0.05)", 
                  borderRadius: 12,
                  border: "1px solid var(--line)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center"
                }}>
                  <div>
                    <div style={{ fontWeight: 600 }}>{source.name}</div>
                    <div style={{ fontSize: 11, color: "var(--muted)" }}>
                      Type: {source.source_type} • Last polled: {source.last_polled_at ? new Date(source.last_polled_at).toLocaleTimeString() : "Never"}
                    </div>
                  </div>
                  <div style={{ 
                    width: 10, 
                    height: 10, 
                    borderRadius: "50%", 
                    background: source.is_active ? "#00ff00" : "#555",
                    boxShadow: source.is_active ? "0 0 10px #00ff00" : "none"
                  }} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Publication Queue */}
        <div className="panel">
          <h2 style={{ marginBottom: 20 }}>Upcoming Schedule</h2>
          {queue.length === 0 ? (
            <div style={{ padding: 60, textAlign: "center", color: "var(--muted)", background: "rgba(0,0,0,0.2)", borderRadius: 12 }}>
              Nothing scheduled yet. Autopilot is scanning for new content.
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ textAlign: "left", fontSize: 12, color: "var(--muted)", borderBottom: "1px solid var(--line)" }}>
                  <th style={{ padding: "12px 0" }}>CLIP</th>
                  <th>PLATFORM</th>
                  <th>STATUS</th>
                  <th>SCHEDULED FOR</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {queue.map(item => (
                  <tr key={item.id} style={{ borderBottom: "1px solid var(--line)", fontSize: 13 }}>
                    <td style={{ padding: "16px 0" }}>
                      <strong>Job #{item.job_id.slice(-4)}</strong>
                      <div style={{ fontSize: 11, color: "var(--muted)" }}>Clip {item.clip_index}</div>
                    </td>
                    <td style={{ textTransform: "capitalize" }}>{item.platform}</td>
                    <td>
                      <span style={{ 
                        padding: "4px 8px", 
                        borderRadius: 20, 
                        fontSize: 10, 
                        fontWeight: 700,
                        background: item.status === "pending" ? "rgba(240, 147, 251, 0.2)" : "rgba(0, 255, 0, 0.1)",
                        color: item.status === "pending" ? "#f093fb" : "#00ff00"
                      }}>
                        {item.status.toUpperCase()}
                      </span>
                    </td>
                    <td>{new Date(item.scheduled_for).toLocaleString()}</td>
                    <td style={{ textAlign: "right" }}>
                      <button style={{ background: "none", border: "none", color: "#ff4500", cursor: "pointer", fontSize: 12 }}>Cancel</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
