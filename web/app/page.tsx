/**
 * File: app/page.tsx
 * Purpose: Landing page. Displays upload form and brand information.
 */

import UploadForm from "../components/upload-form";


export default function HomePage() {
  return (
    <main className="page hero-shell">
      <div className="brand">
        <div className="brand-mark">
          <span className="brand-dot" />
          ClipMind
        </div>
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <span className="hero-chip">AI clip studio</span>
          <a href="/jobs" className="subtle-button">
            My uploads
          </a>
          <a href="/campaigns" className="subtle-button">
            Campaigns
          </a>
          <a href="/intelligence" className="subtle-button">
            📊 Analytics
          </a>
        </div>
      </div>

      <section className="hero">
        <div className="hero-copy">
          <div className="kicker">Viral moments detected from full transcripts</div>
          <h1>Turn long videos into ready-to-post clips.</h1>
          <p className="lead">
            ClipMind finds the strongest moments, burns in captions, and exports vertical clips
            for Shorts, Reels, and TikTok without opening a timeline editor.
          </p>

          <div className="hero-actions">
            <a href="/campaigns/new" className="subtle-button">
              Build a campaign
            </a>
            <a href="/intelligence" className="subtle-button">
              See analytics
            </a>
          </div>

          <div className="hero-meta">
            <span className="hero-chip">3 top clips returned</span>
            <span className="hero-chip">25-60s duration window</span>
            <span className="hero-chip">1080×1920 vertical export</span>
          </div>
        </div>

        <aside className="poster">
          <div className="signal-board">
            <div className="signal-frame">
              <div className="signal-header">
                <div>
                  <strong>Processing path</strong>
                  <div className="shell-subtitle">From upload to clip export in one pass.</div>
                </div>
                <span className="hero-chip">Live</span>
              </div>

              <div className="signal-steps">
                <div className="signal-step">
                  <div>
                    <b>1. Upload source video</b>
                    <small>MP4 or MOV up to 2GB</small>
                  </div>
                  <em>Start here</em>
                </div>
                <div className="signal-step">
                  <div>
                    <b>2. Detect high-signal moments</b>
                    <small>Transcript, hook, emotion, clarity</small>
                  </div>
                  <em>AI scoring</em>
                </div>
                <div className="signal-step">
                  <div>
                    <b>3. Export vertical clips</b>
                    <small>Captions burned in, ready to publish</small>
                  </div>
                  <em>Auto export</em>
                </div>
              </div>
            </div>

            <div className="signal-meta">
              <div>
                <strong>Real-time</strong>
                <span>Job status updates while the worker runs.</span>
              </div>
              <div>
                <strong>Campaign-ready</strong>
                <span>Reuse clips across multiple campaigns.</span>
              </div>
            </div>
          </div>

          <div className="panel" style={{ marginTop: 18 }}>
            <h2>Start a job</h2>
            <p>
              ClipMind validates the upload, queues a background worker, and returns a <code>job_id</code>
              immediately. The job page handles polling and preview.
            </p>
            <UploadForm />
            <p className="note">
              Accepted formats: MP4, MOV. Max size: 2GB. Duration: 2 to 90 minutes.
            </p>
          </div>
        </aside>
      </section>

      <section className="section-band">
        <div>
          <h2>What the product does well</h2>
          <p>
            The interface is tuned for fast upload, clear progress, and quick review. Each screen
            should feel like a working studio, not a generic dashboard.
          </p>
        </div>

        <div className="feature-grid">
          <div className="feature-item">
            <strong>Find the moment</strong>
            <span>
              The pipeline ranks clips by hook strength, emotion, and clarity so the right cut is
              easy to spot.
            </span>
          </div>
          <div className="feature-item">
            <strong>Keep the brand intact</strong>
            <span>
              Captions, clip sizing, and brand-kit support keep exports visually consistent.
            </span>
          </div>
          <div className="feature-item">
            <strong>Move to publish</strong>
            <span>
              Campaigns and analytics live one click away from the upload flow, so the handoff is
              quick.
            </span>
          </div>
        </div>
      </section>
    </main>
  );
}
