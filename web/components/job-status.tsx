"use client";

import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";

import ClipList from "./clip-list";
import { getJobStatus, JobStatusResponse } from "../lib/api";


const statusProgress: Record<string, number> = {
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


function progressStyle(progress: number): CSSProperties {
  return { ["--progress" as "--progress"]: `${progress}%` };
}


export default function JobStatus({ jobId }: { jobId: string }) {
  const [data, setData] = useState<JobStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let intervalId: number | undefined;

    async function fetchStatus() {
      try {
        const response = await getJobStatus(jobId);
        if (cancelled) {
          return;
        }
        setData(response);
        setError(null);
        if (response.status === "completed" || response.status === "failed") {
          if (intervalId) {
            window.clearInterval(intervalId);
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
      if (intervalId) {
        window.clearInterval(intervalId);
      }
    };
  }, [jobId]);

  const progress = useMemo(() => {
    if (!data) {
      return 8;
    }
    return statusProgress[data.status] ?? 15;
  }, [data]);

  if (error) {
    return <div className="alert">{error}</div>;
  }

  if (!data) {
    return (
      <div className="stack">
        <div className="status-strip">
          <span>Loading status</span>
          <span>Contacting backend</span>
        </div>
        <div className="progress" style={progressStyle(12)}>
          <span />
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="status-strip">
        <span>Job ID: {data.job_id}</span>
        <span>Status: {data.status}</span>
      </div>

      <div className="progress" style={progressStyle(progress)}>
        <span />
      </div>

      {data.error_message ? (
        <div className="alert">
          {data.failed_stage ? `${data.failed_stage}: ` : null}
          {data.error_message}
        </div>
      ) : null}

      {data.status === "completed" && data.clips ? (
        <ClipList clips={data.clips} />
      ) : (
        <p className="note">
          ClipMind is processing the source video in the background. This page keeps polling
          until the clips are ready.
        </p>
      )}
    </div>
  );
}
