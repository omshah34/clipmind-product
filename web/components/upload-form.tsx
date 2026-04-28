/**
 * File: components/upload-form.tsx
 * Purpose: Upload form component. Handles video file selection, validation,
 *          and submission to backend /upload endpoint.
 *
 * Gap 240: Files ≥ 100 MB are automatically routed through the ETag-verified
 * chunked uploader (lib/chunked-uploader.ts) for resumability on flaky networks.
 * Smaller files continue to use the single-PUT direct upload path.
 */

"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

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

export default function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Fine-grained progress label shown only during chunked uploads. */
  const [chunkProgress, setChunkProgress] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!file) {
      setError("Please select a video file before generating clips.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    setChunkProgress(null);
    let directUploadSession: { job_id: string } | null = null;

    try {
      const uploadCapabilities = await getUploadCapabilities();

      // ── Gap 240: Route large files through the ETag-verified chunked uploader ──
      if (uploadCapabilities.multipart_upload && shouldUseChunkedUpload(file)) {
        try {
          const sourceVideoUrl = await uploadFileChunked(
            file,
            undefined, // no existing session — fresh upload
            ({ uploadedParts, totalParts, uploadedBytes, totalBytes }) => {
              const pct = Math.round((uploadedBytes / totalBytes) * 100);
              setChunkProgress(
                `Uploading part ${uploadedParts} / ${totalParts} (${pct}%)`
              );
            },
          );
          // sourceVideoUrl is the canonical URL returned by complete endpoint
          // Create the job via the standard form-based upload response shape
          router.push(`/jobs/new?source=${encodeURIComponent(sourceVideoUrl)}`);
          return;
        } catch (chunkedError) {
          const message = chunkedError instanceof Error ? chunkedError.message : "";
          if (!message.includes("Multipart upload requires cloud storage")) {
            throw chunkedError;
          }
          // If cloud storage isn't available, we fall through to standard upload
          setChunkProgress(null);
        }
      }

      // ── Standard direct upload (files < 100 MB) ──────────────────────────────
      const durationSeconds = await probeVideoDuration(file);

      if (uploadCapabilities.direct_upload) {
        try {
          const session = await initDirectUpload(file, durationSeconds);
          directUploadSession = { job_id: session.job_id };
          await uploadFileToSignedUrl(session.upload_url, file);
          await completeDirectUpload(session.job_id);
          router.push(`/jobs/${session.job_id}`);
          return;
        } catch (directUploadError) {
          const message =
            directUploadError instanceof Error ? directUploadError.message : "";
          if (directUploadSession) {
            await failDirectUpload(directUploadSession.job_id, message || "Direct upload failed.");
          }
          throw directUploadError;
        }
      }

      const response = await uploadVideo(file);
      router.push(`/jobs/${response.job_id}`);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Upload failed. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
      setChunkProgress(null);
    }
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>

      {/* ── How to use YouTube videos ────────────────────────────────────────── */}
      <div style={{
        marginBottom: 20,
        padding: "14px 16px",
        borderRadius: 12,
        border: "1px solid var(--line)",
        background: "rgba(255, 255, 255, 0.03)",
      }}>
        <div className="upload-label" style={{ marginBottom: 8 }}>
          📺 Using a YouTube video?
        </div>
        <p className="upload-copy" style={{ margin: 0, lineHeight: 1.6 }}>
          Download the video to your device first, then upload it below.
          You can use{" "}
          <a
            href="https://www.y2mate.com"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--accent, #a78bfa)", textDecoration: "underline" }}
          >
            y2mate.com
          </a>
          {" "}or{" "}
          <a
            href="https://yt1s.com"
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: "var(--accent, #a78bfa)", textDecoration: "underline" }}
          >
            yt1s.com
          </a>
          {" "}to save it as an MP4. ClipMind then turns it into viral shorts automatically.
        </p>
      </div>

      {/* ── File dropzone ─────────────────────────────────────────────────────── */}
      <label className="upload-dropzone">
        <input
          className="upload-input"
          accept=".mp4,.mov,video/mp4,video/quicktime"
          disabled={isSubmitting}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          type="file"
        />
        <div className="upload-dropzone-top">
          <div>
            <div className="upload-label">Source video</div>
            <h3 className="upload-title">Drop a file or browse from your computer</h3>
            <p className="upload-copy">
              MP4 or MOV, up to 2GB. ClipMind handles the rest and sends you to the job page.
            </p>
          </div>
          <span className="upload-browse">{file ? "Change file" : "Browse files"}</span>
        </div>
        <div className="upload-file">
          <strong>{file ? file.name : "No file selected yet"}</strong>
          {file ? <span>Ready to process</span> : <span>2 to 90 minutes recommended</span>}
        </div>
      </label>

      <div className="upload-row">
        <button className="button" disabled={isSubmitting} type="submit">
          {chunkProgress
            ? chunkProgress
            : isSubmitting
            ? "Uploading…"
            : "Generate clips"}
        </button>
        <span className="note">You'll be redirected as soon as processing starts.</span>
      </div>

      {error ? <div className="alert">{error}</div> : null}
    </form>
  );
}
