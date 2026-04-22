/**
 * File: components/clip-timeline-editor.tsx
 * Purpose: Redesigned Clip Studio — inline video preview per clip, download buttons,
 *          score breakdowns, dark studio aesthetic, regeneration controls.
 */

'use client';

import React, { useState, useEffect } from 'react';
import { ScoreRadar } from './score-radar';
import {
  getClipPreview,
  regenerateClips,
  getRegenerations,
  downloadClip,
  getHookVariants,
  downloadCapcutBridge,
  adjustClipBoundary,
  type ClipPreviewData,
  type RegenerationResult,
} from '@/lib/api';

type Clip = ClipPreviewData['current_clips'][number] & {
  clip_index?: number;
};

type ClipTimelineEditorProps = {
  jobId: string;
  userId: string;
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

function ScorePill({ label, score }: { label: string; score: number }) {
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
}

function ScoreBar({ label, score }: { label: string; score: number }) {
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
}

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

  // clip_url is the /stream endpoint — valid as long as it's a non-empty string
  const hasVideo = !!clip.clip_url && clip.clip_url !== '';
  const borderColor = isSelected ? T.accent : T.border;

  // 0-based index for the API
  const clipIndex = (clip as any).clip_index != null
    ? (clip as any).clip_index - 1   // clip_index from backend is 1-based
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
      {/* ── Card header ── */}
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

      {/* ── Video player ── */}
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
            // clip_url is now the /stream proxy endpoint — supports range requests
            src={clip.clip_url}
            style={{ width: '100%', display: 'block', maxHeight: 240, objectFit: 'contain', background: '#07080d' }}
            onError={(e) => {
              // Surface load errors in the console to aid debugging
              console.error(`[ClipCard] Video failed to load: ${clip.clip_url}`, e);
            }}
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

      {/* ── Reason ── */}
      <p style={{ fontSize: 13, color: '#8b8fa8', lineHeight: 1.65, margin: '0 0 14px 0' }}>
        {clip.reason}
      </p>

      {/* ── Score pills ── */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 16 }}>
        {SCORE_DIMS.map(({ key, label }) => (
          <ScorePill key={key} label={label} score={(clip as any)[key] ?? 0} />
        ))}
      </div>

      {/* ── Actions ── */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ display: 'flex', gap: 10, flexDirection: 'column' }}
      >
        <div style={{ display: 'flex', gap: 10 }}>
          {hasVideo && (
            // Use a <button> + fetch-blob approach instead of <a download>
            // so it works cross-origin (the <a download> attr is same-origin only)
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
              onMouseEnter={(e) => { if (!downloading) (e.currentTarget as HTMLButtonElement).style.background = 'rgba(0,201,167,0.2)'; }}
              onMouseLeave={(e) => { if (!downloading) (e.currentTarget as HTMLButtonElement).style.background = T.accentDim; }}
            >
              {downloading ? (
                <>
                  <span style={{
                    width: 11, height: 11,
                    border: `2px solid ${T.muted}`, borderTopColor: T.accent,
                    borderRadius: '50%', animation: 'cm-spin 0.7s linear infinite',
                    display: 'inline-block',
                  }} />
                  Downloading…
                </>
              ) : (
                <>
                  <DownloadIcon />
                  Download Clip
                </>
              )}
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
              transition: 'background 0.15s, color 0.15s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.color = T.text;
              (e.currentTarget as HTMLButtonElement).style.background = T.faint;
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.color = T.muted;
              (e.currentTarget as HTMLButtonElement).style.background = isSelected ? T.faint : 'transparent';
            }}
          >
            {isSelected ? '✓ Selected' : 'View Score'}
          </button>
          
          <button
            onClick={handleCapcutBridge}
            disabled={exportingCapcut}
            title="Download Raw MP4 + synced SRT for CapCut/Premiere"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 7,
              padding: '8px 14px',
              background: 'transparent',
              border: `1px solid ${T.faint}`,
              borderRadius: 8,
              color: T.muted,
              fontSize: 12, fontWeight: 500,
              cursor: exportingCapcut ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
            }}
            onMouseEnter={(e) => { if(!exportingCapcut) (e.currentTarget as HTMLButtonElement).style.borderColor = T.purple; (e.currentTarget as HTMLButtonElement).style.color = T.purple; }}
            onMouseLeave={(e) => { if(!exportingCapcut) (e.currentTarget as HTMLButtonElement).style.borderColor = T.faint; (e.currentTarget as HTMLButtonElement).style.color = T.muted; }}
          >
            {exportingCapcut ? 'Zipping...' : 'CapCut Bridge'}
          </button>
        </div>

        {/* Download error */}
        {dlError && (
          <p style={{ fontSize: 11, color: T.red, margin: 0 }}>{dlError}</p>
        )}
      </div>
    </div>
  );
}

/* ─── Main Component ───────────────────────────────────────── */

export default function ClipTimelineEditor({ jobId, userId }: ClipTimelineEditorProps) {
  const [preview, setPreview] = useState<ClipPreviewData | null>(null);
  const [regenerations, setRegenerations] = useState<RegenerationResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [selectedIdx, setSelectedIdx] = useState<number>(0);
  const [customInstructions, setCustomInstructions] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showTranscript, setShowTranscript] = useState(false);
  const [customWeights, setCustomWeights] = useState({
    hook_score: 0.2,
    emotion_score: 0.2,
    clarity_score: 0.2,
    story_score: 0.2,
    virality_score: 0.2,
  });

  const [isDragging, setIsDragging] = useState(false);
  const [dragStartIdx, setDragStartIdx] = useState<number | null>(null);
  const [dragEndIdx, setDragEndIdx] = useState<number | null>(null);

  const [hookVariants, setHookVariants] = useState<Array<{ start_time: number; label: string; logic: string }>>([]);
  const [loadingHooks, setLoadingHooks] = useState(false);

  useEffect(() => { loadData(); }, [jobId]);

  useEffect(() => {
    if (preview && preview.current_clips.length > 0) {
      loadHookVariants(selectedIdx);
    }
  }, [selectedIdx, preview]);

  async function loadHookVariants(idx: number) {
    if (!preview) return;
    try {
      setLoadingHooks(true);
      const data = await getHookVariants(jobId, idx);
      setHookVariants(data.variants);
    } catch (err) {
      console.error('Failed to load hook variants', err);
    } finally {
      setLoadingHooks(false);
    }
  }

  async function handleSelectHook(startTime: number) {
    if (!preview) return;
    const nextClips = [...preview.current_clips];
    nextClips[selectedIdx] = { ...nextClips[selectedIdx], start_time: startTime };
    setPreview({ ...preview, current_clips: nextClips });
    // Note: This only updates UI locally. Boundary adjustment API will persist later if handle moved.
  }

  // Debouncing for transcript adjustment (Feature 3)
  useEffect(() => {
    if (!preview || !preview.current_clips[selectedIdx]) return;
    const clip = preview.current_clips[selectedIdx];
    
    // Check if bounds actually changed from original (simple check)
    // We fetch original bounds from the API in a real app, 
    // but here we just debounce the local state changes.
    const timer = setTimeout(async () => {
      try {
        await adjustClipBoundary(jobId, userId, selectedIdx, clip.start_time, clip.end_time);
        console.log('Boundary adjusted & re-render queued');
      } catch (err) {
        console.error('Debounced adjustment failed', err);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [preview?.current_clips[selectedIdx]?.start_time, preview?.current_clips[selectedIdx]?.end_time]);

  async function loadData() {
    try {
      setLoading(true);
      setError(null);
      const [p, r] = await Promise.all([
        getClipPreview(jobId),
        getRegenerations(jobId),
      ]);
      setPreview(p);
      setRegenerations(r.regenerations ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  }

  async function handleRegenerate() {
    if (!preview) return;
    try {
      setRegenerating(true);
      setError(null);
      await regenerateClips(
        jobId, userId,
        preview.current_clips.length,
        showAdvanced ? customWeights : undefined,
        customInstructions || undefined,
      );
      await new Promise((r) => setTimeout(r, 1200));
      await loadData();
      setCustomInstructions('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Regeneration failed');
    } finally {
      setRegenerating(false);
    }
  }

  function updateWeight(key: string, value: number) {
    const next = { ...customWeights, [key]: value };
    const sum = Object.values(next).reduce((a, b) => a + b, 0);
    const norm = Object.fromEntries(
      Object.entries(next).map(([k, v]) => [k, v / sum])
    ) as typeof customWeights;
    setCustomWeights(norm);
  }

  /* ── Loading ── */
  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 320, background: T.bg }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{
          width: 36, height: 36, margin: '0 auto 12px',
          border: `3px solid ${T.border}`, borderTopColor: T.accent,
          borderRadius: '50%', animation: 'cm-spin 0.7s linear infinite',
        }} />
        <p style={{ color: T.muted, fontSize: 13 }}>Loading Clip Studio…</p>
        <style>{`@keyframes cm-spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    </div>
  );

  /* ── Error ── */
  if (error || !preview) return (
    <div style={{
      background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)',
      borderRadius: 10, padding: '16px 20px', color: '#f87171', fontSize: 14,
    }}>
      {error ?? 'Failed to load preview'}
    </div>
  );

  const clips = preview.current_clips;
  const selectedClip = clips[selectedIdx] ?? null;
  const avgScore = clips.length
    ? clips.reduce((s, c) => s + c.final_score, 0) / clips.length
    : 0;

  return (
    <div style={{ fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif', color: T.text }}>

      {/* ── Stats bar ── */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 24 }}>
        {[
          { label: 'Clips Found',    value: clips.length.toString() },
          { label: 'Avg Score',      value: avgScore.toFixed(1) },
          { label: 'Regenerations',  value: preview.regeneration_count.toString() },
        ].map(({ label, value }) => (
          <div key={label} style={{
            background: T.card, border: `1px solid ${T.border}`,
            borderRadius: 10, padding: '10px 18px',
            display: 'flex', flexDirection: 'column', gap: 2,
          }}>
            <span style={{ fontSize: 20, fontWeight: 700, fontFamily: 'monospace', color: T.accent }}>
              {value}
            </span>
            <span style={{ fontSize: 11, color: T.muted, letterSpacing: '0.06em' }}>{label.toUpperCase()}</span>
          </div>
        ))}
      </div>

      {/* ── Error banner ── */}
      {error && (
        <div style={{
          background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.25)',
          borderRadius: 8, padding: '10px 14px', color: '#f87171', fontSize: 13, marginBottom: 16,
        }}>
          {error}
        </div>
      )}

      {/* ── Main two-column layout ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 320px', gap: 20, alignItems: 'start' }}>

        {/* LEFT: Clip list */}
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: T.muted, letterSpacing: '0.1em', margin: '0 0 14px 0' }}>
            DETECTED CLIPS ({clips.length})
          </h3>

          {clips.length === 0 ? (
            <div style={{
              background: T.card, border: `1px solid ${T.border}`, borderRadius: 12,
              padding: 32, textAlign: 'center',
            }}>
              <div style={{ fontSize: 32, marginBottom: 10 }}>🔍</div>
              <p style={{ color: T.muted, fontSize: 14 }}>
                No clips detected. Try regenerating with different settings.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {clips.map((clip, idx) => {
                const clipNum = (clip as any).clip_index ?? idx + 1;
                return (
                  <ClipCard
                    key={idx}
                    clip={clip as Clip}
                    clipNum={clipNum}
                    jobId={jobId}
                    isSelected={selectedIdx === idx}
                    onSelect={() => setSelectedIdx(idx)}
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* RIGHT: Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, position: 'sticky', top: 20 }}>

          {/* Hook A/B Variants */}
          {selectedClip && (
            <div style={{
              background: T.card, border: `1px solid ${T.border}`,
              borderRadius: 14, padding: 20,
            }}>
              <h3 style={{ fontSize: 11, fontWeight: 700, color: T.muted, letterSpacing: '0.1em', margin: '0 0 12px 0' }}>
                HOOK A/B TESTING (AI)
              </h3>
              
              {loadingHooks ? (
                <div style={{ padding: '12px 0', textAlign: 'center', color: T.faint, fontSize: 12 }}>
                  Analyzing alternative hooks...
                </div>
              ) : hookVariants.length === 0 ? (
                <div style={{ fontSize: 12, color: T.muted }}>No alternative hooks found for this segment.</div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {hookVariants.map((v, i) => {
                    const isActive = Math.abs(selectedClip.start_time - v.start_time) < 0.1;
                    return (
                      <button
                        key={i}
                        onClick={() => handleSelectHook(v.start_time)}
                        style={{
                          textAlign: 'left', padding: '10px 12px', borderRadius: 8,
                          background: isActive ? T.accentDim : '#0d0e14',
                          border: `1px solid ${isActive ? T.accentBdr : T.faint}`,
                          cursor: 'pointer', transition: 'all 0.15s',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                          <span style={{ fontSize: 12, fontWeight: 700, color: isActive ? T.accent : T.text }}>
                            Hook {String.fromCharCode(65 + i)}
                          </span>
                          <span style={{ fontSize: 11, fontFamily: 'monospace', color: T.muted }}>
                            T+{v.start_time.toFixed(1)}s
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: T.muted, lineHeight: 1.4 }}>
                          {v.logic}
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Score breakdown */}
          {selectedClip && (
            <div style={{
              background: T.card, border: `1px solid ${T.border}`,
              borderRadius: 14, padding: 20,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h3 style={{ fontSize: 13, fontWeight: 600, color: T.muted, letterSpacing: '0.08em', margin: 0 }}>
                  CLIP BREAKDOWN
                </h3>
                <span style={{ fontSize: 11, color: T.muted, fontFamily: 'monospace', background: T.faint, padding: '2px 8px', borderRadius: 4 }}>
                  #{String((selectedClip as any).clip_index ?? selectedIdx + 1).padStart(2, '0')}
                </span>
              </div>

              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 16 }}>
                <ScoreRadar
                  hookScore={selectedClip.hook_score}
                  emotionScore={selectedClip.emotion_score}
                  clarityScore={selectedClip.clarity_score}
                  storyScore={selectedClip.story_score}
                  viralityScore={selectedClip.virality_score}
                  size={160}
                />
              </div>

              <div>
                {SCORE_DIMS.map(({ key, label }) => (
                  <ScoreBar key={key} label={label} score={(selectedClip as any)[key] ?? 0} />
                ))}
              </div>

              <div style={{
                marginTop: 14, paddingTop: 14, borderTop: `1px solid ${T.faint}`,
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                <span style={{ fontSize: 12, color: T.muted }}>Overall Score</span>
                <span style={{
                  fontSize: 22, fontWeight: 800, fontFamily: 'monospace',
                  color: scoreColor(selectedClip.final_score),
                }}>
                  {fmt(selectedClip.final_score)}
                </span>
              </div>
            </div>
          )}

          {/* Regeneration controls */}
          <div style={{
            background: T.card, border: `1px solid ${T.border}`,
            borderRadius: 14, padding: 20,
          }}>
            <h3 style={{ fontSize: 13, fontWeight: 600, color: T.muted, letterSpacing: '0.08em', margin: '0 0 16px 0' }}>
              FIND MORE CLIPS
            </h3>

            <label style={{ fontSize: 12, color: T.muted, display: 'block', marginBottom: 8 }}>
              Custom Instructions
            </label>
            <textarea
              value={customInstructions}
              onChange={(e) => setCustomInstructions(e.target.value)}
              placeholder={'e.g., "Focus on moments with music" or "Find longer clips"'}
              disabled={regenerating}
              rows={3}
              style={{
                width: '100%', boxSizing: 'border-box',
                background: '#0d0e14', border: `1px solid ${T.borderHi}`,
                borderRadius: 8, padding: '10px 12px',
                color: T.text, fontSize: 13, resize: 'vertical',
                outline: 'none', fontFamily: 'inherit',
                marginBottom: 12, transition: 'border-color 0.15s',
              }}
              onFocus={(e) => (e.currentTarget.style.borderColor = T.accentBdr)}
              onBlur={(e) => (e.currentTarget.style.borderColor = T.borderHi)}
            />

            <button
              onClick={() => setShowAdvanced(!showAdvanced)}
              style={{
                background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                color: T.accent, fontSize: 12, fontWeight: 600,
                display: 'flex', alignItems: 'center', gap: 6,
                marginBottom: 12, letterSpacing: '0.04em',
              }}
            >
              <span style={{
                fontSize: 9, display: 'inline-block',
                transform: showAdvanced ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 0.2s',
              }}>▶</span>
              Advanced Weight Settings
            </button>

            {showAdvanced && (
              <div style={{
                background: '#0d0e14', border: `1px solid ${T.faint}`,
                borderRadius: 8, padding: 14, marginBottom: 14,
              }}>
                {Object.entries(customWeights).map(([key, val]) => {
                  const label = key.replace('_score', '').replace('_', ' ')
                    .split(' ').map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
                  return (
                    <div key={key} style={{ marginBottom: 10 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                        <span style={{ fontSize: 11, color: T.muted }}>{label}</span>
                        <span style={{ fontSize: 11, fontFamily: 'monospace', color: T.text }}>
                          {(val * 100).toFixed(0)}%
                        </span>
                      </div>
                      <input
                        type="range" min={0} max={1} step={0.01} value={val}
                        onChange={(e) => updateWeight(key, parseFloat(e.target.value))}
                        disabled={regenerating}
                        style={{ width: '100%', accentColor: T.accent }}
                      />
                    </div>
                  );
                })}
              </div>
            )}

            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              style={{
                width: '100%', padding: '11px 0',
                background: regenerating ? T.faint : T.accent,
                border: 'none', borderRadius: 9,
                color: regenerating ? T.muted : '#07080d',
                fontSize: 14, fontWeight: 700,
                cursor: regenerating ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s, opacity 0.15s',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
              }}
              onMouseEnter={(e) => { if (!regenerating) (e.currentTarget as HTMLButtonElement).style.opacity = '0.88'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.opacity = '1'; }}
            >
              {regenerating ? (
                <>
                  <span style={{
                    width: 14, height: 14, border: `2px solid ${T.muted}`,
                    borderTopColor: T.text, borderRadius: '50%',
                    animation: 'cm-spin 0.7s linear infinite', display: 'inline-block',
                  }} />
                  Regenerating…
                </>
              ) : 'Regenerate Clips'}
            </button>

            {preview.regeneration_count > 0 && (
              <p style={{ fontSize: 11, color: T.muted, textAlign: 'center', margin: '10px 0 0' }}>
                {preview.regeneration_count} regeneration(s) on record
              </p>
            )}
          </div>

          {/* Tips */}
          <div style={{
            background: 'rgba(124,106,247,0.07)', border: '1px solid rgba(124,106,247,0.2)',
            borderRadius: 14, padding: 16,
          }}>
            <p style={{ fontSize: 11, fontWeight: 700, color: T.purple, letterSpacing: '0.08em', margin: '0 0 10px 0' }}>
              💡 TIPS
            </p>
            <ul style={{ fontSize: 12, color: T.muted, lineHeight: 1.7, paddingLeft: 16, margin: 0 }}>
              <li>Use natural language to guide detection</li>
              <li>Adjust weights to prioritise specific aspects</li>
              <li>3–5 word instructions work best</li>
              <li>Compare regenerations to find the best cuts</li>
            </ul>
          </div>

          {/* Recent regenerations */}
          {regenerations.length > 0 && (
            <div style={{
              background: T.card, border: `1px solid ${T.border}`,
              borderRadius: 14, padding: 16,
            }}>
              <p style={{ fontSize: 11, fontWeight: 600, color: T.muted, letterSpacing: '0.08em', margin: '0 0 12px 0' }}>
                RECENT REGENERATIONS
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 200, overflowY: 'auto' }}>
                {regenerations.slice(0, 5).map((r) => (
                  <div key={r.regen_id} style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    background: '#0d0e14', borderRadius: 7, padding: '8px 11px',
                  }}>
                    <div>
                      <p style={{ fontSize: 12, color: T.text, margin: 0 }}>{r.clips.length} clip(s)</p>
                      <p style={{ fontSize: 11, color: T.muted, margin: 0 }}>
                        {new Date(r.completed_at).toLocaleDateString()}
                      </p>
                    </div>
                    <span style={{
                      fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', padding: '2px 8px', borderRadius: 99,
                      ...(r.status === 'completed'
                        ? { background: 'rgba(0,201,167,0.1)', color: T.accent }
                        : r.status === 'failed'
                        ? { background: 'rgba(239,68,68,0.1)', color: T.red }
                        : { background: 'rgba(245,158,11,0.1)', color: T.amber }),
                    }}>
                      {r.status.toUpperCase()}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Transcript (collapsible) ── */}
      <div style={{ marginTop: 24 }}>
        <button
          onClick={() => setShowTranscript(!showTranscript)}
          style={{
            background: T.card, border: `1px solid ${T.border}`, borderRadius: 10,
            padding: '12px 18px', width: '100%', cursor: 'pointer',
            color: T.muted, fontSize: 13, fontWeight: 600,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            letterSpacing: '0.06em',
          }}
        >
          <span>TRANSCRIPT TIMELINE</span>
          <span style={{ fontSize: 11, transform: showTranscript ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}>▼</span>
        </button>

        {showTranscript && (
          <div 
            onMouseLeave={() => {
              if (isDragging) setIsDragging(false);
            }}
            style={{
              background: T.card, border: `1px solid ${T.border}`, borderRadius: '0 0 12px 12px',
              borderTop: 'none', padding: 20, marginTop: -1,
              maxHeight: 260, overflowY: 'auto',
              lineHeight: 1.9, fontSize: 14,
              userSelect: 'none', // Prevent text selection during drag
            }}
          >
            {preview.transcript_words.length === 0 ? (
              <p style={{ color: T.muted, fontSize: 13 }}>No transcript available.</p>
            ) : (
              preview.transcript_words.map((w, i) => {
                let inSelected = selectedClip
                  && w.start >= selectedClip.start_time
                  && w.end <= selectedClip.end_time;
                
                // If dragging, override visual selection to show pending drag
                if (isDragging && dragStartIdx !== null && dragEndIdx !== null) {
                  const min = Math.min(dragStartIdx, dragEndIdx);
                  const max = Math.max(dragStartIdx, dragEndIdx);
                  inSelected = i >= min && i <= max;
                }

                const inAny = clips.some((c) => w.start >= c.start_time && w.end <= c.end_time);
                
                const isStart = selectedClip && Math.abs(w.start - selectedClip.start_time) < 0.2;
                const isEnd = selectedClip && Math.abs(w.end - selectedClip.end_time) < 0.2;

                return (
                  <span
                    key={i}
                    onMouseDown={(e) => {
                      if (!preview || !selectedClip) return;
                      setIsDragging(true);
                      setDragStartIdx(i);
                      setDragEndIdx(i);
                    }}
                    onMouseEnter={() => {
                      if (isDragging) {
                        setDragEndIdx(i);
                      }
                    }}
                    onMouseUp={() => {
                      if (isDragging && dragStartIdx !== null) {
                        const nextClips = [...preview.current_clips];
                        const clip = nextClips[selectedIdx];
                        
                        const min = Math.min(dragStartIdx, i);
                        const max = Math.max(dragStartIdx, i);
                        
                        clip.start_time = preview.transcript_words[min].start;
                        clip.end_time = preview.transcript_words[max].end;
                        
                        setPreview({ ...preview, current_clips: nextClips });
                        setIsDragging(false);
                        setDragStartIdx(null);
                        setDragEndIdx(null);
                      }
                    }}
                    title={`${fmt(w.start)}s – ${fmt((w as any).end ?? w.start)}s`}
                    style={{
                      display: 'inline-block', margin: '2px 2px',
                      padding: '1px 4px', borderRadius: 3,
                      cursor: 'pointer',
                      background: inSelected ? T.accentDim : inAny ? 'rgba(0,201,167,0.07)' : 'transparent',
                      color: inSelected ? T.accent : inAny ? '#5ecfbb' : T.muted,
                      fontWeight: inSelected ? 600 : 400,
                      borderLeft: isStart && !isDragging ? `2px solid ${T.accent}` : 'none',
                      borderRight: isEnd && !isDragging ? `2px solid ${T.accent}` : 'none',
                      transition: 'background 0.1s, border 0.1s',
                    }}
                  >
                    {w.word}
                  </span>
                );
              })
            )}
          </div>
        )}
      </div>

      <style>{`
        @keyframes cm-spin { to { transform: rotate(360deg); } }
        textarea::placeholder { color: ${T.muted}; opacity: 0.7; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: ${T.faint}; border-radius: 99px; }
      `}</style>
    </div>
  );
}