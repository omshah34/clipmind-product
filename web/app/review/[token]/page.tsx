/**
 * File: app/review/[token]/page.tsx
 * Purpose: Public unauthenticated Client Portal Review link.
 *          Allows agencies (B2B) to send their clients a link to review AI clips.
 */

"use client";

import { useState } from "react";
import { useParams } from "next/navigation";

export default function ClientReviewPage() {
  const params = useParams();
  const token = params.token as string;

  const [status, setStatus] = useState<"idle" | "submitting" | "completed">("idle");
  const [feedback, setFeedback] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Note for Phase 1: We mock the video playback in this preview. 
  // In Phase 2, a GET endpoint would fetch the actual clips bound to this submission_token.
  const MOCK_CLIPS = [
    { title: "Hook A - Controversial Start", duration: "45s", url: "mock_video_url_1" },
  ];

  async function handleSubmitReview(action: "approved" | "changes_requested" | "rejected") {
    if (action === "changes_requested" && !feedback.trim()) {
      setError("Please provide feedback so the agency knows what to change.");
      return;
    }

    setStatus("submitting");
    setError(null);
    try {
      const res = await fetch(`/api/v1/workspaces/public/submissions/${token}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: action,
          client_feedback: feedback,
        }),
      });

      if (!res.ok) {
        const payload = await res.json().catch(() => null);
        throw new Error(payload?.detail || "Failed to submit review");
      }

      setStatus("completed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Submission error");
      setStatus("idle");
    }
  }

  if (status === "completed") {
    return (
      <main className="page" style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "80vh" }}>
        <div className="panel" style={{ textAlign: "center", maxWidth: 400 }}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>✅</div>
          <h2>Review Submitted</h2>
          <p style={{ color: "var(--muted)", fontSize: 14 }}>
            Thank you! Your feedback has been sent directly back to your agency's ClipMind dashboard.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="page" style={{ maxWidth: 900, margin: "0 auto", padding: "40px 20px" }}>
      <div className="brand" style={{ marginBottom: 40 }}>
        <div className="brand-mark">
          <div className="brand-dot" style={{ background: "linear-gradient(135deg, #10b981, #047857)" }} />
          Client Portal Review
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 350px", gap: 32 }}>
        
        {/* Left Column: Clip Preview (Mocked for Visual Layer) */}
        <div>
          <h2 style={{ marginBottom: 16 }}>Pending Content Review</h2>
          {MOCK_CLIPS.map((clip, idx) => (
            <div key={idx} className="panel" style={{ marginBottom: 16 }}>
              <div 
                style={{ 
                  backgroundColor: "rgba(0,0,0,0.5)", 
                  aspectRatio: "9/16", 
                  borderRadius: 12, 
                  display: "flex", 
                  alignItems: "center", 
                  justifyContent: "center",
                  backgroundImage: "linear-gradient(45deg, #2a2a2a, #1a1a1a)"
                }}
              >
                <div style={{ textAlign: "center", color: "var(--muted)" }}>
                  <div style={{ fontSize: 32, marginBottom: 8 }}>▶</div>
                  <div>Preview Video: {clip.title}</div>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Right Column: Feedback Controls */}
        <div>
          <div className="panel" style={{ position: "sticky", top: 20 }}>
            <h3 style={{ marginBottom: 16 }}>Feedback & Decision</h3>
            
            {error && (
              <div style={{ padding: 12, marginBottom: 16, border: "1px solid #AA0000", backgroundColor: "rgba(255, 0, 0, 0.1)", borderRadius: 8, fontSize: 12, color: "#FF6666" }}>
                {error}
              </div>
            )}

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: "block", marginBottom: 8, fontSize: 13, fontWeight: 600 }}>
                Leave comments for your Editor
              </label>
              <textarea
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Make the hook more aggressive..."
                style={{
                  width: "100%",
                  minHeight: 120,
                  padding: 12,
                  borderRadius: 8,
                  border: "1px solid var(--line)",
                  backgroundColor: "rgba(0, 0, 0, 0.2)",
                  color: "var(--text)",
                  resize: "vertical",
                }}
                disabled={status === "submitting"}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <button
                className="button"
                onClick={() => handleSubmitReview("approved")}
                disabled={status === "submitting"}
                style={{ backgroundColor: "#10b981", border: "none", color: "#fff", fontWeight: 700 }}
              >
                {status === "submitting" ? "Processing..." : "Approve & Schedule"}
              </button>

              <button
                className="button"
                onClick={() => handleSubmitReview("changes_requested")}
                disabled={status === "submitting"}
                style={{ backgroundColor: "rgba(255, 111, 97, 0.1)", border: "1px solid var(--accent)", color: "var(--accent)", fontWeight: 700 }}
              >
                Request AI Changes
              </button>
            </div>
            
            <div style={{ marginTop: 24, fontSize: 11, color: "var(--muted)", textAlign: "center" }}>
              Secure Client Workflow powered by ClipMind
            </div>
          </div>
        </div>

      </div>
    </main>
  );
}
