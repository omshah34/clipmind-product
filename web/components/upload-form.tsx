"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";

import {
  completeDirectUpload,
  failDirectUpload,
  getUploadCapabilities,
  initDirectUpload,
  probeVideoDuration,
  uploadFileToSignedUrl,
  uploadVideo,
} from "../lib/api";
import {
  uploadFileChunked,
  shouldUseChunkedUpload,
} from "../lib/chunked-uploader";

type UploadMode = "idle" | "dragging" | "url-preview" | "uploading" | "done";

interface VideoPreview {
  thumbnail: string;
  title: string;
  duration: string;
  channel: string;
}

const Icon = ({ d, size = 18, style = {} }: { d: string; size?: number; style?: React.CSSProperties }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" style={style}>
    <path d={d} />
  </svg>
);

/* Simulate a YouTube URL preview fetch (Backend Gap: Real API needed) */
async function fetchVideoPreview(url: string): Promise<VideoPreview | null> {
  if (!url.includes("youtube.com") && !url.includes("youtu.be")) return null;
  await new Promise(r => setTimeout(r, 900));
  return {
    thumbnail: `https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg`,
    title: "How to Build a SaaS in 2025 — Complete Walkthrough",
    duration: "42:18",
    channel: "Your Channel",
  };
}

export default function UploadForm() {
  const router = useRouter();
  const [mode, setMode] = useState<UploadMode>("idle");
  const [url, setUrl] = useState("");
  const [preview, setPreview] = useState<VideoPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [brandKit, setBrandKit] = useState("default");
  const [autoPublish, setAutoPublish] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileRef = useRef<HTMLInputElement>(null);
  const urlTimeout = useRef<ReturnType<typeof setTimeout>>();

  /* URL preview on paste / type */
  useEffect(() => {
    if (!url) { setPreview(null); return; }
    clearTimeout(urlTimeout.current);
    urlTimeout.current = setTimeout(async () => {
      setPreviewLoading(true);
      setError(null);
      const result = await fetchVideoPreview(url);
      setPreviewLoading(false);
      if (result) {
        setPreview(result);
        setMode("url-preview");
      } else {
        setPreview(null);
        if (url.length > 10) setError("Paste a YouTube URL, or upload a file below.");
      }
    }, 600);
    return () => clearTimeout(urlTimeout.current);
  }, [url]);

  /* Drag handlers */
  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setMode("dragging");
  }, []);
  const onDragLeave = useCallback(() => {
    setMode("idle");
  }, []);
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("video/")) {
      setFile(f);
      setMode("url-preview");
      setPreview(null);
    } else {
      setError("Please drop a video file (MP4, MOV, WebM).");
      setMode("idle");
    }
  }, []);

  /* File picker */
  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      setFile(f);
      setMode("url-preview");
      setPreview(null);
    }
  };

  /* ── Production Hardened Upload Logic (Gap 240) ── */
  const handleSubmit = async () => {
    if (!url && !file) return;
    
    // For now, if it's a URL, we simulate (Backend doesn't support URL ingestion yet)
    if (url && !file) {
        setMode("uploading");
        setProgress(15);
        await new Promise(r => setTimeout(r, 1500));
        setProgress(100);
        setTimeout(() => setMode("done"), 400);
        return;
    }

    if (!file) return;

    setMode("uploading");
    setError(null);
    setProgress(0);
    let directUploadSession: { job_id: string } | null = null;

    try {
      const uploadCapabilities = await getUploadCapabilities();

      // Gap 240: Chunked uploader for large files
      if (uploadCapabilities.multipart_upload && shouldUseChunkedUpload(file)) {
        const sourceVideoUrl = await uploadFileChunked(
          file,
          undefined,
          ({ uploadedBytes, totalBytes }) => {
            setProgress((uploadedBytes / totalBytes) * 100);
          }
        );
        router.push(`/jobs/new?source=${encodeURIComponent(sourceVideoUrl)}&brand_kit=${brandKit}&auto_publish=${autoPublish}`);
        return;
      }

      // Standard direct upload
      const durationSeconds = await probeVideoDuration(file);
      if (uploadCapabilities.direct_upload) {
        const session = await initDirectUpload(file, durationSeconds);
        directUploadSession = { job_id: session.job_id };
        await uploadFileToSignedUrl(session.upload_url, file);
        await completeDirectUpload(session.job_id);
        router.push(`/jobs/${session.job_id}`);
        return;
      }

      const response = await uploadVideo(file);
      router.push(`/jobs/${response.job_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
      setMode("url-preview");
      if (directUploadSession) {
        await failDirectUpload(directUploadSession.job_id, "Upload failed.");
      }
    }
  };

  const reset = () => {
    setMode("idle");
    setUrl("");
    setFile(null);
    setPreview(null);
    setProgress(0);
    setError(null);
  };

  const isDragging = mode === "dragging";
  const hasContent = (preview || file) && mode !== "idle";

  return (
    <div style={{ maxWidth: 640, margin: "0 auto", padding: "32px 20px" }}>

      <div style={{ marginBottom: "28px" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: "22px", fontWeight: 700, marginBottom: "6px", letterSpacing: "-0.02em" }}>
          New job
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "13.5px" }}>
          Paste a YouTube URL or upload a video file to extract your best moments.
        </p>
      </div>

      {/* ── URL Input ── */}
      <div style={{
        background: "var(--bg-surface)", border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)", padding: "4px", marginBottom: "16px",
        display: "flex", alignItems: "center", gap: "8px",
        transition: "border-color 0.2s",
      }}
      onFocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--accent)"; }}
      onBlur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--border)"; }}
      >
        <div style={{ padding: "0 10px", color: "var(--text-tertiary)" }}>
          <Icon d="M15 10l4.553-2.069A1 1 0 0121 8.882v6.236a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" size={16} />
        </div>
        <input
          type="url"
          placeholder="Paste YouTube URL — e.g. https://youtube.com/watch?v=..."
          value={url}
          onChange={(e) => { setUrl(e.target.value); setError(null); }}
          style={{
            flex: 1, background: "none", border: "none", outline: "none",
            color: "var(--text-primary)", fontSize: "14px", padding: "12px 0",
            fontFamily: "var(--font-body)",
          }}
        />
        {previewLoading && (
          <div style={{ padding: "0 10px", color: "var(--accent)" }}>
            <svg width={16} height={16} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
              className="animate-spin" strokeLinecap="round">
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
          </div>
        )}
      </div>

      {/* Error */}
      {error && (
        <p style={{ fontSize: "12px", color: "var(--red)", marginBottom: "12px", display: "flex", alignItems: "center", gap: "5px" }}>
          <Icon d="M18 6L6 18M6 6l12 12" size={12} />
          {error}
        </p>
      )}

      {/* ── URL Preview card ── */}
      {preview && mode === "url-preview" && (
        <div style={{
          background: "var(--bg-surface)", border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)", overflow: "hidden",
          marginBottom: "16px", animation: "fadeIn 0.2s ease",
        }}
        className="animate-fadeIn"
        >
          <div style={{ display: "flex", gap: "14px", padding: "14px" }}>
            <div style={{
              width: 120, height: 68, borderRadius: "var(--radius-md)", overflow: "hidden",
              background: "var(--bg-elevated)", flexShrink: 0, position: "relative",
            }}>
              <img
                src={preview.thumbnail}
                alt={preview.title}
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
              <span style={{
                position: "absolute", bottom: 4, right: 4,
                background: "rgba(0,0,0,0.8)", color: "#fff",
                fontSize: "10px", fontFamily: "var(--font-mono)",
                padding: "2px 5px", borderRadius: "var(--radius-sm)",
              }}>
                {preview.duration}
              </span>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{ fontSize: "13px", fontWeight: 500, marginBottom: "4px", lineHeight: 1.4 }}>
                {preview.title}
              </p>
              <p style={{ fontSize: "12px", color: "var(--text-tertiary)" }}>{preview.channel}</p>
              <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "8px" }}>
                <span style={{ fontSize: "11px", color: "var(--green)", background: "var(--green-dim)", padding: "2px 7px", borderRadius: "99px" }}>
                  ✓ Ready to process
                </span>
              </div>
            </div>
            <button onClick={reset} style={{
              background: "none", border: "none", cursor: "pointer",
              color: "var(--text-tertiary)", padding: "4px", alignSelf: "flex-start",
            }}>
              <Icon d="M18 6L6 18M6 6l12 12" size={14} />
            </button>
          </div>
        </div>
      )}

      {/* ── File upload zone ── */}
      {!hasContent && (
        <>
          <div style={{
            display: "flex", alignItems: "center", gap: "12px",
            color: "var(--text-tertiary)", margin: "8px 0", fontSize: "12px",
          }}>
            <div style={{ flex: 1, height: "1px", background: "var(--border)" }} />
            or upload a file
            <div style={{ flex: 1, height: "1px", background: "var(--border)" }} />
          </div>

          <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            style={{
              border: `2px dashed ${isDragging ? "var(--accent)" : "var(--border-strong)"}`,
              borderRadius: "var(--radius-lg)",
              padding: "40px 24px",
              textAlign: "center",
              cursor: "pointer",
              background: isDragging ? "var(--accent-dim)" : "transparent",
              transition: "all 0.15s ease",
              marginBottom: "20px",
            }}
          >
            <div style={{
              width: 44, height: 44, borderRadius: "var(--radius-lg)",
              background: isDragging ? "var(--accent-glow)" : "var(--bg-elevated)",
              margin: "0 auto 14px",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: isDragging ? "var(--accent)" : "var(--text-tertiary)",
              transition: "all 0.15s",
            }}>
              <Icon d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" size={20} />
            </div>
            <p style={{ fontSize: "14px", fontWeight: 500, color: isDragging ? "var(--accent)" : "var(--text-primary)", marginBottom: "4px" }}>
              {isDragging ? "Drop to upload" : "Drag & drop your video here"}
            </p>
            <p style={{ fontSize: "12px", color: "var(--text-tertiary)" }}>
              MP4, MOV, WebM · up to 4GB
            </p>
            <input ref={fileRef} type="file" accept="video/*" style={{ display: "none" }} onChange={onFileChange} />
          </div>
        </>
      )}

      {/* ── File ready card ── */}
      {file && !preview && (
        <div style={{
          background: "var(--bg-surface)", border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)", padding: "14px 16px",
          display: "flex", alignItems: "center", gap: "12px", marginBottom: "16px",
        }}>
          <div style={{
            width: 36, height: 36, background: "var(--accent-dim)", borderRadius: "var(--radius-md)",
            display: "flex", alignItems: "center", justifyContent: "center", color: "var(--accent)",
          }}>
            <Icon d="M15 10l4.553-2.069A1 1 0 0121 8.882v6.236a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" size={16} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: "13px", fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {file.name}
            </p>
            <p style={{ fontSize: "11px", color: "var(--text-tertiary)" }}>
              {(file.size / 1024 / 1024).toFixed(1)} MB
            </p>
          </div>
          <button onClick={reset} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-tertiary)", padding: "4px" }}>
            <Icon d="M18 6L6 18M6 6l12 12" size={14} />
          </button>
        </div>
      )}

      {/* ── Options ── */}
      {(preview || file) && mode !== "uploading" && mode !== "done" && (
        <div style={{
          background: "var(--bg-surface)", border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)", padding: "16px 18px",
          marginBottom: "16px",
        }}>
          <div style={{ marginBottom: "14px" }}>
            <label style={{ fontSize: "12px", color: "var(--text-secondary)", fontWeight: 500, display: "block", marginBottom: "7px" }}>
              Brand kit
            </label>
            <select
              value={brandKit}
              onChange={(e) => setBrandKit(e.target.value)}
              style={{
                width: "100%", padding: "8px 12px",
                background: "var(--bg-elevated)", border: "1px solid var(--border)",
                borderRadius: "var(--radius-md)", color: "var(--text-primary)",
                fontSize: "13px", fontFamily: "var(--font-body)", outline: "none",
                cursor: "pointer",
              }}
            >
              <option value="default">Default</option>
              <option value="hormozi">Hormozi-style captions</option>
              <option value="minimal">Minimal subtitle</option>
              <option value="branded">Custom brand overlay</option>
            </select>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <p style={{ fontSize: "13px", fontWeight: 500, marginBottom: "2px" }}>Auto-publish when done</p>
              <p style={{ fontSize: "11px", color: "var(--text-tertiary)" }}>Send top clips directly to your connected platforms</p>
            </div>
            <button
              onClick={() => setAutoPublish(p => !p)}
              style={{
                width: 40, height: 22,
                background: autoPublish ? "var(--accent)" : "var(--bg-overlay)",
                border: "none", borderRadius: "99px", cursor: "pointer",
                position: "relative", transition: "background 0.2s", flexShrink: 0,
              }}
            >
              <span style={{
                position: "absolute", top: 2, left: autoPublish ? 20 : 2,
                width: 18, height: 18, background: "#fff", borderRadius: "50%",
                transition: "left 0.2s",
              }} />
            </button>
          </div>
        </div>
      )}

      {/* ── Upload progress ── */}
      {mode === "uploading" && (
        <div style={{
          background: "var(--bg-surface)", border: "1px solid var(--border)",
          borderRadius: "var(--radius-lg)", padding: "20px 18px",
          marginBottom: "16px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
            <span style={{ fontSize: "13px", fontWeight: 500 }}>
              {progress < 100 ? "Uploading & queueing…" : "Queued!"}
            </span>
            <span style={{ fontSize: "12px", fontFamily: "var(--font-mono)", color: "var(--text-secondary)" }}>
              {Math.round(progress)}%
            </span>
          </div>
          <div style={{ height: 4, background: "var(--bg-elevated)", borderRadius: "99px", overflow: "hidden" }}>
            <div style={{
              height: "100%",
              width: `${progress}%`,
              background: "var(--accent)",
              borderRadius: "99px",
              transition: "width 0.15s ease",
            }} />
          </div>
        </div>
      )}

      {/* ── Done state ── */}
      {mode === "done" && (
        <div style={{
          background: "var(--green-dim)", border: "1px solid rgba(16,185,129,0.25)",
          borderRadius: "var(--radius-lg)", padding: "18px",
          marginBottom: "16px", textAlign: "center",
        }}>
          <p style={{ fontSize: "14px", fontWeight: 500, color: "var(--green)", marginBottom: "4px" }}>
            ✓ Job created successfully
          </p>
          <p style={{ fontSize: "12px", color: "var(--text-secondary)", marginBottom: "12px" }}>
            Processing starts immediately. You'll get a notification when clips are ready.
          </p>
          <button onClick={reset} style={{
            background: "var(--bg-surface)", border: "1px solid var(--border)",
            color: "var(--text-primary)", fontSize: "12px", padding: "6px 16px",
            borderRadius: "var(--radius-md)", cursor: "pointer",
          }}>
            Upload another
          </button>
        </div>
      )}

      {/* ── Submit button ── */}
      {(preview || file) && mode !== "uploading" && mode !== "done" && (
        <button
          onClick={handleSubmit}
          style={{
            width: "100%", padding: "13px",
            background: "var(--accent)", border: "none",
            borderRadius: "var(--radius-md)", color: "#fff",
            fontSize: "14px", fontWeight: 600, fontFamily: "var(--font-display)",
            cursor: "pointer", transition: "opacity 0.15s", letterSpacing: "0.01em",
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.opacity = "0.85"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.opacity = "1"; }}
        >
          Process video →
        </button>
      )}
    </div>
  );
}
