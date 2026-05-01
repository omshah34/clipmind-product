'use client';

import React, { useState } from 'react';
import Link from 'next/link';

/* ── Inline icon helper ── */
const Icon = ({ d, size = 16 }: { d: string; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

/* ── Fake data (replace with React Query hooks in production) ── */
const STATS = [
  { label: 'Total clips',     value: '1,284',  delta: '+12%',  up: true,  icon: 'M15 10l4.553-2.069A1 1 0 0121 8.882v6.236a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z' },
  { label: 'Avg score',       value: '81.4',   delta: '+3.2',  up: true,  icon: 'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z' },
  { label: 'Views this week', value: '94.2K',  delta: '+18%',  up: true,  icon: 'M1 12S5 4 12 4s11 8 11 8-4 8-11 8S1 12 1 12z M12 15a3 3 0 100-6 3 3 0 000 6z' },
  { label: 'Jobs queued',     value: '3',      delta: '−2',    up: false, icon: 'M12 20h9M16.376 3.622A1 1 0 0118 4.466v.001a1 1 0 01-.293.708L7 16l-4 1 1-4L14.879 2.707a1 1 0 011.497.915z' },
];

const JOBS = [
  { id: 'j1', title: 'How to build a SaaS in 2025', platform: 'YouTube', status: 'completed', clips: 8,  score: 88, time: '2h ago'   },
  { id: 'j2', title: 'My morning routine as a creator', platform: 'Upload', status: 'processing', clips: 0,  score: 0,  time: '45m ago'  },
  { id: 'j3', title: 'React 19 deep dive — full tutorial', platform: 'YouTube', status: 'completed', clips: 12, score: 91, time: '5h ago'   },
  { id: 'j4', title: 'Podcast Ep. 47 — Guest Interview', platform: 'Upload', status: 'failed',    clips: 0,  score: 0,  time: '1d ago'   },
  { id: 'j5', title: 'Day in the life vlog', platform: 'YouTube', status: 'completed', clips: 5,  score: 74, time: '2d ago'   },
];

const TOP_CLIPS = [
  { id: 'c1', title: 'The ONE thing that changed my productivity', score: 96, views: '18.4K', platform: 'TikTok'   },
  { id: 'c2', title: 'Hot take: React is getting too complex',     score: 93, views: '12.1K', platform: 'YouTube'  },
  { id: 'c3', title: 'This mistake cost me $10K',                  score: 89, views: '9.8K',  platform: 'LinkedIn' },
];

/* ── StatusBadge ── */
function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; icon: string; cls: string }> = {
    completed:  { label: 'Completed',  icon: 'M20 6L9 17l-5-5',                    cls: 'status-completed'  },
    processing: { label: 'Processing', icon: 'M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83', cls: 'status-processing' },
    failed:     { label: 'Failed',     icon: 'M18 6L6 18M6 6l12 12',               cls: 'status-failed'     },
    queued:     { label: 'Queued',     icon: 'M12 8v4l3 3M12 2a10 10 0 100 20 10 10 0 000-20z', cls: 'status-queued' },
  };
  const { label, icon, cls } = map[status] ?? map.queued;
  return (
    <span className={cls} style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      fontSize: '11px', fontWeight: 500, padding: '3px 8px',
      borderRadius: '99px',
    }}>
      <svg width={11} height={11} viewBox="0 0 24 24" fill="none"
        stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round"
        className={status === 'processing' ? 'animate-spin' : ''}>
        <path d={icon} />
      </svg>
      {label}
    </span>
  );
}

/* ── Score pill ── */
function ScorePill({ score }: { score: number }) {
  const color = score >= 85 ? 'var(--green)' : score >= 65 ? 'var(--amber)' : 'var(--red)';
  const bg    = score >= 85 ? 'var(--green-dim)' : score >= 65 ? 'var(--amber-dim)' : 'var(--red-dim)';
  if (!score) return null;
  return (
    <span style={{
      fontSize: '11px', fontWeight: 600, fontFamily: 'var(--font-mono)',
      color, background: bg, padding: '2px 7px', borderRadius: '99px',
    }}>
      {score}
    </span>
  );
}

/* ── Platform tag ── */
function PlatformTag({ platform }: { platform: string }) {
  const map: Record<string, string> = {
    YouTube: '#FF4444', TikTok: '#69C9D0', LinkedIn: '#0A66C2', Upload: 'var(--text-tertiary)',
  };
  return (
    <span style={{
      fontSize: '10px', fontWeight: 500, letterSpacing: '0.04em',
      color: map[platform] ?? 'var(--text-tertiary)',
      background: 'var(--bg-elevated)', border: '1px solid var(--border)',
      padding: '2px 7px', borderRadius: 'var(--radius-sm)',
      textTransform: 'uppercase',
    }}>
      {platform}
    </span>
  );
}

export default function DashboardPage() {
  const [hoveredJob, setHoveredJob] = useState<string | null>(null);

  return (
    <div style={{ padding: '32px 36px', maxWidth: 1200, margin: '0 auto' }}>

      {/* ── Header ── */}
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '26px', fontWeight: 700, letterSpacing: '-0.02em', marginBottom: '6px' }}>
          Good morning
          <span style={{ color: 'var(--accent)' }}> ✦</span>
        </h1>
        <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>
          Your content pipeline is running. 3 jobs active this week.
        </p>
      </div>

      {/* ── Stats row ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '36px' }}>
        {STATS.map((s) => (
          <div key={s.label} style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)', padding: '18px 20px',
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-strong)'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', fontWeight: 500 }}>{s.label}</span>
              <span style={{
                width: 28, height: 28, borderRadius: 'var(--radius-md)',
                background: 'var(--bg-elevated)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--text-secondary)',
              }}>
                <Icon d={s.icon} size={13} />
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '24px', fontWeight: 500, color: 'var(--text-primary)', letterSpacing: '-0.03em' }}>
                {s.value}
              </span>
              <span style={{ fontSize: '11px', fontWeight: 500, color: s.up ? 'var(--green)' : 'var(--red)' }}>
                {s.delta}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* ── Two columns ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px', alignItems: 'start' }}>

        {/* ── Recent Jobs ── */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <h2 style={{ fontSize: '15px', fontWeight: 600, fontFamily: 'var(--font-display)' }}>Recent jobs</h2>
            <Link href="/jobs" style={{ fontSize: '12px', color: 'var(--text-secondary)', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '4px' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--accent)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)'; }}
            >
              View all
              <Icon d="M9 18l6-6-6-6" size={12} />
            </Link>
          </div>
          <div style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)', overflow: 'hidden',
          }}>
            {JOBS.map((job, i) => (
              <Link key={job.id} href={`/jobs/${job.id}`} style={{ textDecoration: 'none' }}>
                <div
                  style={{
                    display: 'flex', alignItems: 'center', gap: '16px',
                    padding: '14px 20px',
                    borderBottom: i < JOBS.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                    background: hoveredJob === job.id ? 'var(--bg-elevated)' : 'transparent',
                    transition: 'background 0.15s', cursor: 'pointer',
                  }}
                  onMouseEnter={() => setHoveredJob(job.id)}
                  onMouseLeave={() => setHoveredJob(null)}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{
                      fontSize: '13.5px', fontWeight: 500, color: 'var(--text-primary)',
                      whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      marginBottom: '4px',
                    }}>
                      {job.title}
                    </p>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <PlatformTag platform={job.platform} />
                      <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>{job.time}</span>
                      {job.clips > 0 && (
                        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                          {job.clips} clips
                        </span>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexShrink: 0 }}>
                    <ScorePill score={job.score} />
                    <StatusBadge status={job.status} />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>

        {/* ── Right panel ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

          {/* Quick upload CTA */}
          <div style={{
            background: 'linear-gradient(135deg, rgba(20,184,166,0.15) 0%, rgba(20,184,166,0.04) 100%)',
            border: '1px solid rgba(20,184,166,0.25)',
            borderRadius: 'var(--radius-lg)', padding: '20px',
          }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '6px' }}>New content ready?</h3>
            <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '14px', lineHeight: 1.5 }}>
              Paste a YouTube URL or upload a video to extract your best moments.
            </p>
            <Link href="/upload" style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px',
              padding: '8px 14px', background: 'var(--accent)',
              color: '#fff', fontSize: '13px', fontWeight: 500,
              borderRadius: 'var(--radius-md)', textDecoration: 'none', transition: 'opacity 0.15s',
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0.85'; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
            >
              <Icon d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" size={14} />
              Start processing
            </Link>
          </div>

          {/* Top performing clips */}
          <div>
            <h2 style={{ fontSize: '15px', fontWeight: 600, fontFamily: 'var(--font-display)', marginBottom: '12px' }}>
              Top clips this week
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {TOP_CLIPS.map((clip, i) => (
                <Link key={clip.id} href={`/clips/${clip.id}`} style={{ textDecoration: 'none' }}>
                  <div style={{
                    background: 'var(--bg-surface)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-md)', padding: '12px 14px',
                    display: 'flex', alignItems: 'flex-start', gap: '12px',
                    transition: 'border-color 0.15s',
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border-strong)'; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
                  >
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontSize: '12px', fontWeight: 500,
                      color: 'var(--text-tertiary)', minWidth: '16px', marginTop: '1px',
                    }}>
                      {i + 1}
                    </span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ fontSize: '12.5px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '4px', lineHeight: 1.4 }}>
                        {clip.title}
                      </p>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <PlatformTag platform={clip.platform} />
                        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>{clip.views} views</span>
                      </div>
                    </div>
                    <ScorePill score={clip.score} />
                  </div>
                </Link>
              ))}
            </div>
          </div>

          {/* Content DNA summary */}
          <div style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)', padding: '18px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 style={{ fontSize: '14px', fontWeight: 600, fontFamily: 'var(--font-display)' }}>Content DNA</h3>
              <Link href="/dna" style={{ fontSize: '11px', color: 'var(--accent)', textDecoration: 'none' }}>View all →</Link>
            </div>
            {[
              { label: 'Hook strength', value: 84 },
              { label: 'Pacing',        value: 71 },
              { label: 'Clarity',       value: 90 },
              { label: 'Virality',      value: 67 },
            ].map((dim) => (
              <div key={dim.label} style={{ marginBottom: '10px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{dim.label}</span>
                  <span style={{ fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', fontWeight: 500 }}>
                    {dim.value}
                  </span>
                </div>
                <div style={{ height: '3px', background: 'var(--bg-elevated)', borderRadius: '99px', overflow: 'hidden' }}>
                  <div style={{
                    height: '100%', width: `${dim.value}%`,
                    background: dim.value >= 80 ? 'var(--green)' : dim.value >= 65 ? 'var(--accent)' : 'var(--amber)',
                    borderRadius: '99px', transition: 'width 0.6s ease',
                  }} />
                </div>
              </div>
            ))}
          </div>

        </div>
      </div>
    </div>
  );
}
