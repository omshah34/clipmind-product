/**
 * File: components/upload-form.tsx
 * Purpose: Upload form component. Handles video file selection, validation,
 *          and submission to backend /upload endpoint.
 */

"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import {
  completeDirectUpload,
  failDirectUpload,
  initDirectUpload,
  probeVideoDuration,
  uploadFileToSignedUrl,
  uploadVideoFromUrl,
  uploadVideo,
} from "../lib/api";


export default function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedUrl = videoUrl.trim();
    if (!file && !trimmedUrl) {
      setError("Choose a file or paste a YouTube link before starting the job.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
      if (trimmedUrl) {
        const response = await uploadVideoFromUrl(trimmedUrl);
        router.push(`/jobs/${response.job_id}`);
        return;
      }

      if (!file) {
        throw new Error("Choose a valid video file.");
      }

      const durationSeconds = await probeVideoDuration(file);

      try {
        const session = await initDirectUpload(file, durationSeconds);
        router.push(`/jobs/${session.job_id}`);

        void (async () => {
          try {
            await uploadFileToSignedUrl(session.upload_url, file);
            await completeDirectUpload(session.job_id);
          } catch (directUploadError) {
            await failDirectUpload(
              session.job_id,
              directUploadError instanceof Error
                ? directUploadError.message
                : "Direct upload failed.",
            );
          }
        })();

        return;
      } catch (directUploadError) {
        const message =
          directUploadError instanceof Error ? directUploadError.message : "";
        if (!message.includes("Direct upload requires Supabase storage")) {
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
    }
  }

  return (
    <form className="upload-form" onSubmit={handleSubmit}>
      <label className="field" style={{ display: "block", marginBottom: 16 }}>
        <div className="upload-label">Video link</div>
        <input
          className="upload-input"
          type="url"
          inputMode="url"
          placeholder="Paste a YouTube URL"
          value={videoUrl}
          disabled={isSubmitting}
          onChange={(event) => setVideoUrl(event.target.value)}
          style={{
            width: "100%",
            marginTop: 8,
            padding: "12px 14px",
            borderRadius: 12,
            border: "1px solid var(--line)",
            background: "rgba(0, 0, 0, 0.2)",
            color: "var(--text)",
          }}
        />
        <p className="upload-copy" style={{ marginTop: 8 }}>
          Paste a YouTube link or drop a local MP4 / MOV file below. URL import only supports YouTube.
        </p>
      </label>

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
          {isSubmitting ? "Uploading..." : "Generate clips"}
        </button>
        <span className="note">You’ll be redirected as soon as processing starts.</span>
      </div>

      {error ? <div className="alert">{error}</div> : null}
    </form>
  );
}
