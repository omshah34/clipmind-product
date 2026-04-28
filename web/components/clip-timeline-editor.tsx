/**
 * File: components/clip-timeline-editor.tsx
 * Purpose: Redesigned Clip Studio — inline video preview per clip, download buttons,
 *          score breakdowns, dark studio aesthetic, regeneration controls.
 *          Gaps 211/213: React Query integration and Memory Leak fix.
 *          Restored: Full UI richness (Advanced Settings sliders, sidebar details).
 */

'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ScoreRadar } from './score-radar';
import {
  getClipPreview,
  regenerateClips,
  downloadClip,
  getHookVariants,
  downloadCapcutBridge,
  adjustClipBoundary,
  type ClipPreviewData,
} from '@/lib/api';

type Clip = ClipPreviewData['current_clips'][number] & {
  clip_index?: number;
};

type TranscriptWord = ClipPreviewData['transcript_words'][number];
type HookVariant = { start_time: number; label: string; logic: string };

type ClipTimelineEditorProps = {
  jobId: string;
  userId: string;
  searchParams?: { clip?: string };
};

/* ─── Design tokens ────────────────────────────────────────── */
const T = {
  bg:        '#0d0e14',
  surface:   '#13151f',
  card:      '#181a26',
  cardHover: '#1c1e2c',
  border:    '#22253a',
  borderHi:  '#2e3250',
  accent:    '#00c9a7',
  accentDim: 'rgba(0,201,167,0.12)',
  accentBdr: 'rgba(0,201,167,0.28)',
  purple:    '#7c6af7',
  amber:     '#f59e0b',
  red:       '#ef4444',
  text:      '#dde0f0',
  muted:     '#555870',
  faint:     '#2a2d3f',
} as const;

function scoreColor(s: number) {
  if (s >= 8.5) return T.accent;
  if (s >= 7.0) return T.purple;
  if (s >= 5.5) return T.amber;
  return T.red;
}

function fmt(n: number) { return n.toFixed(1); }

const SCORE_DIMS = [
  { key: 'hook_score',     label: 'Hook'     },
  { key: 'emotion_score',  label: 'Emotion'  },
  { key: 'clarity_score',  label: 'Clarity'  },
  { key: 'story_score',    label: 'Story'    },
  { key: 'virality_score', label: 'Virality' },
] as const;

/* ─── Sub-components ───────────────────────────────────────── */

const ScorePill = React.memo(({ label, score }: { label: string; score: number }) => {
  const c = scoreColor(score);
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 9px', borderRadius: 100,
      background: `${c}14`, border: `1px solid ${c}30`,
      fontSize: 11, color: T.muted, whiteSpace: 'nowrap',
    }}>
      <span style={{ color: c, fontWeight: 700, fontFamily: 'monospace' }}>
        {fmt(score)}
      </span>
      {label}
    </span>
  );
});

const ScoreBar = React.memo(({ label, score }: { label: string; score: number }) => {
  const c = scoreColor(score);
  const pct = (score / 10) * 100;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
      <span style={{ fontSize: 12, color: T.muted, width: 60, flexShrink: 0 }}>{label}</span>
      <div style={{ flex: 1, height: 4, background: T.faint, borderRadius: 99 }}>
        <div style={{ width: `${pct}%`, height: '100%', background: c, borderRadius: 99, transition: 'width 0.4s ease' }} />
      </div>
      <span style={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 700, color: c, width: 28, textAlign: 'right' }}>
        {fmt(score)}
      </span>
    </div>
  );
});

function DownloadIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/>
      <line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
  );
}

function ClipCard({
  clip,
  clipNum,
  jobId,
  isSelected,
  onSelect,
}: {
  clip: Clip;
  clipNum: number;
  jobId: string;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const [downloading, setDownloading] = useState(false);
  const [dlError, setDlError] = useState<string | null>(null);

  const hasVideo = !!clip.clip_url && clip.clip_url !== '';
  const borderColor = isSelected ? T.accent : T.border;

  const clipIndex = (clip as any).clip_index != null
    ? (clip as any).clip_index
    : clipNum - 1;

  async function handleDownload(e: React.MouseEvent) {
    e.stopPropagation();
    setDlError(null);
    try {
      await downloadClip(
        jobId,
        clipIndex,
        `clipmind-clip-${clipNum}.mp4`,
        () => setDownloading(true),
        () => setDownloading(false),
      );
    } catch {
      setDownloading(false);
      setDlError('Download failed — try again');
    }
  }

  const [exportingCapcut, setExportingCapcut] = useState(false);
  async function handleCapcutBridge(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await downloadCapcutBridge(
        jobId,
        clipIndex,
        `clipmind-capcut-assets-${clipNum}.zip`,
        () => setExportingCapcut(true),
        () => setExportingCapcut(false),
      );
    } catch {
      setExportingCapcut(false);
      setDlError('CapCut export failed — try again');
    }
  }

  return (
    <div
      id={`clip-card-${clipNum - 1}`}
      onClick={onSelect}
      style={{
        background: isSelected ? T.cardHover : T.card,
        border: `1px solid ${borderColor}`,
        borderRadius: 14,
        padding: 22,
        cursor: 'pointer',
        transition: 'border-color 0.15s, background 0.15s',
        outline: isSelected ? `1px solid ${T.accentBdr}` : 'none',
        outlineOffset: -1,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{
            fontSize: 10, fontWeight: 700, letterSpacing: '0.12em',
            color: T.accent, background: T.accentDim, border: `1px solid ${T.accentBdr}`,
            borderRadius: 5, padding: '3px 9px', fontFamily: 'monospace',
          }}>
            CLIP {String(clipNum).padStart(2, '0')}
          </span>
          <span style={{ fontSize: 11, color: T.muted, fontFamily: 'monospace' }}>
            {fmt(clip.start_time)}s – {fmt(clip.end_time)}s
          </span>
          <span style={{
            fontSize: 11, color: T.muted,
            background: T.faint, borderRadius: 4, padding: '2px 7px',
          }}>
            {fmt(clip.duration)}s
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', flexShrink: 0 }}>
          <span style={{
            fontSize: 26, fontWeight: 800, fontFamily: 'monospace',
            color: scoreColor(clip.final_score), lineHeight: 1,
          }}>
            {fmt(clip.final_score)}
          </span>
          <span style={{ fontSize: 10, color: T.muted, letterSpacing: '0.08em' }}>SCORE</span>
        </div>
      </div>

      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#07080d',
          borderRadius: 10,
          overflow: 'hidden',
          marginBottom: 14,
          border: `1px solid ${T.faint}`,
        }}
      >
        {hasVideo ? (
          <video
            controls
            playsInline
            preload="metadata"
            src={clip.clip_url}
            style={{ width: '100%', display: 'block', maxHeight: 240, objectFit: 'contain', background: '#07080d' }}
          />
        ) : (
          <div style={{
            height: 120, display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexDirection: 'column', gap: 8, color: T.faint,
          }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            <span style={{ fontSize: 12 }}>Processing video…</span>
          </div>
        )}
      </div>

      <p style={{ fontSize: 13, color: '#8b8fa8', lineHeight: 1.65, margin: '0 0 14px 0' }}>
        {clip.reason}
      </p>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {SCORE_DIMS.map(({ key, label }) => (
          <ScorePill key={key} label={label} score={(clip as any)[key] ?? 0} />
        ))}
      </div>

      <div
        onClick={(e) => e.stopPropagation()}
        style={{ display: 'flex', gap: 10, flexDirection: 'column' }}
      >
        <div style={{ display: 'flex', gap: 10 }}>
          {hasVideo && (
            <button
              onClick={handleDownload}
              disabled={downloading}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 7,
                padding: '8px 16px',
                background: downloading ? T.faint : T.accentDim,
                border: `1px solid ${T.accentBdr}`,
                borderRadius: 8,
                color: downloading ? T.muted : T.accent,
                fontSize: 13, fontWeight: 600,
                cursor: downloading ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s',
              }}
            >
              {downloading ? '...' : <><DownloadIcon />Download Clip</>}
            </button>
          )}
          <button
            onClick={onSelect}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '8px 14px',
              background: isSelected ? T.faint : 'transparent',
              border: `1px solid ${T.borderHi}`,
              borderRadius: 8,
              color: T.muted,
              fontSize: 13, fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            {isSelected ? '✓ Selected' : 'View Score'}
          </button>
          
          <button
            onClick={handleCapcutBridge}
            disabled={exportingCapcut}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '8px 14px',
              background: 'transparent', border: `1px solid ${T.faint}`,
              borderRadius: 8, color: T.muted, fontSize: 12, cursor: 'pointer',
            }}
          >
            {exportingCapcut ? '...' : 'CapCut Bridge'}
          </button>
        </div>
        {dlError && <p style={{ fontSize: 11, color: T.red, margin: 0 }}>{dlError}</p>}
      </div>
    </div>
  );
}

/* ─── Main Component ───────────────────────────────────────── */

export default function ClipTimelineEditor({ jobId, userId, searchParams }: ClipTimelineEditorProps) {
  const queryClient = useQueryClient();

  const { data: preview, isLoading: loading, error: queryError } = useQuery({
    queryKey: ['clips', jobId],
    queryFn: () => getClipPreview(jobId),
    staleTime: 300000,
  });

  const [regenerating, setRegenerating] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [customInstructions, setCustomInstructions] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [customWeights, setCustomWeights] = useState({
    hook_score: 0.2, emotion_score: 0.2, clarity_score: 0.2, story_score: 0.2, virality_score: 0.2,
  });

  const isDraggingRef = useRef(false);
  const dragStartIdxRef = useRef<number | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStartIdx, setDragStartIdx] = useState<number | null>(null);
  const [dragEndIdx, setDragEndIdx] = useState<number | null>(null);

  const [hookVariants, setHookVariants] = useState<HookVariant[]>([]);
  const [loadingHooks, setLoadingHooks] = useState(false);

  const clips = useMemo<Clip[]>(
    () => (Array.isArray(preview?.current_clips) ? (preview.current_clips as Clip[]) : []),
    [preview],
  );
  const transcriptWords = useMemo<TranscriptWord[]>(
    () => (Array.isArray(preview?.transcript_words) ? preview.transcript_words : []),
    [preview],
  );

  useEffect(() => {
    if (!clips.length) {
      if (selectedIdx !== 0) setSelectedIdx(0);
      setHookVariants([]);
      return;
    }
    if (selectedIdx >= clips.length) {
      setSelectedIdx(clips.length - 1);
    }
  }, [clips.length, selectedIdx]);

  useEffect(() => {
    if (!clips[selectedIdx]) {
      setHookVariants([]);
      return;
    }
    void loadHookVariants(selectedIdx);
  }, [clips, selectedIdx, jobId]);

  async function loadHookVariants(idx: number) {
    if (!clips[idx]) {
      setHookVariants([]);
      return;
    }
    try {
      setLoadingHooks(true);
      const data = await getHookVariants(jobId, idx);
      setHookVariants(Array.isArray(data.variants) ? data.variants : []);
    } catch {
      setHookVariants([]);
    } finally {
      setLoadingHooks(false);
    }
  }

  useEffect(() => {
    const handleGlobalMouseUp = (e: MouseEvent) => {
      if (!isDraggingRef.current || dragStartIdxRef.current === null || !preview) return;
      const target = e.target as HTMLElement;
      const wordIdxAttr = target.getAttribute('data-word-idx');
      const finalIdx = wordIdxAttr !== null ? parseInt(wordIdxAttr, 10) : dragEndIdx;
      if (finalIdx !== null) {
        const nextClips = [...clips];
        const clip = { ...nextClips[selectedIdx] };
        const min = Math.min(dragStartIdxRef.current, finalIdx);
        const max = Math.max(dragStartIdxRef.current, finalIdx);
        const startWord = transcriptWords[min];
        const endWord = transcriptWords[max];
        if (!clip || !startWord || !endWord) {
          isDraggingRef.current = false;
          dragStartIdxRef.current = null;
          setIsDragging(false);
          setDragStartIdx(null);
          setDragEndIdx(null);
          return;
        }
        const nextStart = startWord.start;
        const nextEnd = endWord.end;
        clip.start_time = nextStart;
        clip.end_time = nextEnd;
        nextClips[selectedIdx] = clip;
        queryClient.setQueryData(['clips', jobId], { ...preview, current_clips: nextClips });
        void adjustClipBoundary(jobId, userId, selectedIdx, nextStart, nextEnd).catch(() => {
          queryClient.invalidateQueries({ queryKey: ['clips', jobId] });
        });
      }
      isDraggingRef.current = false;
      dragStartIdxRef.current = null;
      setIsDragging(false);
      setDragStartIdx(null);
      setDragEndIdx(null);
    };

    const handleGlobalMouseMove = (e: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const target = e.target as HTMLElement;
      const wordIdxAttr = target.getAttribute('data-word-idx');
      if (wordIdxAttr !== null) setDragEndIdx(parseInt(wordIdxAttr, 10));
    };

    if (isDragging) {
      window.addEventListener('mouseup', handleGlobalMouseUp);
      window.addEventListener('mousemove', handleGlobalMouseMove);
    }
    return () => {
      window.removeEventListener('mouseup', handleGlobalMouseUp);
      window.removeEventListener('mousemove', handleGlobalMouseMove);
    };
  }, [isDragging, dragEndIdx, preview, clips, transcriptWords, selectedIdx, jobId, userId, queryClient]);

  function updateWeight(key: string, value: number) {
    const next = { ...customWeights, [key]: value };
    const sum = Object.values(next).reduce((a, b) => a + b, 0);
    const norm = Object.fromEntries(Object.entries(next).map(([k, v]) => [k, v / (sum || 1)])) as typeof customWeights;
    setCustomWeights(norm);
  }

  async function handleRegenerate() {
    if (!preview) return;
    try {
      setRegenerating(true);
      await regenerateClips(jobId, userId, clips.length, showAdvanced ? customWeights : undefined, customInstructions || undefined);
      await new Promise((r) => setTimeout(r, 1200));
      queryClient.invalidateQueries({ queryKey: ['clips', jobId] });
      setCustomInstructions('');
    } catch { /* ignore */ } finally {
      setRegenerating(false);
    }
  }

  if (loading) return <div style={{ minHeight: 320, background: T.bg, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>Loading...</div>;
  if (queryError || !preview) return <div>Error loading studio</div>;

  const selectedClip = clips[selectedIdx] ?? null;

  return (
    <div style={{ color: T.text, paddingBottom: 80 }}>
      {/* Stats bar */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '10px 18px' }}>
          <span style={{ fontSize: 20, fontWeight: 700, color: T.accent }}>{clips.length}</span>
          <span style={{ fontSize: 11, color: T.muted, marginLeft: 8 }}>CLIPS</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 320px', gap: 20 }}>
        {/* LEFT */}
        <div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {clips.map((clip, idx) => (
              <ClipCard key={idx} clip={clip as Clip} clipNum={idx + 1} jobId={jobId} isSelected={selectedIdx === idx} onSelect={() => setSelectedIdx(idx)} />
            ))}
          </div>
        </div>

        {/* RIGHT: Sidebar - RESTORED ADVANCED SETTINGS */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, position: 'sticky', top: 20 }}>
          {selectedClip && (
            <>
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20 }}>
                <h3 style={{ fontSize: 11, fontWeight: 700, color: T.muted, letterSpacing: '0.1em', marginBottom: 12 }}>HOOK VARIATIONS</h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {loadingHooks ? (
                    <div style={{ fontSize: 12, color: T.muted }}>Loading hook variations…</div>
                  ) : hookVariants.length ? hookVariants.map((v, i) => (
                    <button key={i} onClick={() => {}} style={{ textAlign: 'left', padding: '10px', borderRadius: 8, background: '#0d0e14', border: `1px solid ${T.faint}`, cursor: 'pointer' }}>
                      <div style={{ fontSize: 12, fontWeight: 700, color: T.text }}>{v.label}</div>
                      <div style={{ fontSize: 11, color: T.muted }}>{v.logic}</div>
                    </button>
                  )) : (
                    <div style={{ fontSize: 12, color: T.muted }}>No hook variations available yet.</div>
                  )}
                </div>
              </div>

              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, color: T.muted, marginBottom: 16 }}>SCORE RADAR</h3>
                <div style={{ display: 'flex', justifyContent: 'center' }}>
                  <ScoreRadar hookScore={selectedClip.hook_score} emotionScore={selectedClip.emotion_score} clarityScore={selectedClip.clarity_score} storyScore={selectedClip.story_score} viralityScore={selectedClip.virality_score} size={160} />
                </div>
              </div>
            </>
          )}

          {/* FIND MORE CLIPS - RESTORED SLIDERS */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
               <h3 style={{ fontSize: 13, fontWeight: 600, color: T.muted, margin: 0 }}>FIND MORE CLIPS</h3>
               <button onClick={() => setShowAdvanced(!showAdvanced)} style={{ background: 'none', border: 'none', color: T.accent, fontSize: 11, cursor: 'pointer' }}>
                 {showAdvanced ? 'Hide Advanced' : 'Advanced Settings'}
               </button>
            </div>

            {showAdvanced && (
              <div style={{ marginBottom: 16, display: 'grid', gap: 12 }}>
                {Object.entries(customWeights).map(([key, val]) => (
                  <div key={key}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 11, color: T.muted }}>{key.replace('_score', '').toUpperCase()}</span>
                      <span style={{ fontSize: 11, color: T.accent }}>{(val * 100).toFixed(0)}%</span>
                    </div>
                    <input type="range" min="0" max="1" step="0.05" value={val} onChange={(e) => updateWeight(key, parseFloat(e.target.value))} style={{ width: '100%', accentColor: T.accent }} />
                  </div>
                ))}
              </div>
            )}
            
            <textarea value={customInstructions} onChange={(e) => setCustomInstructions(e.target.value)} placeholder='e.g., "Focus on moments with music"' rows={3} style={{ width: '100%', background: '#0d0e14', border: `1px solid ${T.borderHi}`, borderRadius: 8, padding: '10px 12px', color: T.text, fontSize: 13, resize: 'none', outline: 'none', marginBottom: 12 }} />
            <button onClick={handleRegenerate} disabled={regenerating} style={{ width: '100%', padding: '11px 0', background: regenerating ? T.faint : T.accent, borderRadius: 9, color: '#07080d', fontWeight: 700, cursor: 'pointer' }}>
              {regenerating ? 'Regenerating...' : 'Regenerate Clips'}
            </button>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 24 }}>
        <button onClick={() => setShowTranscript(!showTranscript)} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: '12px 18px', width: '100%', cursor: 'pointer', color: T.muted, fontSize: 13, fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
          <span>TRANSCRIPT TIMELINE</span>
          <span>{showTranscript ? '▲' : '▼'}</span>
        </button>
        {showTranscript && (
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: '0 0 12px 12px', borderTop: 'none', padding: 20, maxHeight: 260, overflowY: 'auto', lineHeight: 1.9, fontSize: 14, userSelect: 'none' }}>
            {transcriptWords.map((w, i) => {
              let inSelected = selectedClip && w.start >= selectedClip.start_time && w.end <= selectedClip.end_time;
              if (isDragging && dragStartIdx !== null && dragEndIdx !== null) {
                const min = Math.min(dragStartIdx, dragEndIdx);
                const max = Math.max(dragStartIdx, dragEndIdx);
                inSelected = i >= min && i <= max;
              }
              return (
                <span key={i} data-word-idx={i} onMouseDown={() => { isDraggingRef.current = true; dragStartIdxRef.current = i; setIsDragging(true); setDragStartIdx(i); setDragEndIdx(i); }} style={{ display: 'inline-block', margin: '2px 2px', padding: '1px 4px', borderRadius: 3, cursor: 'pointer', background: inSelected ? T.accentDim : 'transparent', color: inSelected ? T.accent : T.muted }}>
                  {w.word}
                </span>
              );
            })}
          </div>
        )}
      </div>

      <style>{`@keyframes cm-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
