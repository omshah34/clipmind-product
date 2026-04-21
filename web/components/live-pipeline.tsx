"use client";

/**
 * File: web/components/live-pipeline.tsx
 * Purpose: Real-time pipeline visualisation — connects via WebSocket and shows
 *          animated stage progress, live scores, and a completion celebration.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";

// ─── Types ───────────────────────────────────────────────────────────────────

interface PipelineEvent {
  type: string;
  job_id: string;
  data: Record<string, any>;
  timestamp: number;
}

interface ClipScore {
  clip_index: number;
  scores: Record<string, number>;
  reason: string;
}

interface ReadyClip {
  clip_index: number;
  duration: number;
  final_score: number;
}

// ─── Pipeline Stages ─────────────────────────────────────────────────────────

const STAGES = [
  { key: "downloading",      label: "Downloading Video",   icon: "⬇️",  color: "#4f46e5" },
  { key: "extracting_audio", label: "Extracting Audio",    icon: "🎵",  color: "#7c3aed" },
  { key: "transcribing",     label: "Transcribing",        icon: "📝",  color: "#8b5cf6" },
  { key: "detecting_clips",  label: "Detecting Clips",     icon: "🧠",  color: "#c026d3" },
  { key: "cutting_clip",     label: "Cutting Clips",       icon: "✂️", color: "#db2777" },
  { key: "captioning_clip",  label: "Burning Captions",    icon: "💬",  color: "#ef4444" },
  { key: "exporting_clip",   label: "Exporting",           icon: "📤",  color: "#f97316" },
  { key: "completed",        label: "Complete",            icon: "🎉",  color: "#16a34a" },
];

// ─── Component ───────────────────────────────────────────────────────────────

interface LivePipelineProps {
  jobId: string;
  initialData?: any;
  onCompleted?: () => void;
}

export default function LivePipeline({ jobId, initialData, onCompleted }: LivePipelineProps) {
  const [currentStage, setCurrentStage] = useState<string>("queued");
  const [progress, setProgress] = useState(0);
  const [clipScores, setClipScores] = useState<ClipScore[]>([]);
  const [readyClips, setReadyClips] = useState<ReadyClip[]>([]);
  const [completionData, setCompletionData] = useState<Record<string, any> | null>(null);
  const [errorData, setErrorData] = useState<{ stage: string; message: string } | null>(null);
  const [extraInfo, setExtraInfo] = useState<Record<string, any>>({});
  const [connected, setConnected] = useState(false);
  const lastMessageTime = useRef<number>(Date.now());
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = `${protocol}://${window.location.hostname}:8000/api/v1/ws/jobs/${jobId}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (evt) => {
      lastMessageTime.current = Date.now();
      try {
        const event: PipelineEvent = JSON.parse(evt.data);
        if (event.type === "pong") return;

        const data = event.data || {};

        switch (event.type) {
          case "stage_change":
            setCurrentStage(data.stage || "");
            if (data.progress) setProgress(data.progress);
            setExtraInfo((prev) => ({ ...prev, ...data }));
            break;

          case "progress":
            if (data.stage) setCurrentStage(data.stage);
            if (data.progress) setProgress(data.progress);
            setExtraInfo((prev) => ({ ...prev, ...data }));
            break;

          case "clip_scored":
            setClipScores((prev) => {
              const exists = prev.find((c) => c.clip_index === data.clip_index);
              if (exists) return prev;
              return [...prev, { clip_index: data.clip_index, scores: data.scores, reason: data.reason }];
            });
            break;

          case "clip_ready":
            setReadyClips((prev) => {
              const exists = prev.find((c) => c.clip_index === data.clip_index);
              if (exists) return prev;
              return [...prev, { clip_index: data.clip_index, duration: data.duration, final_score: data.final_score }];
            });
            break;

          case "completed":
            setCurrentStage("completed");
            setProgress(100);
            setCompletionData(data);
            onCompleted?.();
            break;

          case "error":
            setErrorData({ stage: data.stage, message: data.message });
            break;
        }
      } catch {
        // Ignore parse errors
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Auto-reconnect after 3 seconds if not completed
      if (currentStage !== "completed") {
        reconnectTimer.current = setTimeout(connect, 3000);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [jobId, currentStage, onCompleted]);

  useEffect(() => {
    connect();
    // Ping keepalive every 15 seconds
    const pingInterval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
      
      // Fallback logic: if no message for 15s and we have initialData, sync from it
      const secondsSinceLastMessage = (Date.now() - lastMessageTime.current) / 1000;
      if (secondsSinceLastMessage > 15 && initialData) {
        if (initialData.status && initialData.status !== currentStage) {
          setCurrentStage(initialData.status);
          // Map status to progress if not provided
          const statusProgress: Record<string, number> = {
            uploading: 10, transcribing: 40, detecting_clips: 60, completed: 100
          };
          if (statusProgress[initialData.status]) setProgress(statusProgress[initialData.status]);
        }
      }
    }, 15000);

    return () => {
      clearInterval(pingInterval);
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect, initialData, currentStage]);

  // Sync with initialData on mount or if WebSocket is down
  useEffect(() => {
    if (!connected && initialData?.status) {
      setCurrentStage(initialData.status);
    }
  }, [initialData, connected]);

  const activeStageIndex = STAGES.findIndex((s) => s.key === currentStage);
  const isComplete = currentStage === "completed";
  const hasError = !!errorData;

  return (
    <div style={{ fontFamily: "'Space Grotesk', sans-serif", color: "var(--text)" }}>
      {/* Connection indicator */}
      <div style={{
        display: "inline-flex", alignItems: "center", gap: 8,
        marginBottom: 18, fontSize: 12, color: "var(--muted)",
        padding: "8px 12px",
        borderRadius: 999,
        background: "rgba(255,255,255,0.82)",
        border: "1px solid rgba(16,32,51,0.08)",
      }}>
        <span style={{
          width: 8, height: 8, borderRadius: "50%",
          backgroundColor: connected ? "#22c55e" : "#ef4444",
          boxShadow: connected ? "0 0 8px rgba(34,197,94,0.35)" : "0 0 8px rgba(239,68,68,0.3)",
        }} />
        {connected ? "Live • Real-time updates" : "Reconnecting..."}
      </div>

      {/* Progress bar */}
      <div style={{
        height: 8, backgroundColor: "rgba(16,32,51,0.08)",
        borderRadius: 999, overflow: "hidden", marginBottom: 24,
      }}>
        <div style={{
          height: "100%", width: `${progress}%`,
          background: hasError
            ? "linear-gradient(90deg, #ef4444, #f97316)"
            : isComplete
              ? "linear-gradient(90deg, #16a34a, #22c55e)"
              : "linear-gradient(90deg, #4f46e5, #8b5cf6, #db2777)",
          transition: "width 0.6s ease-out",
          borderRadius: 999,
        }} />
      </div>

      {/* Stage indicators */}
      <div style={{
        display: "grid", gridTemplateColumns: `repeat(${STAGES.length}, 1fr)`,
        gap: 4, marginBottom: 24,
      }}>
        {STAGES.map((stage, i) => {
          const isPast = i < activeStageIndex;
          const isActive = stage.key === currentStage;
          const isFuture = i > activeStageIndex && !isComplete;

          return (
            <div key={stage.key} style={{
              textAlign: "center", opacity: isFuture ? 0.3 : 1,
              transition: "opacity 0.3s ease",
            }}>
              <div style={{
                width: 36, height: 36, borderRadius: "50%",
                margin: "0 auto 6px",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 16,
                background: isPast || isComplete
                  ? `${stage.color}18`
                  : isActive
                    ? `${stage.color}18`
                    : "rgba(255,255,255,0.95)",
                border: isActive ? `2px solid ${stage.color}` : "1px solid rgba(16,32,51,0.08)",
                animation: isActive ? "pulse 2s infinite" : "none",
                transition: "all 0.3s ease",
                boxShadow: isActive ? `0 10px 24px ${stage.color}18` : "0 8px 18px rgba(16,32,51,0.04)",
              }}>
                {isPast || isComplete ? "✓" : stage.icon}
              </div>
              <div style={{
                fontSize: 10, color: isActive ? stage.color : "var(--muted)",
                fontWeight: isActive ? 700 : 400,
                lineHeight: 1.2,
              }}>
                {stage.label}
              </div>
            </div>
          );
        })}
      </div>

      {/* Current stage detail */}
      {!isComplete && !hasError && currentStage !== "queued" && (
        <div style={{
          padding: 16, borderRadius: 12,
          backgroundColor: "rgba(79, 70, 229, 0.07)",
          border: "1px solid rgba(79, 70, 229, 0.18)",
          marginBottom: 20,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>
            {STAGES.find((s) => s.key === currentStage)?.icon}{" "}
            {STAGES.find((s) => s.key === currentStage)?.label || currentStage}
            <span style={{
              marginLeft: 8, fontSize: 12, color: "var(--muted)",
              animation: "pulse 1.5s infinite",
            }}>
              Processing...
            </span>
          </div>

          {extraInfo.words && (
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              📊 Transcribed {extraInfo.words.toLocaleString()} words
            </div>
          )}
          {extraInfo.candidates_found && (
            <div style={{ fontSize: 12, color: "#7c3aed" }}>
              🎯 Found {extraInfo.candidates_found} clip candidates
            </div>
          )}
          {extraInfo.clip_index !== undefined && extraInfo.total_clips && (
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              ✂️ Processing clip {extraInfo.clip_index + 1} of {extraInfo.total_clips}
            </div>
          )}
        </div>
      )}

      {/* Clip scores as they come in */}
      {clipScores.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 12, color: "#7c3aed" }}>
            🧠 AI Scoring Results
          </h3>
          <div style={{ display: "grid", gap: 8 }}>
            {clipScores.map((cs) => (
              <div key={cs.clip_index} style={{
                padding: 12, borderRadius: 10,
                backgroundColor: "rgba(255,255,255,0.92)",
                border: "1px solid rgba(16,32,51,0.08)",
                animation: "fadeSlideIn 0.4s ease-out",
                boxShadow: "0 10px 24px rgba(16, 32, 51, 0.04)",
              }}>
                <div style={{
                  display: "flex", justifyContent: "space-between",
                  alignItems: "center", marginBottom: 8,
                }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>
                    Clip {cs.clip_index + 1}
                  </span>
                  {cs.reason && (
                    <span style={{ fontSize: 11, color: "var(--muted)", maxWidth: "60%", textAlign: "right" }}>
                      {cs.reason.substring(0, 80)}{cs.reason.length > 80 ? "..." : ""}
                    </span>
                  )}
                </div>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  {Object.entries(cs.scores).map(([key, val]) => {
                    const label = key.replace("_score", "");
                    const numVal = Number(val) || 0;
                    const colors: Record<string, string> = {
                      hook: "#ef4444", emotion: "#14b8a6",
                      clarity: "#0ea5e9", story: "#f97316", virality: "#eab308",
                    };
                    return (
                      <div key={key} style={{
                        padding: "3px 8px", borderRadius: 6,
                        backgroundColor: `${colors[label] || "#999"}15`,
                        border: `1px solid ${colors[label] || "#999"}33`,
                        fontSize: 11, fontWeight: 600,
                        color: colors[label] || "#999",
                      }}>
                        {label}: {numVal.toFixed(1)}
                      </div>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Ready clips */}
      {readyClips.length > 0 && !isComplete && (
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 8, color: "#16a34a" }}>
            ✅ Clips Ready
          </h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {readyClips.map((rc) => (
              <div key={rc.clip_index} style={{
                padding: "6px 12px", borderRadius: 8,
                backgroundColor: "rgba(34, 197, 94, 0.08)",
                border: "1px solid rgba(34, 197, 94, 0.16)",
                fontSize: 12, fontWeight: 600, color: "#22c55e",
              }}>
                Clip {rc.clip_index + 1} • {Math.round(rc.duration)}s • Score: {rc.final_score.toFixed(1)}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Completion celebration */}
      {isComplete && completionData && (
        <div style={{
          padding: 24, borderRadius: 16, textAlign: "center",
          background: "linear-gradient(135deg, rgba(34,197,94,0.08), rgba(74,222,128,0.04))",
          border: "1px solid rgba(34, 197, 94, 0.22)",
          animation: "fadeSlideIn 0.5s ease-out",
        }}>
          <div style={{ fontSize: 48, marginBottom: 12 }}>🎉</div>
          <h2 style={{ fontSize: 22, fontWeight: 800, marginBottom: 8, color: "#22c55e" }}>
            Clips Ready!
          </h2>
          <div style={{
            display: "flex", justifyContent: "center", gap: 24,
            marginBottom: 12,
          }}>
            <div>
              <div style={{ fontSize: 28, fontWeight: 800, color: "var(--text)" }}>
                {completionData.total_clips}
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>Clips Generated</div>
            </div>
            <div>
              <div style={{ fontSize: 28, fontWeight: 800, color: "#d97706" }}>
                {(completionData.best_score || 0).toFixed(1)}
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>Best Score</div>
            </div>
            <div>
              <div style={{ fontSize: 28, fontWeight: 800, color: "#7c3aed" }}>
                {Math.round(completionData.processing_time_seconds || 0)}s
              </div>
              <div style={{ fontSize: 11, color: "var(--muted)" }}>Processing Time</div>
            </div>
          </div>
        </div>
      )}

      {/* Error */}
      {hasError && errorData && (
        <div style={{
          padding: 16, borderRadius: 12,
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          border: "1px solid rgba(239, 68, 68, 0.3)",
        }}>
          <div style={{ fontWeight: 700, color: "#ef4444", marginBottom: 6 }}>
            ❌ Error at {errorData.stage}
          </div>
          <div style={{ fontSize: 13, color: "#fca5a5" }}>
            {errorData.message}
          </div>
        </div>
      )}

      {/* Animations */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        @keyframes fadeSlideIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
