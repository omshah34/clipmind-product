/**
 * File: app/sequences/sequences-content.tsx
 * Purpose: Clip Sequences content component. Uses useSearchParams for job ID.
 *          Wrapped in Suspense in parent page component.
 */

"use client";

import { useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth-provider";

interface Clip {
  clip_id: string;
  clip_index: number;
  duration: number;
  title: string;
  thumbnail_url?: string;
  hook_score: number;
  virality_score: number;
}

interface ClipSequence {
  sequence_id: string;
  clips: Clip[];
  total_duration: number;
  cliffhanger_score: number;
  platform_optimizations: Record<
    string,
    {
      duration: number;
      recommendation: string;
    }
  >;
  created_at: string;
}

const PLATFORMS = [
  {
    id: "tiktok",
    name: "TikTok",
    icon: "♪",
    minDuration: 15,
    maxDuration: 60,
    color: "#000",
  },
  {
    id: "instagram",
    name: "Instagram",
    icon: "📷",
    minDuration: 10,
    maxDuration: 90,
    color: "#E4405F",
  },
  {
    id: "youtube",
    name: "YouTube",
    icon: "▶",
    minDuration: 30,
    maxDuration: 600,
    color: "#FF0000",
  },
  {
    id: "linkedin",
    name: "LinkedIn",
    icon: "in",
    minDuration: 15,
    maxDuration: 300,
    color: "#0A66C2",
  },
];

export default function SequencesContent() {
  const searchParams = useSearchParams();
  const { user, token } = useAuth();

  const jobId = searchParams.get("job") || "";
  const [sequences, setSequences] = useState<ClipSequence[]>([]);
  const [selectedSequence, setSelectedSequence] = useState<ClipSequence | null>(
    null
  );
  const [isLoading, setIsLoading] = useState(true);
  const [isPublishing, setIsPublishing] = useState(false);
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>([]);
  const [publishError, setPublishError] = useState<string | null>(null);

  useEffect(() => {
    if (jobId) {
      fetchSequences();
    }
  }, [jobId, token]);

  const fetchSequences = async () => {
    try {
      const response = await fetch(`/api/v1/sequences/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setSequences(data);
        if (data.length > 0) {
          setSelectedSequence(data[0]);
        }
      }
    } catch (error) {
      console.error("Failed to fetch sequences:", error);
    } finally {
      setIsLoading(false);
    }
  };

  const handlePublishSequence = async () => {
    if (!selectedSequence || selectedPlatforms.length === 0) {
      setPublishError("Select at least one platform");
      return;
    }

    setIsPublishing(true);
    setPublishError(null);

    try {
      const response = await fetch(
        `/api/v1/sequences/${selectedSequence.sequence_id}/publish`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            platforms: selectedPlatforms,
          }),
        }
      );

      if (!response.ok) throw new Error("Publish failed");

      // Success feedback
      setSelectedPlatforms([]);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Publish failed";
      setPublishError(message);
    } finally {
      setIsPublishing(false);
    }
  };

  const handleCancelSequence = async (sequenceId: string) => {
    try {
      await fetch(`/api/v1/sequences/${sequenceId}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      setSequences(sequences.filter((s) => s.sequence_id !== sequenceId));
      if (selectedSequence?.sequence_id === sequenceId) {
        setSelectedSequence(sequences[0] || null);
      }
    } catch (error) {
      console.error("Failed to cancel sequence:", error);
    }
  };

  const getPlatformFit = (sequence: ClipSequence, platformId: string) => {
    const platform = PLATFORMS.find((p) => p.id === platformId);
    const opt = sequence.platform_optimizations[platformId];

    if (!platform || !opt) return null;

    const isWithinRange =
      opt.duration >= platform.minDuration &&
      opt.duration <= platform.maxDuration;
    const status = isWithinRange ? "optimal" : "trim";

    return { platform, duration: opt.duration, status };
  };

  if (isLoading) {
    return (
      <div className="page">
        <div style={{ textAlign: "center", color: "var(--muted)", paddingTop: 60 }}>
          Loading sequences...
        </div>
      </div>
    );
  }

  if (sequences.length === 0) {
    return (
      <div className="page">
        <div className="brand" style={{ marginBottom: 32 }}>
          <div className="brand-mark">
            <div
              className="brand-dot"
              style={{
                background: "linear-gradient(135deg, #667eea, #764ba2)",
              }}
            />
            Clip Sequences
          </div>
        </div>
        <div className="panel" style={{ textAlign: "center" }}>
          <p style={{ color: "var(--muted)", marginBottom: 16 }}>
            No sequences detected yet
          </p>
          <button
            onClick={fetchSequences}
            style={{
              padding: "8px 16px",
              borderRadius: 6,
              border: "1px solid var(--accent)",
              backgroundColor: "rgba(255, 111, 97, 0.2)",
              color: "var(--accent)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Detect Sequences
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="brand" style={{ marginBottom: 32 }}>
        <div className="brand-mark">
          <div
            className="brand-dot"
            style={{
              background: "linear-gradient(135deg, #667eea, #764ba2)",
            }}
          />
          Clip Sequences
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: 24 }}>
        {/* Sequence List */}
        <div className="panel">
          <h3 style={{ margin: "0 0 16px" }}>Detected Sequences</h3>
          <div style={{ display: "grid", gap: 8 }}>
            {sequences.map((sequence, idx) => (
              <div
                key={sequence.sequence_id}
                onClick={() => setSelectedSequence(sequence)}
                style={{
                  padding: 12,
                  borderRadius: 8,
                  border:
                    selectedSequence?.sequence_id === sequence.sequence_id
                      ? "2px solid var(--accent)"
                      : "1px solid var(--line)",
                  backgroundColor:
                    selectedSequence?.sequence_id === sequence.sequence_id
                      ? "rgba(255, 111, 97, 0.1)"
                      : "rgba(0, 0, 0, 0.2)",
                  cursor: "pointer",
                  transition: "all 0.2s",
                }}
              >
                <div
                  style={{
                    fontWeight: 700,
                    marginBottom: 4,
                    fontSize: 13,
                  }}
                >
                  Series {idx + 1}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: "var(--muted)",
                    marginBottom: 6,
                  }}
                >
                  {sequence.clips.length} clips •{" "}
                  {Math.floor(sequence.total_duration)}s
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 10,
                    color: "var(--muted)",
                  }}
                >
                  <span>⚡ {(sequence.cliffhanger_score * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Sequence Details */}
        {selectedSequence && (
          <div>
            <div className="panel" style={{ marginBottom: 24 }}>
              <h2>Series Overview</h2>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 12,
                  marginBottom: 16,
                }}
              >
                <div
                  style={{
                    padding: 12,
                    backgroundColor: "rgba(255, 111, 97, 0.1)",
                    borderRadius: 8,
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>
                    Total Clips
                  </div>
                  <div
                    style={{
                      fontSize: 24,
                      fontWeight: 700,
                      color: "var(--accent)",
                    }}
                  >
                    {selectedSequence.clips.length}
                  </div>
                </div>

                <div
                  style={{
                    padding: 12,
                    backgroundColor: "rgba(78, 205, 196, 0.1)",
                    borderRadius: 8,
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>
                    Total Duration
                  </div>
                  <div
                    style={{
                      fontSize: 24,
                      fontWeight: 700,
                      color: "#4ECDC4",
                    }}
                  >
                    {Math.floor(selectedSequence.total_duration)}s
                  </div>
                </div>

                <div
                  style={{
                    padding: 12,
                    backgroundColor: "rgba(255, 215, 0, 0.1)",
                    borderRadius: 8,
                    textAlign: "center",
                  }}
                >
                  <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>
                    Cliffhanger Score
                  </div>
                  <div
                    style={{
                      fontSize: 24,
                      fontWeight: 700,
                      color: "#FFD700",
                    }}
                  >
                    {(selectedSequence.cliffhanger_score * 100).toFixed(0)}%
                  </div>
                </div>
              </div>

              <h3 style={{ margin: "16px 0 12px", fontSize: 16 }}>Clips in Sequence</h3>
              <div style={{ display: "grid", gap: 8 }}>
                {selectedSequence.clips.map((clip) => (
                  <div
                    key={clip.clip_id}
                    style={{
                      display: "grid",
                      gridTemplateColumns: "60px 1fr",
                      gap: 12,
                      padding: 10,
                      backgroundColor: "rgba(0, 0, 0, 0.2)",
                      borderRadius: 6,
                      border: "1px solid var(--line)",
                    }}
                  >
                    <div
                      style={{
                        width: 60,
                        height: 45,
                        backgroundColor: "rgba(0, 0, 0, 0.4)",
                        borderRadius: 4,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 10,
                        color: "var(--muted)",
                      }}
                    >
                      {clip.duration}s
                    </div>
                    <div>
                      <div style={{ fontWeight: 600, marginBottom: 2, fontSize: 13 }}>
                        Clip {clip.clip_index + 1}
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--muted)",
                          display: "flex",
                          gap: 8,
                        }}
                      >
                        <span>🎯 Hook: {(clip.hook_score * 100).toFixed(0)}%</span>
                        <span>⚡ Virality: {(clip.virality_score * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Platform Optimization */}
            <div className="panel" style={{ marginBottom: 24 }}>
              <h2>Platform Optimization</h2>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                  gap: 12,
                }}
              >
                {PLATFORMS.map((platform) => {
                  const fit = getPlatformFit(selectedSequence, platform.id);
                  if (!fit) return null;

                  const isSelected = selectedPlatforms.includes(platform.id);

                  return (
                    <div
                      key={platform.id}
                      onClick={() => {
                        setSelectedPlatforms((prev) =>
                          prev.includes(platform.id)
                            ? prev.filter((p) => p !== platform.id)
                            : [...prev, platform.id]
                        );
                      }}
                      style={{
                        padding: 12,
                        borderRadius: 8,
                        border: isSelected
                          ? `2px solid ${platform.color}`
                          : "1px solid var(--line)",
                        backgroundColor: isSelected
                          ? `${platform.color}15`
                          : "rgba(0, 0, 0, 0.2)",
                        cursor: "pointer",
                        transition: "all 0.2s",
                      }}
                    >
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                          marginBottom: 8,
                        }}
                      >
                        <span style={{ fontSize: 18 }}>{platform.icon}</span>
                        <strong>{platform.name}</strong>
                      </div>

                      <div
                        style={{
                          fontSize: 12,
                          marginBottom: 6,
                          color: "var(--muted)",
                        }}
                      >
                        Duration: <strong>{fit.duration}s</strong>
                      </div>

                      <div
                        style={{
                          fontSize: 11,
                          padding: 6,
                          borderRadius: 4,
                          backgroundColor:
                            fit.status === "optimal"
                              ? "rgba(0, 255, 0, 0.1)"
                              : "rgba(255, 215, 0, 0.1)",
                          color:
                            fit.status === "optimal"
                              ? "#00FF00"
                              : "#FFD700",
                        }}
                      >
                        {fit.status === "optimal"
                          ? "✓ Optimal for platform"
                          : "⚠ May need trimming"}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Publish */}
            <div className="panel">
              {publishError && (
                <div
                  style={{
                    padding: 12,
                    marginBottom: 16,
                    backgroundColor: "rgba(255, 0, 0, 0.1)",
                    border: "1px solid #AA0000",
                    borderRadius: 8,
                    fontSize: 12,
                    color: "#FF6666",
                  }}
                >
                  {publishError}
                </div>
              )}

              <button
                onClick={handlePublishSequence}
                disabled={
                  isPublishing || selectedPlatforms.length === 0
                }
                style={{
                  width: "100%",
                  padding: 12,
                  marginBottom: 8,
                  borderRadius: 8,
                  border: "1px solid var(--accent)",
                  backgroundColor: "rgba(255, 111, 97, 0.2)",
                  color: "var(--accent)",
                  fontWeight: 600,
                  cursor: isPublishing ? "not-allowed" : "pointer",
                  opacity: isPublishing || selectedPlatforms.length === 0 ? 0.5 : 1,
                }}
              >
                {isPublishing ? "Publishing..." : "Publish to Selected Platforms"}
              </button>

              <button
                onClick={() =>
                  handleCancelSequence(selectedSequence.sequence_id)
                }
                style={{
                  width: "100%",
                  padding: 12,
                  borderRadius: 8,
                  border: "1px solid rgba(200, 0, 0, 0.3)",
                  backgroundColor: "rgba(200, 0, 0, 0.1)",
                  color: "#FF6666",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Delete Sequence
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
