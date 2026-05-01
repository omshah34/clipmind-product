/**
 * File: components/clip-list.tsx
 * Purpose: Grid of completed clips with scores, player, and download.
 *          Used on the job status page once a job completes.
 */

import { ClipSummary } from '../lib/api';
import { ClipCard } from './clip-card';

export default function ClipList({ clips, jobId }: { clips: ClipSummary[]; jobId: string }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
      gap: 16,
    }}>
      {clips.map((clip) => (
        <ClipCard key={clip.clip_index} clip={clip} jobId={jobId} />
      ))}
    </div>
  );
}
