/**
 * File: components/job-status.tsx
 * Purpose: Job status component. Polls /jobs/{job_id}/status endpoint
 *          every 4 seconds and displays current processing stage.
 */

"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import ClipList from "./clip-list";
import LivePipeline from "./live-pipeline";
import { getJobStatus, JobStatusResponse } from "../lib/api";

const statusProgress: Record<string, number> = {
  uploading: 6,
  uploaded: 10,
  queued: 20,
  extracting_audio: 35,
  transcribing: 50,
  detecting_clips: 65,
  cutting_video: 78,
  rendering_captions: 88,
  exporting: 95,
  retrying: 55,
  completed: 100,
  failed: 100,
  cancelled: 100,
};

const statusLabel: Record<string, string> = {
  uploading: "Uploading video...",
  uploaded: "Upload complete",
  queued: "Queued for processing...",
  extracting_audio: "Extracting audio...",
  transcribing: "Transcribing speech...",
  detecting_clips: "Detecting best clips...",
  cutting_video: "Cutting video clips...",
  rendering_captions: "Rendering captions...",
  exporting: "Exporting clips...",
  retrying: "Retrying...",
  completed: "Done!",
  failed: "Failed",
  cancelled: "Cancelled",
};

function progressStyle(progress: number): React.CSSProperties & { "--progress"?: string } {
  return { "--progress": `${progress}%` } as React.CSSProperties & { "--progress"?: string };
}

export default function JobStatus({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [data, setData] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let intervalId: number | undefined;

    async function fetchStatus() {
      try {
        const response = await getJobStatus(jobId);
        if (cancelled) return;

        setData(response);
        setError(null);

        if (response.status === "completed" || response.status === "failed") {
          window.clearInterval(intervalId);

          // ── Auto-redirect to studio on completion ──────────────────────
          if (response.status === "completed") {
            setRedirecting(true);
            setTimeout(() => {
              router.push(`/jobs/${jobId}/studio`);
            }, 1500); // 1.5s so user sees "Done!" before navigating
          }
        }
      } catch (statusError) {
        if (!cancelled) {
          setError(
            statusError instanceof Error
              ? statusError.message
              : "Unable to load job status.",
          );
        }
      }
    }

    fetchStatus();
    intervalId = window.setInterval(fetchStatus, 4000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [jobId, router]);

  const progress = useMemo(() => {
    if (!data) return 8;
    return statusProgress[data.status] ?? 15;
  }, [data]);

  // ── Error state ──────────────────────────────────────────────────────────
  if (error) {
    return <div className="alert">{error}</div>;
  }

  // ── Loading state (first fetch not yet returned) ─────────────────────────
  if (!data) {
    return (
      <div className="stack">
        <div className="status-strip">
          <span>Loading status</span>
          <span>Contacting backend…</span>
        </div>
        <div className="progress" style={progressStyle(12)}>
          <span />
        </div>
      </div>
    );
  }

  // ── Failed state ─────────────────────────────────────────────────────────
  if (data.status === "failed") {
    return (
      <div className="stack">
        <div className="status-strip">
          <span>Job ID: {data.job_id}</span>
          <span style={{ color: "#f87171" }}>Status: failed</span>
        </div>
        <div className="progress" style={progressStyle(100)}>
          <span style={{ background: "#ef4444" }} />
        </div>
        {data.error_message && (
          <div className="alert">
            {data.failed_stage ? `${data.failed_stage}: ` : null}
            {data.error_message}
          </div>
        )}
        <a href="/" className="px-4 py-2 bg-gray-200 text-gray-900 rounded-lg hover:bg-gray-300 transition font-medium w-fit">
          Try another upload
        </a>
      </div>
    );
  }

  // ── Completed state ──────────────────────────────────────────────────────
  if (data.status === "completed") {
    return (
      <div className="stack">
        <div className="status-strip">
          <span>Job ID: {data.job_id}</span>
          <span style={{ color: "#4ade80" }}>✓ Completed</span>
        </div>
        <div className="progress" style={progressStyle(100)}>
          <span />
        </div>

        {redirecting ? (
          <p className="note">✅ Clips are ready! Taking you to the studio…</p>
        ) : (
          <>
            {/* Show clips inline if available */}
            {data.clips && data.clips.length > 0 && (
              <ClipList clips={data.clips} jobId={jobId} />
            )}

            {/* Manual navigation buttons if redirect hasn't fired */}
            <div className="flex gap-2 mt-6">
              <Link
                href={`/jobs/${jobId}/studio`}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition font-medium"
              >
                🎬 Open Studio
              </Link>
              <Link
                href={`/intelligence?job_id=${jobId}`}
                className="px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition font-medium"
              >
                📊 View Analytics
              </Link>
              <a
                href="/"
                className="px-4 py-2 bg-gray-200 text-gray-900 rounded-lg hover:bg-gray-300 transition font-medium"
              >
                Upload Another
              </a>
            </div>
          </>
        )}
      </div>
    );
  }

  // ── In-progress state — Live Pipeline Dashboard ──────────────────────────
  return (
    <div className="stack">
      <div className="status-strip">
        <span>Job ID: {data.job_id}</span>
        <span>Status: {data.status}</span>
      </div>

      {/* Live real-time pipeline visualization */}
      <LivePipeline
        jobId={jobId}
        initialData={data}
        onCompleted={() => {
          // Re-fetch status to get clips data
          getJobStatus(jobId).then(setData).catch(() => {});
        }}
      />

      <p className="note" style={{ marginTop: 16, fontSize: 12, opacity: 0.6 }}>
        ClipMind is working on your video in the background.
        This page updates in real-time via WebSocket.
      </p>
    </div>
  );
}
