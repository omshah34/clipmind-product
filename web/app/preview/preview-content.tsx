/**
 * File: app/preview/page.tsx
 * Purpose: Preview Studio - In-browser caption editing and rendering.
 *          Users can edit captions, style them, and render final clips.
 *          Includes HTML5 video and Canvas overlay for live preview.
 */

"use client";

import { useState, useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/components/auth-provider";

interface RenderJob {
  render_job_id: string;
  job_id: string;
  clip_index: number;
  status: "queued" | "processing" | "completed" | "failed";
  progress_percent: number;
  output_url?: string;
  error_message?: string;
}

const CaptionStyleOptions = {
  fonts: ["Arial", "Helvetica", "Verdana", "Georgia", "Courier"],
  colors: [
    { name: "White", hex: "#FFFFFF" },
    { name: "Yellow", hex: "#FFFF00" },
    { name: "Accent", hex: "#FF6F61" },
    { name: "Gray", hex: "#CCCCCC" },
  ],
  backgrounds: [
    { name: "None", value: "none" },
    { name: "Black", value: "black" },
    { name: "Transparent", value: "transparent" },
    { name: "Gradient", value: "gradient" },
  ],
};

function parseSrt(srtText: string) {
  if (!srtText) return [];
  const blocks = srtText.trim().split(/\n\s*\n/);
  return blocks.map(block => {
    const lines = block.split('\n');
    if (lines.length < 3) return null;
    const timeRe = /(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})/;
    const match = lines[1].match(timeRe);
    if (!match) return null;

    function toSeconds(h: string, m: string, s: string, ms: string) {
      return parseInt(h) * 3600 + parseInt(m) * 60 + parseInt(s) + parseInt(ms) / 1000;
    }

    return {
      start: toSeconds(match[1], match[2], match[3], match[4]),
      end: toSeconds(match[5], match[6], match[7], match[8]),
      text: lines.slice(2).join('\n')
    };
  }).filter(Boolean);
}

export default function PreviewContent() {
  const searchParams = useSearchParams();
  const { user, token } = useAuth();

  const jobId = searchParams.get("job") || "";
  const clipIndex = parseInt(searchParams.get("clip") || "0");

  const [clipUrl, setClipUrl] = useState<string>("");
  const [captions, setCaptions] = useState<string>("");
  const [captionStyle, setCaptionStyle] = useState({
    font: "Arial",
    color: "#FFFFFF",
    background: "none",
    fontSize: 24,
  });

  const [renderJob, setRenderJob] = useState<RenderJob | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [renderError, setRenderError] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Fetch initial preview data
  useEffect(() => {
    if (!jobId || !token) return;
    fetch(`/api/v1/preview/${jobId}/${clipIndex}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) {
          setClipUrl(data.clip_url || data.clipUrl || "");
          if (data.current_srt || data.currentSrt) {
            setCaptions(data.current_srt || data.currentSrt);
          } else {
            // Placeholder SRT if none fetched
            setCaptions(
              "1\n00:00:00,000 --> 00:00:05,000\n[No Captions Found]"
            );
          }
        }
      })
      .catch(console.error);
  }, [jobId, clipIndex, token]);

  // Live caption canvas overlay loop
  useEffect(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;

    const renderCaptions = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const srtData = parseSrt(captions);
      if (!srtData || srtData.length === 0) {
        animationFrameId = requestAnimationFrame(renderCaptions);
        return;
      }

      const currentTime = video.currentTime;
      const activeCaption = srtData.find(c => c && currentTime >= c.start && currentTime <= c.end);

      if (activeCaption && activeCaption.text) {
        ctx.font = `bold ${captionStyle.fontSize}px ${captionStyle.font}`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';

        const lines = activeCaption.text.split('\n');
        const lineHeight = captionStyle.fontSize * 1.2;
        const startY = canvas.height - 100 - ((lines.length - 1) * lineHeight / 2);

        lines.forEach((line, i) => {
          const y = startY + (i * lineHeight);

          // Background drawing
          if (captionStyle.background !== 'none' && captionStyle.background !== 'transparent') {
            ctx.fillStyle = captionStyle.background === 'black' ? 'rgba(0,0,0,0.7)' : captionStyle.background;
            const textMetrics = ctx.measureText(line);
            const padding = 10;
            ctx.fillRect(
              (canvas.width / 2) - (textMetrics.width / 2) - padding,
              y - (captionStyle.fontSize / 2) - padding,
              textMetrics.width + (padding * 2),
              captionStyle.fontSize + (padding * 2)
            );
          } else {
            // Text Outline / Stroke for readability
            ctx.lineWidth = 4;
            ctx.strokeStyle = '#000000';
            ctx.strokeText(line, canvas.width / 2, y);
          }

          // Text Fill
          ctx.fillStyle = captionStyle.color;
          ctx.fillText(line, canvas.width / 2, y);
        });
      }

      animationFrameId = requestAnimationFrame(renderCaptions);
    };

    const handlePlay = () => {
      animationFrameId = requestAnimationFrame(renderCaptions);
    };

    video.addEventListener('play', handlePlay);
    video.addEventListener('timeupdate', renderCaptions); // Ensure it catches updates while scrubbing

    return () => {
      video.removeEventListener('play', handlePlay);
      video.removeEventListener('timeupdate', renderCaptions);
      cancelAnimationFrame(animationFrameId);
    };
  }, [captions, captionStyle]);

  // Fetch render job status and handle WebSocket streaming
  useEffect(() => {
    if (!renderJob?.render_job_id || !user) return;
    
    let ws: WebSocket;
    
    const connectWebsocket = () => {
        // Upgrade connection to WSS based on current origin
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws/jobs/${user.id}`;
        
        ws = new WebSocket(wsUrl);
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                // Listen for render_job events directed at this ID
                if (data.render_job_id === renderJob.render_job_id) {
                    setRenderJob(data);
                    
                    if (data.status === "completed" || data.status === "failed") {
                        setIsRendering(false);
                        if (data.status === "completed" && data.output_url) {
                            setClipUrl(data.output_url);
                        }
                    }
                }
            } catch (err) {
                console.error("Format error from WebSocket", err);
            }
        };
        
        ws.onclose = () => {
            // Primitive Reconnect strategy if rendering isn't done
            setTimeout(connectWebsocket, 3000);
        };
    };
    
    connectWebsocket();

    return () => {
        if (ws) {
            ws.onclose = null; // Prevent reconnect Loop when unmounting
            ws.close();
        }
    };
  }, [renderJob?.render_job_id, user]);

  const handleRender = async () => {
    if (!captions.trim()) {
      setRenderError("Please enter captions before rendering");
      return;
    }

    setIsRendering(true);
    setRenderError(null);

    try {
      const response = await fetch(
        `/api/v1/preview/${jobId}/${clipIndex}/render`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            edited_srt: captions,
            caption_style: captionStyle,
          }),
        }
      );

      if (!response.ok) {
        throw new Error("Render request failed");
      }

      const data = await response.json();
      setRenderJob(data);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Render failed. Please try again.";
      setRenderError(message);
      setIsRendering(false);
    }
  };

  return (
    <div className="page">
      <div className="brand" style={{ marginBottom: 32 }}>
        <div className="brand-mark">
          <div className="brand-dot" style={{ background: "linear-gradient(135deg, #87ceeb, #4a90e2)" }} />
          Preview Studio
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        {/* Left side: Video preview */}
        <div className="panel">
          <h2>Video Preview (Live Canvas)</h2>
          <div
            style={{
              position: "relative",
              backgroundColor: "#111",
              borderRadius: 12,
              minHeight: 320,
              width: "100%",
              overflow: "hidden",
              marginBottom: 16,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {clipUrl ? (
              <>
                <video
                  ref={videoRef}
                  src={clipUrl}
                  controls
                  crossOrigin="anonymous"
                  style={{
                    width: "100%",
                    display: "block",
                    borderRadius: 12
                  }}
                />
                <canvas
                  ref={canvasRef}
                  width={640} // Scaled for higher resolution text rendering
                  height={1138} // 9:16 vertical ratio overlay
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: "100%",
                    pointerEvents: "none",
                    objectFit: "contain"
                  }}
                />
              </>
            ) : (
              <div style={{ color: "var(--muted)", fontSize: 14 }}>
                Loading Video Player...
              </div>
            )}
          </div>
          {renderJob?.output_url && (
            <div
              style={{
                padding: 12,
                backgroundColor: "rgba(0, 255, 0, 0.1)",
                border: "1px solid #00AA00",
                borderRadius: 8,
                fontSize: 13,
                marginTop: 12,
              }}
            >
              ✓ Rendered clip ready: <a href={renderJob.output_url} target="_blank" rel="noopener noreferrer" style={{ color: "#00FF00", fontWeight: "bold" }}>Download</a>
            </div>
          )}
        </div>

        {/* Right side: Caption editor */}
        <div className="panel">
          <h2>Caption Editor</h2>
          <label className="field" style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8, fontSize: 13, color: "var(--muted)" }}>
              SRT Format Captions (Edit here to see live updates!)
            </div>
            <textarea
              value={captions}
              onChange={(e) => setCaptions(e.target.value)}
              placeholder="1&#10;00:00:00,000 --&gt; 00:00:05,000&#10;Your caption here&#10;&#10;2&#10;00:00:05,000 --&gt; 00:00:10,000&#10;Next caption..."
              style={{
                width: "100%",
                minHeight: 200,
                padding: 12,
                backgroundColor: "rgba(0, 0, 0, 0.3)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                color: "var(--text)",
                fontFamily: "monospace",
                fontSize: 12,
              }}
              disabled={isRendering}
            />
          </label>

          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 12, fontSize: 13, fontWeight: 600 }}>
              Caption Style
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
              <label className="field">
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>Font</div>
                <select
                  value={captionStyle.font}
                  onChange={(e) => setCaptionStyle({ ...captionStyle, font: e.target.value })}
                  style={{
                    width: "100%",
                    padding: 8,
                    backgroundColor: "rgba(0, 0, 0, 0.3)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    color: "var(--text)",
                  }}
                  disabled={isRendering}
                >
                  {CaptionStyleOptions.fonts.map((font) => (
                    <option key={font} value={font}>
                      {font}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>Color</div>
                <select
                  value={captionStyle.color}
                  onChange={(e) => setCaptionStyle({ ...captionStyle, color: e.target.value })}
                  style={{
                    width: "100%",
                    padding: 8,
                    backgroundColor: "rgba(0, 0, 0, 0.3)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    color: "var(--text)",
                  }}
                  disabled={isRendering}
                >
                  {CaptionStyleOptions.colors.map((c) => (
                    <option key={c.hex} value={c.hex}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>Background</div>
                <select
                  value={captionStyle.background}
                  onChange={(e) => setCaptionStyle({ ...captionStyle, background: e.target.value })}
                  style={{
                    width: "100%",
                    padding: 8,
                    backgroundColor: "rgba(0, 0, 0, 0.3)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    color: "var(--text)",
                  }}
                  disabled={isRendering}
                >
                  {CaptionStyleOptions.backgrounds.map((bg) => (
                    <option key={bg.value} value={bg.value}>
                      {bg.name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="field">
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 6 }}>Font Size</div>
                <input
                  type="number"
                  value={captionStyle.fontSize}
                  onChange={(e) =>
                    setCaptionStyle({ ...captionStyle, fontSize: parseInt(e.target.value) })
                  }
                  min="16"
                  max="72"
                  style={{
                    width: "100%",
                    padding: 8,
                    backgroundColor: "rgba(0, 0, 0, 0.3)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    color: "var(--text)",
                  }}
                  disabled={isRendering}
                />
              </label>
            </div>
          </div>

          {renderError && (
            <div
              style={{
                padding: 12,
                backgroundColor: "rgba(255, 0, 0, 0.1)",
                border: "1px solid #AA0000",
                borderRadius: 8,
                fontSize: 12,
                color: "#FF6666",
                marginBottom: 12,
              }}
            >
              {renderError}
            </div>
          )}

          {renderJob && (
            <div style={{ marginBottom: 12, fontSize: 12 }}>
              <div style={{ marginBottom: 6, color: "var(--muted)" }}>
                Status: <strong>{renderJob.status.toUpperCase()}</strong>
              </div>
              <div
                style={{
                  height: 4,
                  backgroundColor: "rgba(0, 0, 0, 0.3)",
                  borderRadius: 2,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${renderJob.progress_percent}%`,
                    backgroundColor: "var(--accent)",
                    transition: "width 0.3s ease",
                  }}
                />
              </div>
              <div style={{ marginTop: 6, color: "var(--muted)", fontSize: 11 }}>
                {renderJob.progress_percent}%
              </div>
            </div>
          )}

          <button
            onClick={handleRender}
            disabled={isRendering || !captions.trim()}
            style={{
              width: "100%",
              padding: 12,
              borderRadius: 8,
              border: "1px solid var(--accent)",
              backgroundColor: "rgba(255, 111, 97, 0.2)",
              color: "var(--accent)",
              fontWeight: 600,
              cursor: isRendering ? "not-allowed" : "pointer",
              opacity: isRendering || !captions.trim() ? 0.5 : 1,
            }}
          >
            {isRendering ? "Rendering Server Side..." : "Render Final Clip"}
          </button>
        </div>
      </div>
    </div>
  );
}

