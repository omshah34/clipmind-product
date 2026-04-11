import JobStatus from "../../../components/job-status";


export default function JobPage({ params }: { params: { jobId: string } }) {
  return (
    <main className="page">
      <div className="brand">
        <div className="brand-mark">
          <span className="brand-dot" />
          ClipMind
        </div>
        <a href="/" className="subtle-button">
          New upload
        </a>
      </div>

      <section className="panel">
        <h2>Processing job</h2>
        <p>
          This page polls the backend every 4 seconds until the job is completed or failed.
        </p>
        <JobStatus jobId={params.jobId} />
      </section>
    </main>
  );
}
