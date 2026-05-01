'use client';

import React from 'react';
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ClipSummary, deleteClip } from "../lib/api";
import ClipPlayer from './clip-player';

// Dummy toast since a global toast system is not yet fully integrated
const toast = {
  error: (msg: string) => {
    console.error(msg);
    alert(msg);
  }
};

function scoreColor(s: number) {
  if (s >= 8.5) return '#00c9a7';
  if (s >= 7.0) return '#7c6af7';
  if (s >= 5.5) return '#f59e0b';
  return '#ef4444';
}

export function ClipCard({ clip, jobId }: { clip: ClipSummary; jobId: string }) {
  const queryClient = useQueryClient();

  const deleteMutation = useMutation({
    mutationFn: (clipIndex: number) => deleteClip(jobId, clipIndex),

    // Gap 271: Optimistically remove from cache immediately
    onMutate: async (clipIndex) => {
      // Cancel any outgoing refetches (so they don't overwrite our optimistic update)
      await queryClient.cancelQueries({ queryKey: ["clips", jobId] });

      // Snapshot the previous value
      const prev = queryClient.getQueryData<ClipSummary[]>(["clips", jobId]);

      // Optimistically update to the new value
      queryClient.setQueryData(["clips", jobId], (old: ClipSummary[] = []) =>
        old.filter((c) => c.clip_index !== clipIndex)
      );

      return { prev }; // return snapshot for rollback
    },

    // 2. Rollback on failure
    onError: (_err, _clipIndex, context) => {
      queryClient.setQueryData(["clips", jobId], context?.prev);
      toast.error("Failed to delete clip — restored.");
    },

    // Always refetch after error or success:
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["clips", jobId] });
    },
  });

  return (
    <article
      style={{
        background: 'linear-gradient(180deg, rgba(255,255,255,0.98), rgba(248,250,253,0.96))',
        border: '1px solid rgba(16, 32, 51, 0.1)',
        borderRadius: 20,
        padding: 18,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
        boxShadow: '0 14px 30px rgba(16, 32, 51, 0.06)',
        transition: 'opacity 0.2s ease',
        opacity: deleteMutation.isPending ? 0.6 : 1,
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
      
      {/* Actions */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, marginTop: 'auto' }}>
         <div style={{ display: 'flex', gap: 10 }}>
           <a 
             href={`/intelligence?job_id=${jobId}&clip_index=${clip.clip_index}`}
             style={{ 
               fontSize: 11, fontWeight: 700, color: '#5271ff', 
               textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 
             }}
           >
             <span>📊</span> View Intelligence
           </a>
           <a 
             href={`/jobs/${jobId}/studio?clip=${clip.clip_index}`}
             style={{ 
               fontSize: 11, fontWeight: 700, color: '#a53c2f', 
               textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 
             }}
           >
             <span>🎬</span> Edit in Studio
           </a>
         </div>

         <button
           onClick={() => {
             if (confirm("Are you sure you want to delete this clip?")) {
               deleteMutation.mutate(clip.clip_index);
             }
           }}
           disabled={deleteMutation.isPending}
           style={{
             background: 'none',
             border: 'none',
             color: '#ef4444',
             fontSize: 11,
             fontWeight: 600,
             cursor: 'pointer',
             padding: '4px 8px',
             borderRadius: 6,
             transition: 'background 0.15s',
           }}
           onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = 'rgba(239, 68, 68, 0.08)'; }}
           onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = 'none'; }}
         >
           Delete
         </button>
      </div>
    </article>
  );
}
