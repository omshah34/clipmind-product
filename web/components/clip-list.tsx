/**
 * File: components/clip-list.tsx
 * Purpose: Grid of completed clips with scores, player, and download.
 *          Used on the job status page once a job completes.
 */

import ClipPlayer from './clip-player';
import { ClipSummary } from '../lib/api';

function scoreColor(s: number) {
  if (s >= 8.5) return '#00c9a7';
  if (s >= 7.0) return '#7c6af7';
  if (s >= 5.5) return '#f59e0b';
  return '#ef4444';
}

export default function ClipList({ clips, jobId }: { clips: ClipSummary[]; jobId: string }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
      gap: 16,
    }}>
      {clips.map((clip) => (
        <article
          key={clip.clip_index}
          style={{
            background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,253,0.96))',
            border: '1px solid rgba(16, 32, 51, 0.1)',
            borderRadius: 20,
            padding: 18,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
            boxShadow: '0 14px 30px rgba(16, 32, 51, 0.06)',
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                fontSize: 10,
                fontWeight: 700,
                letterSpacing: '0.12em',
                color: '#a53c2f',
                background: 'rgba(255,111,97,0.1)',
                border: '1px solid rgba(255,111,97,0.18)',
                borderRadius: 999,
                padding: '4px 10px',
                textTransform: 'uppercase',
              }}>
                CLIP {String(clip.clip_index).padStart(2, '0')}
              </span>
              <p style={{ fontSize: 12, color: 'var(--muted)', margin: '8px 0 0' }}>
                {clip.duration.toFixed(1)}s
              </p>
            </div>
            <div style={{ textAlign: 'right' }}>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                minWidth: 64,
                padding: '8px 12px',
                borderRadius: 999,
                fontSize: 16,
                fontWeight: 800,
                color: scoreColor(clip.final_score),
                background: `${scoreColor(clip.final_score)}14`,
                border: `1px solid ${scoreColor(clip.final_score)}22`,
              }}>
                {clip.final_score.toFixed(1)}
              </span>
              <p style={{ fontSize: 10, color: 'var(--muted)', margin: '6px 0 0', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Score</p>
            </div>
          </div>

          {/* Player */}
          <ClipPlayer clipUrl={clip.clip_url} jobId={jobId} clipIndex={clip.clip_index} />

          {/* Reason */}
          <p style={{ fontSize: 13, color: 'var(--muted)', lineHeight: 1.6, margin: 0 }}>
            {clip.reason}
          </p>
        </article>
      ))}
    </div>
  );
}
