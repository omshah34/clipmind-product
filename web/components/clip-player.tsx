/**
 * File: components/clip-player.tsx
 * Purpose: Standalone video player with download button.
 *          Used by ClipList on the job status page.
 *          Gap 216: Handled video decode/network exceptions.
 */

'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { downloadClip } from '@/lib/api';

type ClipPlayerProps = {
  clipUrl: string;
  jobId: string;
  clipIndex: number;   // 0-based clip index used by the API
  onTimeUpdate?: (time: number) => void;
};

export default function ClipPlayer({ clipUrl, jobId, clipIndex, onTimeUpdate }: ClipPlayerProps) {
  const [copying, setCopying]     = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [dlError, setDlError]     = useState<string | null>(null);
  const [videoError, setVideoError] = useState<{ code: number; message: string } | null>(null);

  const isValid = !!clipUrl && clipUrl !== 'None' && clipUrl !== '' && !videoError;

  async function copyLink() {
    try {
      const fullUrl = clipUrl.startsWith('http') ? clipUrl : `${window.location.origin}${clipUrl}`;
      await navigator.clipboard.writeText(fullUrl);
      setCopying(true);
      setTimeout(() => setCopying(false), 1800);
    } catch { /* ignore */ }
  }

  async function handleDownload() {
    setDlError(null);
    try {
      await downloadClip(jobId, clipIndex, `clipmind-clip-${clipIndex + 1}.mp4`, () => setDownloading(true), () => setDownloading(false));
    } catch {
      setDownloading(false);
      setDlError('Download failed — please try again');
    }
  }

  // Gap 216: Discriminate between decode and network errors
  const handleVideoError = (e: React.SyntheticEvent<HTMLVideoElement, Event>) => {
    const error = (e.target as HTMLVideoElement).error;
    if (!error) return;

    let message = 'An unknown video error occurred.';
    if (error.code === 3) message = 'Unsupported format or decode error.';
    else if (error.code === 2) message = 'Network error while loading video.';
    else if (error.code === 4) message = 'Source not supported.';

    setVideoError({ code: error.code, message });
  };

  // Gap 354: Precision Scrubbing & rAF Playhead
  const videoRef = useRef<HTMLVideoElement>(null);
  const isSeeking = useRef(false);
  const pendingSeek = useRef<number | null>(null);
  const rafId = useRef<number>();

  const seekTo = useCallback((time: number) => {
    const video = videoRef.current;
    if (!video) return;

    if (isSeeking.current) {
      pendingSeek.current = time;
      return;
    }

    isSeeking.current = true;
    video.currentTime = time;
  }, []);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const onSeeked = () => {
      isSeeking.current = false;
      if (pendingSeek.current !== null) {
        const next = pendingSeek.current;
        pendingSeek.current = null;
        seekTo(next);
      }
    };

    const tick = () => {
      if (!video.paused && onTimeUpdate) {
        onTimeUpdate(video.currentTime);
      }
      rafId.current = requestAnimationFrame(tick);
    };
    rafId.current = requestAnimationFrame(tick);

    video.addEventListener("seeked", onSeeked);
    return () => {
      video.removeEventListener("seeked", onSeeked);
      if (rafId.current) cancelAnimationFrame(rafId.current);
    };
  }, [seekTo, onTimeUpdate]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{
        background: '#07080d', borderRadius: 10, overflow: 'hidden', border: '1px solid #22253a',
        aspectRatio: '9/16', maxHeight: 260, display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {isValid ? (
          <div style={{ width: "100%", height: "100%", isolation: "isolate", position: "relative" }}>
            <video
              ref={videoRef}
              controls
              playsInline
              preload="metadata"
              src={clipUrl}
              style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#07080d', display: "block" }}
              onError={handleVideoError}
            />
          </div>
        ) : (
          <div style={{ color: '#555870', fontSize: 12, textAlign: 'center', padding: 20 }}>
            {videoError ? (
              <>
                <p style={{ color: '#ef4444', marginBottom: 12 }}>{videoError.message}</p>
                {videoError.code === 2 && (
                  <button 
                    onClick={() => setVideoError(null)}
                    style={{ background: '#22253a', color: '#fff', border: 'none', padding: '6px 12px', borderRadius: 6, cursor: 'pointer' }}
                  >
                    Retry
                  </button>
                )}
              </>
            ) : (
              <>
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" style={{ marginBottom: 8 }}>
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
                <p style={{ margin: 0 }}>Processing…</p>
              </>
            )}
          </div>
        )}
      </div>

      {isValid && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              onClick={handleDownload}
              disabled={downloading}
              style={{
                flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, padding: '8px 0',
                background: downloading ? 'rgba(0,201,167,0.05)' : 'rgba(0,201,167,0.1)',
                border: '1px solid rgba(0,201,167,0.3)', borderRadius: 8, color: downloading ? '#3a9e8b' : '#00c9a7',
                fontSize: 13, fontWeight: 600, cursor: downloading ? 'not-allowed' : 'pointer', transition: 'all 0.15s',
              }}
            >
              {downloading ? 'Downloading…' : 'Download'}
            </button>
            <button
              onClick={copyLink}
              style={{ padding: '8px 12px', background: '#181a26', border: '1px solid #22253a', borderRadius: 8, color: copying ? '#00c9a7' : '#555870', fontSize: 12, cursor: 'pointer' }}
              title="Copy stream link"
            >
              {copying ? '✓' : '⎘'}
            </button>
          </div>
          {dlError && <p style={{ fontSize: 11, color: '#ef4444', margin: 0 }}>{dlError}</p>}
        </div>
      )}
    </div>
  );
}