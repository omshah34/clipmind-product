/**
 * File: components/clip-player.tsx
 * Purpose: Standalone video player with download button.
 *          Used by ClipList on the job status page.
 */

'use client';

import { useState } from 'react';
import { downloadClip } from '@/lib/api';

type ClipPlayerProps = {
  clipUrl: string;
  jobId: string;
  clipIndex: number;   // 0-based clip index used by the API
};

export default function ClipPlayer({ clipUrl, jobId, clipIndex }: ClipPlayerProps) {
  const [copying, setCopying]     = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [dlError, setDlError]     = useState<string | null>(null);

  // clipUrl is now the /stream proxy endpoint from the backend — always valid HTTP
  const isValid = !!clipUrl && clipUrl !== 'None' && clipUrl !== '';

  async function copyLink() {
    try {
      // Build the full URL for clipboard (clipUrl may be a relative path)
      const fullUrl = clipUrl.startsWith('http')
        ? clipUrl
        : `${window.location.origin}${clipUrl}`;
      await navigator.clipboard.writeText(fullUrl);
      setCopying(true);
      setTimeout(() => setCopying(false), 1800);
    } catch { /* ignore */ }
  }

  async function handleDownload() {
    setDlError(null);
    try {
      await downloadClip(
        jobId,
        clipIndex,
        `clipmind-clip-${clipIndex + 1}.mp4`,
        () => setDownloading(true),
        () => setDownloading(false),
      );
    } catch {
      setDownloading(false);
      setDlError('Download failed — please try again');
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{
        background: '#07080d',
        borderRadius: 10, overflow: 'hidden',
        border: '1px solid #22253a',
        aspectRatio: '9/16',
        maxHeight: 260,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        {isValid ? (
          <video
            controls
            playsInline
            preload="metadata"
            src={clipUrl}
            style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#07080d' }}
            onError={(e) => {
              console.error(`[ClipPlayer] Video failed to load: ${clipUrl}`, e);
            }}
          />
        ) : (
          <div style={{ color: '#333650', fontSize: 12, textAlign: 'center', padding: 16 }}>
            <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
              stroke="currentColor" strokeWidth="1.5" style={{ marginBottom: 8 }}>
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            <p style={{ margin: 0 }}>Processing…</p>
          </div>
        )}
      </div>

      {isValid && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ display: 'flex', gap: 8 }}>
            {/* Use fetch → blob download instead of <a download> — works cross-origin */}
            <button
              onClick={handleDownload}
              disabled={downloading}
              style={{
                flex: 1,
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                padding: '8px 0',
                background: downloading ? 'rgba(0,201,167,0.05)' : 'rgba(0,201,167,0.1)',
                border: '1px solid rgba(0,201,167,0.3)',
                borderRadius: 8,
                color: downloading ? '#3a9e8b' : '#00c9a7',
                fontSize: 13, fontWeight: 600,
                cursor: downloading ? 'not-allowed' : 'pointer',
                transition: 'background 0.15s, color 0.15s',
              }}
            >
              {downloading ? (
                <>
                  <span style={{
                    width: 11, height: 11,
                    border: '2px solid rgba(0,201,167,0.3)', borderTopColor: '#00c9a7',
                    borderRadius: '50%', animation: 'cp-spin 0.7s linear infinite',
                    display: 'inline-block',
                  }} />
                  Downloading…
                </>
              ) : (
                <>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
                    stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="7 10 12 15 17 10"/>
                    <line x1="12" y1="15" x2="12" y2="3"/>
                  </svg>
                  Download
                </>
              )}
            </button>

            <button
              onClick={copyLink}
              style={{
                padding: '8px 12px',
                background: '#181a26',
                border: '1px solid #22253a',
                borderRadius: 8,
                color: copying ? '#00c9a7' : '#555870',
                fontSize: 12, cursor: 'pointer',
                transition: 'color 0.15s',
              }}
              title="Copy stream link"
            >
              {copying ? '✓' : '⎘'}
            </button>
          </div>

          {dlError && (
            <p style={{ fontSize: 11, color: '#ef4444', margin: 0 }}>{dlError}</p>
          )}
        </div>
      )}

      <style>{`@keyframes cp-spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}