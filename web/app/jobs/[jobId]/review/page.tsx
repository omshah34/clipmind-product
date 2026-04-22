// DEV ONLY — REVERT BEFORE DEPLOY
import { auth } from '@/auth';
import { redirect } from 'next/navigation';
import { getClipPreview } from '@/lib/api';
import SwipeDeck from '@/components/swipe-deck';

import type { Metadata, Viewport } from "next";

export const metadata: Metadata = { 
  title: 'Review Clips — ClipMind',
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default async function ReviewPage({
  params,
}: {
  params: { jobId: string };
}) {
  // const session = await auth();

  // Redirect unauthenticated users
  // if (!session?.user) {
  //   redirect('/login');
  // }

  const userId = '00000000-0000-0000-0000-000000000000';


  // Fetch preview data server-side
  let preview;
  try {
    preview = await getClipPreview(params.jobId);
  } catch (err) {
    return (
      <div style={{ background: '#0d0e14', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', padding: 20 }}>
        <p>Failed to load clips. Please try again later.</p>
      </div>
    );
  }

  // Only show clips that haven't been approved/discarded yet for the swipe flow
  // (Filter out discarded ones, but maybe show all pending ones)
  const pendingClips = preview.current_clips.filter(c => (c as any).user_status !== 'discarded');

  return (
    <div style={{
      minHeight: '100vh',
      background: '#0d0e14',
      overflow: 'hidden',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    }}>
      {/* ── Top bar ── */}
      <header style={{
        padding: '16px 24px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        borderBottom: '1px solid #22253a',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#00c9a7', boxShadow: '0 0 8px #00c9a7' }} />
          <span style={{ fontSize: 14, fontWeight: 700, color: '#dde0f0', letterSpacing: '0.05em' }}>
            REVIEW MODE
          </span>
        </div>
        <a 
          href={`/jobs/${params.jobId}/studio`}
          style={{ fontSize: 12, color: '#555870', textDecoration: 'none' }}
        >
          Close
        </a>
      </header>

      <main style={{ padding: '20px' }}>
        <SwipeDeck 
          jobId={params.jobId} 
          userId={userId} 
          clips={pendingClips} 
          onComplete={() => {}} 
        />
      </main>
    </div>
  );
}
