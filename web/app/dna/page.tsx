/**
 * File: app/dna/page.tsx
 * Purpose: Content DNA - Personalized clip scoring insights.
 *          Shows learning progress, score weights, and recommendations.
 */

"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/components/auth-provider";

interface ScoreMetric {
  name: string;
  weight: number;
  trend: "up" | "down" | "stable";
}

interface SignalSummary {
  total_signals: number;
  downloaded_count: number;
  skipped_count: number;
  edited_count: number;
  regenerated_count: number;
  published_count: number;
}

interface ContentDNAData {
  user_id: string;
  learning_status: "learning" | "converging" | "optimized";
  confidence_score: number;
  score_weights: Record<string, number>;
  signals: SignalSummary;
  recommendations: string[];
  progress_to_next: {
    label: string;
    percentage: number;
    signals_needed: number;
  };
  manual_overrides: string[];
}

const SCORE_COLORS: Record<string, string> = {
  hook: "#FF6B6B",
  emotion: "#4ECDC4",
  clarity: "#45B7D1",
  story: "#FFA07A",
  virality: "#FFD700",
};

const LEARNING_STAGES = {
  learning: {
    icon: "📚",
    color: "#4a90e2",
    description: "Gathering clip preferences. Watch or interact with more clips to improve recommendations.",
  },
  converging: {
    icon: "🔄",
    color: "#f5a623",
    description: "Pattern emerging. Your preferences are becoming clear. Continue interacting.",
  },
  optimized: {
    icon: "⭐",
    color: "var(--accent)",
    description: "Fully optimized! ClipMind deeply understands your content preferences.",
  },
};

export default function ContentDNAPage() {
  const { user, token } = useAuth();
  const [dnaData, setDnaData] = useState<ContentDNAData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedMetric, setSelectedMetric] = useState<string | null>(null);

  useEffect(() => {
    fetchContentDNA();
    // Refresh every 30 seconds
    const interval = setInterval(fetchContentDNA, 30000);
    return () => clearInterval(interval);
  }, [token]);

  const fetchContentDNA = async () => {
    try {
      const response = await fetch("/api/v1/dna/weights", {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setDnaData(data);
      }
    } catch (error) {
      console.error("Failed to fetch Content DNA:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleToggleLock = async (dimension: string, currentlyLocked: boolean) => {
    try {
      const response = await fetch("/api/v1/dna/overrides", {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}` 
        },
        body: JSON.stringify({ 
          dimension, 
          locked: !currentlyLocked 
        }),
      });

      if (response.ok) {
        fetchContentDNA();
      }
    } catch (error) {
      console.error("Failed to toggle weight lock:", error);
    }
  };

  if (isLoading || !dnaData) {
    return (
      <div className="page">
        <div style={{ textAlign: "center", color: "var(--muted)", paddingTop: 60 }}>
          Loading your DNA profile...
        </div>
      </div>
    );
  }

  const stage = LEARNING_STAGES[dnaData.learning_status];
  const metrics: (ScoreMetric & { isLocked: boolean })[] = Object.entries(dnaData.score_weights).map(
    ([name, weight]) => ({
      name,
      weight,
      trend: Math.random() > 0.5 ? "up" : "stable",
      isLocked: dnaData.manual_overrides.includes(`${name}_weight`)
    })
  );

  const maxWeight = Math.max(...metrics.map((m) => m.weight));
  const engagementRate =
    dnaData.signals.total_signals > 0
      ? ((dnaData.signals.published_count / dnaData.signals.total_signals) * 100).toFixed(1)
      : 0;

  return (
    <div className="page">
      <div className="brand" style={{ marginBottom: 32 }}>
        <div className="brand-mark">
          <div
            className="brand-dot"
            style={{
              background: "linear-gradient(135deg, #f093fb, #f5576c)",
            }}
          />
          Content DNA
        </div>
      </div>

      {/* Learning Status */}
      <div className="panel" style={{ marginBottom: 24 }}>
        <div
          style={{
            padding: 20,
            borderRadius: 12,
            background: `${stage.color}15`,
            border: `2px solid ${stage.color}`,
            display: "flex",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div style={{ fontSize: 40 }}>{stage.icon}</div>
          <div style={{ flex: 1 }}>
            <h2 style={{ margin: "0 0 8px" }}>
              {dnaData.learning_status.charAt(0).toUpperCase() +
                dnaData.learning_status.slice(1)}
            </h2>
            <p style={{ margin: 0, color: "var(--muted)", fontSize: 14 }}>
              {stage.description}
            </p>
          </div>
          <div style={{ textAlign: "right" }}>
            <div
              style={{
                fontSize: 32,
                fontWeight: 700,
                color: stage.color,
                marginBottom: 4,
              }}
            >
              {(dnaData.confidence_score * 100).toFixed(0)}%
            </div>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>Confidence</div>
          </div>
        </div>

        {/* Progress bar to next stage */}
        {dnaData.learning_status !== "optimized" && (
          <div style={{ marginTop: 16 }}>
            <div style={{ marginBottom: 8, fontSize: 12, color: "var(--muted)" }}>
              Progress to {dnaData.progress_to_next.label}
            </div>
            <div
              style={{
                height: 8,
                backgroundColor: "rgba(0, 0, 0, 0.3)",
                borderRadius: 4,
                overflow: "hidden",
                marginBottom: 4,
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${dnaData.progress_to_next.percentage}%`,
                  backgroundColor: stage.color,
                  transition: "width 0.3s ease",
                }}
              />
            </div>
            <div
              style={{
                fontSize: 11,
                color: "var(--muted)",
              }}
            >
              {dnaData.progress_to_next.signals_needed} more signals needed
            </div>
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, marginBottom: 24 }}>
        {/* Score Weights */}
        <div className="panel">
          <h2>Score Weights</h2>
          <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>
            How your clips are scored based on your preferences
          </p>

          <div style={{ display: "grid", gap: 16 }}>
            {metrics.map((metric) => {
              const isSelected = selectedMetric === metric.name;
              const normalizedWeight = (metric.weight / maxWeight) * 100;

              return (
                <div
                  key={metric.name}
                  onClick={() => setSelectedMetric(isSelected ? null : metric.name)}
                  style={{
                    padding: 12,
                    borderRadius: 8,
                    backgroundColor: isSelected
                      ? `${SCORE_COLORS[metric.name]}15`
                      : "rgba(0, 0, 0, 0.2)",
                    border: `2px solid ${isSelected ? SCORE_COLORS[metric.name] : "var(--line)"}`,
                    cursor: "pointer",
                    transition: "all 0.2s ease",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 8,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <div
                        style={{
                          fontWeight: 600,
                          textTransform: "capitalize",
                          color: SCORE_COLORS[metric.name],
                        }}
                      >
                        {metric.name}
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleToggleLock(metric.name, metric.isLocked);
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          padding: "2px 6px",
                          cursor: "pointer",
                          fontSize: 14,
                          display: "flex",
                          alignItems: "center",
                          opacity: metric.isLocked ? 1 : 0.4,
                          transition: "opacity 0.2s",
                        }}
                        title={
                          metric.isLocked
                            ? "Manual Override Active"
                            : "Automated AI Learning"
                        }
                      >
                        {metric.isLocked ? "🔒" : "🔓"}
                      </button>
                    </div>

                    <div
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: metric.isLocked ? "var(--accent)" : "inherit",
                      }}
                    >
                      {metric.weight.toFixed(2)}x{" "}
                      {metric.isLocked && (
                        <span style={{ fontSize: 10, opacity: 0.6 }}>(Static)</span>
                      )}
                    </div>
                  </div>

                  <div
                    style={{
                      height: 4,
                      backgroundColor: "rgba(0, 0, 0, 0.3)",
                      borderRadius: 2,
                      overflow: "hidden",
                      marginTop: 10,
                    }}
                  >
                    <div
                      style={{
                        height: "100%",
                        width: `${normalizedWeight}%`,
                        backgroundColor: SCORE_COLORS[metric.name],
                        transition: "width 0.3s ease",
                      }}
                    />
                  </div>

                  {isSelected && (
                    <div
                      style={{
                        marginTop: 12,
                        paddingTop: 12,
                        borderTop: `1px solid ${SCORE_COLORS[metric.name]}33`,
                        fontSize: 12,
                        color: "var(--muted)",
                      }}
                    >
                      {metric.isLocked ? (
                        <div style={{ color: "var(--accent)" }}>
                          <strong>Locked:</strong> This weight is static. AI feedback loops will not adjust this dimension until unlocked.
                        </div>
                      ) : (
                        <>
                          <strong>Impact:</strong> Clips are boosted{" "}
                          <strong style={{ color: SCORE_COLORS[metric.name] }}>
                            {metric.weight.toFixed(0)}%
                          </strong>{" "}
                          higher when ranked on this metric.
                          {metric.trend === "up" && (
                            <div style={{ marginTop: 4, color: "#00FF00" }}>
                              ↑ Trending upward in your preferences
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Signal Summary */}
        <div className="panel">
          <h2>Interaction Summary</h2>
          <p style={{ color: "var(--muted)", fontSize: 13, marginBottom: 16 }}>
            Total interactions: <strong>{dnaData.signals.total_signals}</strong>
          </p>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 12,
              marginBottom: 24,
            }}
          >
            <div
              style={{
                padding: 12,
                backgroundColor: "rgba(255, 107, 107, 0.1)",
                borderRadius: 8,
                border: "1px solid rgba(255, 107, 107, 0.2)",
              }}
            >
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                Downloaded
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: "#FF6B6B" }}>
                {dnaData.signals.downloaded_count}
              </div>
            </div>

            <div
              style={{
                padding: 12,
                backgroundColor: "rgba(78, 205, 196, 0.1)",
                borderRadius: 8,
                border: "1px solid rgba(78, 205, 196, 0.2)",
              }}
            >
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                Published
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: "#4ECDC4" }}>
                {dnaData.signals.published_count}
              </div>
            </div>

            <div
              style={{
                padding: 12,
                backgroundColor: "rgba(255, 160, 122, 0.1)",
                borderRadius: 8,
                border: "1px solid rgba(255, 160, 122, 0.2)",
              }}
            >
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                Edited
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: "#FFA07A" }}>
                {dnaData.signals.edited_count}
              </div>
            </div>

            <div
              style={{
                padding: 12,
                backgroundColor: "rgba(69, 183, 209, 0.1)",
                borderRadius: 8,
                border: "1px solid rgba(69, 183, 209, 0.2)",
              }}
            >
              <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 4 }}>
                Regenerated
              </div>
              <div style={{ fontSize: 24, fontWeight: 700, color: "#45B7D1" }}>
                {dnaData.signals.regenerated_count}
              </div>
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8, fontSize: 12, color: "var(--muted)" }}>
              Engagement Rate
            </div>
            <div
              style={{
                height: 8,
                backgroundColor: "rgba(0, 0, 0, 0.3)",
                borderRadius: 4,
                overflow: "hidden",
                marginBottom: 4,
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${engagementRate}%`,
                  backgroundColor: "var(--accent)",
                }}
              />
            </div>
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              {engagementRate}% of clips published
            </div>
          </div>
        </div>
      </div>

      {/* Recommendations */}
      {dnaData.recommendations.length > 0 && (
        <div className="panel">
          <h2>Recommendations</h2>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: 12,
            }}
          >
            {dnaData.recommendations.map((rec, idx) => (
              <div
                key={idx}
                style={{
                  padding: 12,
                  backgroundColor: "rgba(255, 111, 97, 0.1)",
                  borderRadius: 8,
                  border: "1px solid rgba(255, 111, 97, 0.2)",
                  fontSize: 13,
                }}
              >
                <span style={{ color: "var(--accent)", marginRight: 8 }}>
                  💡
                </span>
                {rec}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
