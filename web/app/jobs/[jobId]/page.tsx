/**
 * File: app/jobs/[jobId]/page.tsx
 * Purpose: Job status page. Polls backend to show job progress or results.
 */

import JobStatus from "../../../components/job-status";

export default function JobPage({ params }: { params: { jobId: string } }) {
  // Page for polling job status
  return (
    <main className="page">
      <div className="brand shell-header">
        <div style={{ display: "grid", gap: 6 }}>
          <div className="brand-mark">
            <span className="brand-dot" />
            ClipMind
          </div>
          <div className="shell-subtitle">Track processing, review clips, and jump into the studio.</div>
        </div>
        <a href="/" className="subtle-button">New upload</a>
      </div>

      <section className="panel">
        <h2>Processing job</h2>
        <p>
          This page polls the backend until the job is completed or failed.
        </p>
        <JobStatus jobId={params.jobId} />
      </section>
    </main>
  );
}
