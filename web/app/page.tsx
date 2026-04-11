import UploadForm from "../components/upload-form";


export default function HomePage() {
  return (
    <main className="page">
      <div className="brand">
        <div className="brand-mark">
          <span className="brand-dot" />
          ClipMind
        </div>
        <span className="note">Upload one video. Get your strongest clips back.</span>
      </div>

      <section className="hero">
        <div className="poster">
          <div className="kicker">Viral moments detected from full transcripts</div>
          <h1>ClipMind</h1>
          <p className="lead">
            Turn a 60-minute conversation into vertical, caption-burned clips that are ready
            for Shorts, Reels, and TikTok without opening a timeline editor.
          </p>

          <div className="metrics">
            <div className="metric">
              <strong>3</strong>
              <span>top clips returned by the MVP</span>
            </div>
            <div className="metric">
              <strong>25-60s</strong>
              <span>strict clip duration window</span>
            </div>
            <div className="metric">
              <strong>1080×1920</strong>
              <span>vertical output, captions burned in</span>
            </div>
          </div>
        </div>

        <aside className="panel">
          <h2>Start a job</h2>
          <p>
            ClipMind validates the upload, queues a background worker, and returns a `job_id`
            immediately. The job page handles polling and preview.
          </p>
          <UploadForm />
          <p className="note">
            Accepted formats: MP4, MOV. Max size: 2GB. Duration: 2 to 90 minutes.
          </p>
        </aside>
      </section>
    </main>
  );
}
