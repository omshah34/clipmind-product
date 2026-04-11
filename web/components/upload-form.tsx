"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { uploadVideo } from "../lib/api";


export default function UploadForm() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose an MP4 or MOV file before starting the job.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    try {
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
      <label className="field">
        <div style={{ marginBottom: 8, fontWeight: 700 }}>Source video</div>
        <input
          accept=".mp4,.mov,video/mp4,video/quicktime"
          disabled={isSubmitting}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          type="file"
        />
      </label>

      <div className="upload-row">
        <button className="button" disabled={isSubmitting} type="submit">
          {isSubmitting ? "Uploading..." : "Generate clips"}
        </button>
        {file ? <span className="note">{file.name}</span> : null}
      </div>

      {error ? <div className="alert">{error}</div> : null}
    </form>
  );
}
