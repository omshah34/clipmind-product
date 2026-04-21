/**
 * File: app/jobs/[jobId]/studio/page.tsx
 * Purpose: Clip Studio page — auth guard, styled header, timeline editor, tips.
 */

import { auth } from '@/auth';
import { redirect } from 'next/navigation';
import Link from 'next/link';
import ClipTimelineEditor from '@/components/clip-timeline-editor';

export const metadata = { title: 'Clip Studio — ClipMind' };

export default async function StudioPage({
  params,
}: {
  params: { jobId: string };
}) {
  const session = await auth();

  // Redirect unauthenticated users
  if (!session?.user) {
    redirect('/login');
  }

  const userId =
    (session.user as any)?.id ||
    session.user.email ||
    'anonymous';

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0d0e14',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    }}>

      {/* ── Top bar ── */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 50,
        background: 'rgba(13,14,20,0.92)',
        backdropFilter: 'blur(12px)',
        borderBottom: '1px solid #22253a',
        padding: '0 24px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        height: 52,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Logo dot */}
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: '#00c9a7',
            boxShadow: '0 0 8px #00c9a7',
            flexShrink: 0,
          }} />
          <span style={{ fontSize: 13, fontWeight: 700, color: '#dde0f0', letterSpacing: '0.06em' }}>
            CLIP STUDIO
          </span>
          <span style={{
            height: 16, width: 1, background: '#22253a', margin: '0 2px',
          }} />
          <span style={{
            fontSize: 11, color: '#555870', fontFamily: 'monospace',
            background: '#181a26', border: '1px solid #22253a',
            borderRadius: 4, padding: '2px 8px',
          }}>
            {params.jobId.slice(0, 8)}…
          </span>
        </div>

        <Link
          href={`/jobs/${params.jobId}`}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '6px 14px',
            background: '#181a26',
            border: '1px solid #22253a',
            borderRadius: 7,
            color: '#8b8fa8',
            fontSize: 12, fontWeight: 600,
            textDecoration: 'none',
          }}
        >
          ← Back to Job
        </Link>
      </header>

      {/* ── Page content ── */}
      <main style={{ maxWidth: 1140, margin: '0 auto', padding: '28px 20px 60px' }}>

        {/* Page heading */}
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: '#dde0f0', margin: '0 0 6px 0' }}>
            Refine your clips
          </h1>
          <p style={{ fontSize: 14, color: '#555870', margin: 0 }}>
            Edit detected clips, regenerate with custom settings, and optimize for your audience.
          </p>
        </div>

        <ClipTimelineEditor jobId={params.jobId} userId={userId} />

        {/* ── Tips panel (from File 2) ── */}
        <div style={{
          marginTop: 32,
          padding: '20px 24px',
          border: '1px solid rgba(255,111,97,0.3)',
          background: 'rgba(255,111,97,0.05)',
          borderRadius: 10,
        }}>
          <h3 style={{ margin: '0 0 10px', fontSize: 16, fontWeight: 600, color: '#dde0f0' }}>
            💡 Tips for best results
          </h3>
          <ul style={{ margin: 0, paddingLeft: 20, color: '#555870', lineHeight: 1.8, fontSize: 14 }}>
            <li>Use natural language instructions to guide clip detection</li>
            <li>Adjust individual score weights to prioritize specific aspects</li>
            <li>Compare different regenerations to find your best clips</li>
            <li>Longer instructions (3–5 words) tend to work better than single adjectives</li>
          </ul>
        </div>

      </main>
    </div>
  );
}