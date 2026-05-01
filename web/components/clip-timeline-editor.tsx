'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';

interface Clip {
  id: string;
  start: number;   // seconds
  end: number;
  score: number;
  label: string;
  selected: boolean;
}

interface Props {
  duration?: number;   // total video seconds
  clips?: Clip[];
  onClipsChange?: (clips: Clip[]) => void;
}

const DEMO_CLIPS: Clip[] = [
  { id: 'c1', start: 12,  end: 45,  score: 92, label: 'Strong hook',        selected: true  },
  { id: 'c2', start: 78,  end: 108, score: 74, label: 'Key insight',        selected: true  },
  { id: 'c3', start: 145, end: 185, score: 88, label: 'Viral moment',       selected: true  },
  { id: 'c4', start: 210, end: 238, score: 61, label: 'Product mention',    selected: false },
  { id: 'c5', start: 270, end: 312, score: 85, label: 'Emotional peak',     selected: true  },
];

const WAVEFORM = Array.from({ length: 120 }, (_, i) =>
  0.15 + 0.85 * Math.abs(Math.sin(i * 0.3 + 1) * Math.cos(i * 0.15) * 0.8 + Math.sin(i * 0.07) * 0.2)
);

function scoreColor(s: number) {
  if (s >= 85) return { bg: 'var(--green-dim)',  border: 'rgba(16,185,129,0.35)', text: 'var(--green)' };
  if (s >= 70) return { bg: 'var(--amber-dim)',  border: 'rgba(245,158,11,0.35)', text: 'var(--amber)' };
  return                { bg: 'var(--red-dim)',   border: 'rgba(244,63,94,0.35)',  text: 'var(--red)'   };
}

function formatTime(s: number) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

const Icon = ({ d, size = 16 }: { d: string; size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

export default function ClipTimelineEditor({
  duration = 360,
  clips: initialClips = DEMO_CLIPS,
  onClipsChange,
}: Props) {
  const [clips, setClips] = useState<Clip[]>(initialClips);
  const [selectedClip, setSelectedClip] = useState<string | null>('c1');
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const [zoom, setZoom] = useState(1);

  const timelineRef = useRef<HTMLDivElement>(null);
  const playIntervalRef = useRef<ReturnType<typeof setInterval>>();

  const TRACK_H = 52;

  /* ── Playback ── */
  const togglePlay = useCallback(() => setPlaying(p => !p), []);

  useEffect(() => {
    if (playing) {
      playIntervalRef.current = setInterval(() => {
        setPlayhead(p => {
          if (p >= duration) { setPlaying(false); return 0; }
          return p + 0.25;
        });
      }, 250);
    } else {
      clearInterval(playIntervalRef.current);
    }
    return () => clearInterval(playIntervalRef.current);
  }, [playing, duration]);

  /* ── Keyboard shortcuts ── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA') return;
      switch (e.key) {
        case ' ':  e.preventDefault(); togglePlay(); break;
        case 'j':  setPlayhead(p => Math.max(0, p - 5)); break;
        case 'k':  togglePlay(); break;
        case 'l':  setPlayhead(p => Math.min(duration, p + 5)); break;
        case 'ArrowLeft':  setPlayhead(p => Math.max(0, p - 1)); break;
        case 'ArrowRight': setPlayhead(p => Math.min(duration, p + 1)); break;
        case '?':  setShowShortcuts(p => !p); break;
        case 'Escape': setShowShortcuts(false); break;
        case 'Delete':
        case 'Backspace':
          if (selectedClip) {
            setClips(cs => cs.filter(c => c.id !== selectedClip));
            setSelectedClip(null);
          }
          break;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [togglePlay, selectedClip, duration]);

  /* ── Timeline click → move playhead ── */
  const onTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    setPlayhead(Math.max(0, Math.min(duration, ratio * duration)));
  };

  /* ── Toggle clip selection ── */
  const toggleClipSelect = (id: string) => {
    setClips(cs => cs.map(c => c.id === id ? { ...c, selected: !c.selected } : c));
  };

  /* ── Natural-language regeneration ── */
  const handlePromptSubmit = async () => {
    if (!prompt.trim()) return;
    setPromptLoading(true);
    await new Promise(r => setTimeout(r, 1800));
    // Simulate new clip from AI
    const newClip: Clip = {
      id: 'c' + Date.now(),
      start: Math.floor(Math.random() * (duration - 60)),
      end: 0,
      score: 70 + Math.floor(Math.random() * 28),
      label: `AI: "${prompt.slice(0, 28)}…"`,
      selected: true,
    };
    newClip.end = newClip.start + 25 + Math.floor(Math.random() * 30);
    setClips(cs => [...cs, newClip]);
    setSelectedClip(newClip.id);
    setPrompt('');
    setPromptLoading(false);
  };

  const selectedClipData = clips.find(c => c.id === selectedClip);
  const playheadPct = (playhead / duration) * 100;

  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-xl)', overflow: 'hidden', userSelect: 'none',
    }}>

      {/* ── Video preview area ── */}
      <div style={{
        background: '#000', aspectRatio: '16/9', maxHeight: 240,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        position: 'relative',
      }}>
        <div style={{ color: 'var(--text-tertiary)', textAlign: 'center' }}>
          <Icon d="M15 10l4.553-2.069A1 1 0 0121 8.882v6.236a1 1 0 01-1.447.894L15 14M3 8a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" size={32} />
          <p style={{ marginTop: 8, fontSize: 12 }}>Video preview</p>
        </div>
        {/* Playhead time overlay */}
        <div style={{
          position: 'absolute', bottom: 12, right: 12,
          background: 'rgba(0,0,0,0.75)', padding: '4px 10px',
          borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)',
          fontSize: 13, color: '#fff', backdropFilter: 'blur(4px)',
        }}>
          {formatTime(playhead)} / {formatTime(duration)}
        </div>
        {/* Selected clip score overlay */}
        {selectedClipData && (
          <div style={{
            position: 'absolute', top: 12, left: 12,
            background: 'rgba(0,0,0,0.75)', padding: '6px 10px',
            borderRadius: 'var(--radius-md)', backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', gap: 8,
          }}>
            <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.6)' }}>Selected clip</span>
            <span style={{
              fontSize: 13, fontFamily: 'var(--font-mono)', fontWeight: 600,
              color: scoreColor(selectedClipData.score).text,
            }}>
              {selectedClipData.score}
            </span>
          </div>
        )}
      </div>

      {/* ── Playback controls ── */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '12px',
        padding: '12px 20px', borderBottom: '1px solid var(--border)',
      }}>
        <button onClick={() => setPlayhead(0)} title="Rewind (J)" style={btnStyle}>
          <Icon d="M19 20L9 12l10-8v16zM5 19V5" size={15} />
        </button>
        <button onClick={() => setPlayhead(p => Math.max(0, p - 5))} title="Back 5s (←)" style={btnStyle}>
          <Icon d="M11 17l-5-5 5-5M18 17l-5-5 5-5" size={15} />
        </button>
        <button onClick={togglePlay} title="Play/Pause (Space)" style={{
          ...btnStyle,
          width: 40, height: 40,
          background: 'var(--accent)',
          color: '#fff',
          borderRadius: '50%',
        }}>
          {playing
            ? <Icon d="M6 4h4v16H6V4zM14 4h4v16h-4V4z" size={16} />
            : <Icon d="M5 3l14 9-14 9V3z" size={16} />
          }
        </button>
        <button onClick={() => setPlayhead(p => Math.min(duration, p + 5))} title="Forward 5s (→)" style={btnStyle}>
          <Icon d="M13 17l5-5-5-5M6 17l5-5-5-5" size={15} />
        </button>

        <div style={{ flex: 1 }} />

        {/* Zoom */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ fontSize: 11, color: 'var(--text-tertiary)' }}>Zoom</span>
          <input type="range" min={1} max={4} step={0.5} value={zoom}
            onChange={e => setZoom(Number(e.target.value))}
            style={{ width: 64 }}
          />
          <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', minWidth: 24 }}>
            {zoom}×
          </span>
        </div>

        <button
          onClick={() => setShowShortcuts(p => !p)}
          title="Keyboard shortcuts (?)"
          style={{ ...btnStyle, fontSize: 12, width: 26, height: 26 }}
        >
          ?
        </button>
      </div>

      {/* ── Timeline ── */}
      <div style={{ padding: '16px 20px' }}>

        {/* Time ruler */}
        <div style={{ position: 'relative', height: 20, marginBottom: 4, overflow: 'hidden' }}>
          {Array.from({ length: Math.ceil(duration / 30) + 1 }).map((_, i) => {
            const t = i * 30;
            const pct = (t / duration) * 100;
            return (
              <span key={i} style={{
                position: 'absolute', left: `${pct}%`,
                fontSize: 10, fontFamily: 'var(--font-mono)',
                color: 'var(--text-tertiary)', transform: 'translateX(-50%)',
              }}>
                {formatTime(t)}
              </span>
            );
          })}
        </div>

        {/* Main track */}
        <div
          ref={timelineRef}
          onClick={onTimelineClick}
          style={{
            position: 'relative',
            height: TRACK_H,
            background: 'var(--bg-elevated)',
            borderRadius: 'var(--radius-md)',
            cursor: 'crosshair',
            overflow: 'hidden',
            marginBottom: 8,
          }}
        >
          {/* Grid lines */}
          {Array.from({ length: Math.ceil(duration / 30) }).map((_, i) => (
            <div key={i} style={{
              position: 'absolute', top: 0, bottom: 0,
              left: `${((i + 1) * 30 / duration) * 100}%`,
              width: 1, background: 'var(--border)',
            }} />
          ))}

          {/* Clip segments */}
          {clips.map((clip) => {
            const left = (clip.start / duration) * 100;
            const width = ((clip.end - clip.start) / duration) * 100;
            const col = scoreColor(clip.score);
            const isSel = clip.id === selectedClip;
            return (
              <div
                key={clip.id}
                onClick={(e) => { e.stopPropagation(); setSelectedClip(clip.id); setPlayhead(clip.start); }}
                style={{
                  position: 'absolute', top: 6, bottom: 6,
                  left: `${left}%`, width: `${width}%`,
                  background: clip.selected ? col.bg : 'var(--bg-overlay)',
                  border: `1.5px solid ${isSel ? col.text : (clip.selected ? col.border : 'var(--border)')}`,
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer', overflow: 'hidden',
                  transition: 'border-color 0.15s, box-shadow 0.15s',
                  boxShadow: isSel ? `0 0 0 2px ${col.text}33` : 'none',
                  display: 'flex', alignItems: 'center',
                  paddingLeft: 6,
                }}
              >
                {width > 4 && (
                  <>
                    <span style={{
                      fontSize: 9, fontFamily: 'var(--font-mono)', fontWeight: 600,
                      color: col.text, marginRight: 4, flexShrink: 0,
                    }}>
                      {clip.score}
                    </span>
                    {width > 8 && (
                      <span style={{
                        fontSize: 9, color: 'var(--text-secondary)',
                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                      }}>
                        {clip.label}
                      </span>
                    )}
                  </>
                )}
              </div>
            );
          })}

          {/* Playhead */}
          <div style={{
            position: 'absolute', top: 0, bottom: 0,
            left: `${playheadPct}%`,
            width: 2, background: 'var(--accent)',
            pointerEvents: 'none', zIndex: 10,
          }}>
            <div style={{
              position: 'absolute', top: -4, left: '50%', transform: 'translateX(-50%)',
              width: 8, height: 8, background: 'var(--accent)', borderRadius: '50%',
            }} />
          </div>
        </div>

        {/* Waveform */}
        <div style={{
          height: 36, background: 'var(--bg-elevated)',
          borderRadius: 'var(--radius-md)', overflow: 'hidden',
          position: 'relative', cursor: 'pointer',
        }}
        onClick={onTimelineClick}
        >
          <svg width="100%" height="100%" viewBox={`0 0 ${WAVEFORM.length} 1`}
            preserveAspectRatio="none" style={{ display: 'block' }}>
            {WAVEFORM.map((h, i) => (
              <rect
                key={i}
                x={i}
                y={(1 - h) / 2}
                width={0.7}
                height={h}
                fill={i / WAVEFORM.length < playheadPct / 100 ? 'var(--accent)' : 'var(--border-strong)'}
              />
            ))}
          </svg>
          {/* Playhead on waveform */}
          <div style={{
            position: 'absolute', top: 0, bottom: 0,
            left: `${playheadPct}%`,
            width: 1.5, background: 'var(--accent)',
            pointerEvents: 'none',
          }} />
        </div>
      </div>

      {/* ── Selected clip detail ── */}
      {selectedClipData && (
        <div style={{
          borderTop: '1px solid var(--border)', padding: '14px 20px',
          display: 'flex', alignItems: 'center', gap: '16px',
          background: 'var(--bg-elevated)',
        }}>
          <div style={{
            width: 36, height: 36, borderRadius: 'var(--radius-md)',
            background: scoreColor(selectedClipData.score).bg,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <span style={{
              fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 600,
              color: scoreColor(selectedClipData.score).text,
            }}>
              {selectedClipData.score}
            </span>
          </div>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 13, fontWeight: 500, marginBottom: 2 }}>{selectedClipData.label}</p>
            <p style={{ fontSize: 11, color: 'var(--text-tertiary)', fontFamily: 'var(--font-mono)' }}>
              {formatTime(selectedClipData.start)} → {formatTime(selectedClipData.end)}
              &nbsp;· {Math.round(selectedClipData.end - selectedClipData.start)}s
            </p>
          </div>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              onClick={() => toggleClipSelect(selectedClipData.id)}
              style={{
                padding: '6px 12px', fontSize: 12, fontWeight: 500,
                background: selectedClipData.selected ? 'var(--accent-dim)' : 'var(--bg-overlay)',
                color: selectedClipData.selected ? 'var(--accent)' : 'var(--text-secondary)',
                border: `1px solid ${selectedClipData.selected ? 'rgba(20,184,166,0.3)' : 'var(--border)'}`,
                borderRadius: 'var(--radius-md)', cursor: 'pointer', transition: 'all 0.15s',
              }}
            >
              {selectedClipData.selected ? '✓ Included' : '+ Include'}
            </button>
            <a href={`/clips/${selectedClipData.id}/export`} style={{
              padding: '6px 12px', fontSize: 12, fontWeight: 500,
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              color: 'var(--text-primary)', borderRadius: 'var(--radius-md)',
              textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 5,
            }}>
              <Icon d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" size={13} />
              Export
            </a>
          </div>
        </div>
      )}

      {/* ── Natural-language prompt ── */}
      <div style={{ padding: '14px 20px', borderTop: '1px solid var(--border)' }}>
        <div style={{
          display: 'flex', gap: '8px', alignItems: 'center',
          background: 'var(--bg-elevated)', border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)', padding: '4px 4px 4px 14px',
          transition: 'border-color 0.2s',
        }}
        onFocus={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--accent)'; }}
        onBlur={(e) => { (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)'; }}
        >
          <svg width={14} height={14} viewBox="0 0 24 24" fill="none"
            stroke="var(--accent)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0 }}>
            <path d="M9.5 2A2.5 2.5 0 0112 4.5v15a2.5 2.5 0 01-4.96-.44 2.5 2.5 0 01-2.96-3.08 3 3 0 01-.34-5.58 2.5 2.5 0 013.32-3.97A2.5 2.5 0 019.5 2z" />
          </svg>
          <input
            type="text"
            placeholder='Find moments where… e.g. "the host laughs" or "product demo"'
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handlePromptSubmit(); }}
            style={{
              flex: 1, background: 'none', border: 'none', outline: 'none',
              fontSize: 13, color: 'var(--text-primary)', fontFamily: 'var(--font-body)',
              padding: '8px 0',
            }}
          />
          <button
            onClick={handlePromptSubmit}
            disabled={!prompt.trim() || promptLoading}
            style={{
              padding: '7px 14px', background: prompt.trim() ? 'var(--accent)' : 'var(--bg-overlay)',
              border: 'none', borderRadius: 'var(--radius-md)', color: prompt.trim() ? '#fff' : 'var(--text-tertiary)',
              fontSize: 12, fontWeight: 500, cursor: 'pointer', flexShrink: 0,
              transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: 5,
            }}
          >
            {promptLoading ? (
              <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
                className="animate-spin" strokeLinecap="round">
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4" />
              </svg>
            ) : (
              <Icon d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" size={12} />
            )}
            Find
          </button>
        </div>
      </div>

      {/* ── Keyboard shortcuts modal ── */}
      {showShortcuts && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
          backdropFilter: 'blur(4px)', zIndex: 100,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
        onClick={() => setShowShortcuts(false)}
        >
          <div style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius-xl)', padding: '28px',
            width: 340, maxWidth: '90vw',
          }}
          onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 600 }}>Keyboard shortcuts</h3>
              <button onClick={() => setShowShortcuts(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', padding: 4 }}>
                <Icon d="M18 6L6 18M6 6l12 12" size={15} />
              </button>
            </div>
            {[
              ['Space / K', 'Play / pause'],
              ['J', 'Back 5 seconds'],
              ['L', 'Forward 5 seconds'],
              ['← / →', 'Back / forward 1 second'],
              ['Delete', 'Remove selected clip'],
              ['?', 'Toggle this dialog'],
            ].map(([key, label]) => (
              <div key={key} style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                padding: '8px 0', borderBottom: '1px solid var(--border-subtle)',
              }}>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{label}</span>
                <kbd style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)',
                  background: 'var(--bg-elevated)', border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-sm)', padding: '2px 8px',
                  color: 'var(--text-primary)',
                }}>
                  {key}
                </kbd>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  width: 32, height: 32, background: 'var(--bg-elevated)', border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)', cursor: 'pointer', color: 'var(--text-secondary)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.15s',
  flexShrink: 0,
};
