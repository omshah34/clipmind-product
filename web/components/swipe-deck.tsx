'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence, useMotionValue, useTransform } from 'framer-motion';
import { approveClip, discardClip, downloadCapcutBridge, type ClipPreviewData } from '@/lib/api';

type Clip = ClipPreviewData['current_clips'][number];

type SwipeDeckProps = {
  jobId: string;
  userId: string;
  clips: Clip[];
  onComplete: () => void;
};

const T = {
  bg: '#0d0e14',
  card: '#181a26',
  accent: '#00c9a7',
  red: '#ef4444',
  text: '#dde0f0',
  muted: '#555870',
  border: '#22253a',
};

export default function SwipeDeck({ jobId, userId, clips, onComplete }: SwipeDeckProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [results, setResults] = useState<{ approved: number; discarded: number }>({ approved: 0, discarded: 0 });
  const [exporting, setExporting] = useState(false);

  const currentClip = clips[currentIndex];

  const handleSwipe = (direction: 'left' | 'right') => {
    if (!currentClip) return;
    
    const clipIdx = currentClip.index || currentIndex;

    // ── Optimistic Update ──────────────────────────────────────────────
    // Immediately move to the next index without waiting for the API
    if (currentIndex < clips.length - 1) {
      setCurrentIndex(prev => prev + 1);
    } else {
      onComplete();
    }

    // Fire API call in the background
    const action = direction === 'right' ? approveClip : discardClip;
    action(jobId, clipIdx, userId)
      .then(() => {
        setResults(prev => ({
          ...prev,
          [direction === 'right' ? 'approved' : 'discarded']: prev[direction === 'right' ? 'approved' : 'discarded'] + 1
        }));
      })
      .catch(err => {
        console.error(`Swipe action failed for clip ${clipIdx}`, err);
        // Note: In a real production app, we might want to "rollback" or show a toast
        // but for a swipe deck, silent logging is often preferred for flow.
      });
  };

  if (!currentClip) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: T.text }}>
        <h2 style={{ fontSize: 24, fontWeight: 700 }}>Deck Complete!</h2>
        <p style={{ color: T.muted, marginTop: 12 }}>
          You approved {results.approved} clips and discarded {results.discarded}.
        </p>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 24 }}>
          <button 
            onClick={() => window.location.href = `/jobs/${jobId}/studio`}
            style={{
              padding: '12px 24px', background: 'transparent', border: `1px solid ${T.border}`, color: T.text,
              borderRadius: 8, fontWeight: 700, cursor: 'pointer'
            }}
          >
            Return to Studio
          </button>
          
          <button 
            disabled={exporting}
            onClick={async () => {
              try {
                // Export the last swiped clip as a bridge example, or just provide a generic bridge zip for the job
                // In this deck, we'll just download the bridge for the first approved clip or current context
                await downloadCapcutBridge(jobId, 0, `clipmind-deck-export.zip`, () => setExporting(true), () => setExporting(false));
              } catch (err) {
                console.error("Deck export failed", err);
              }
            }}
            style={{
              padding: '12px 24px', background: exporting ? T.muted : T.accent, color: '#000',
              borderRadius: 8, fontWeight: 700, border: 'none', cursor: exporting ? 'not-allowed' : 'pointer'
            }}
          >
            {exporting ? 'Zipping...' : 'Export to CapCut'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: 'calc(100vh - 100px)', display: 'flex', justifyContent: 'center', alignItems: 'center', overflow: 'hidden' }}>
      <AnimatePresence mode="popLayout">
        <SwipeCard 
          key={currentIndex}
          clip={currentClip}
          onSwipe={handleSwipe}
        />
      </AnimatePresence>
      
      {/* Progress bar */}
      <div style={{ position: 'absolute', bottom: 20, left: 20, right: 20, height: 4, background: T.border, borderRadius: 2 }}>
        <motion.div 
          initial={{ width: 0 }}
          animate={{ width: `${((currentIndex) / clips.length) * 100}%` }}
          style={{ height: '100%', background: T.accent, borderRadius: 2 }}
        />
      </div>
    </div>
  );
}

function SwipeCard({ clip, onSwipe }: { clip: Clip; onSwipe: (dir: 'left' | 'right') => void }) {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-200, 200], [-25, 25]);
  const opacity = useTransform(x, [-200, -150, 0, 150, 200], [0, 1, 1, 1, 0]);
  
  const approveOpacity = useTransform(x, [50, 150], [0, 1]);
  const discardOpacity = useTransform(x, [-150, -50], [1, 0]);

  const handleDragEnd = (event: any, info: any) => {
    if (info.offset.x > 100) {
      onSwipe('right');
    } else if (info.offset.x < -100) {
      onSwipe('left');
    }
  };

  return (
    <motion.div
      drag="x"
      dragConstraints={{ left: 0, right: 0 }}
      style={{
        x, rotate, opacity,
        position: 'absolute',
        width: '90%',
        maxWidth: 400,
        height: '70vh',
        background: T.card,
        borderRadius: 24,
        border: `1px solid ${T.border}`,
        boxShadow: '0 20px 40px rgba(0,0,0,0.5)',
        cursor: 'grab',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        zIndex: 10,
      }}
      whileTap={{ cursor: 'grabbing' }}
      onDragEnd={handleDragEnd}
      exit={{ x: x.get() > 0 ? 500 : -500, opacity: 0, transition: { duration: 0.3 } }}
    >
      {/* Visual feedback overlays */}
      <motion.div style={{ 
        position: 'absolute', top: 40, right: 40, opacity: approveOpacity,
        padding: '10px 20px', border: `4px solid ${T.accent}`, color: T.accent,
        borderRadius: 12, fontSize: 32, fontWeight: 900, transform: 'rotate(15deg)',
        zIndex: 20, pointerEvents: 'none'
      }}>
        APPROVE
      </motion.div>
      
      <motion.div style={{ 
        position: 'absolute', top: 40, left: 40, opacity: discardOpacity,
        padding: '10px 20px', border: `4px solid ${T.red}`, color: T.red,
        borderRadius: 12, fontSize: 32, fontWeight: 900, transform: 'rotate(-15deg)',
        zIndex: 20, pointerEvents: 'none'
      }}>
        DISCARD
      </motion.div>

      {/* Video Content */}
      <div style={{ flex: 1, background: '#000', position: 'relative' }}>
        <video 
          src={clip.clip_url} 
          autoPlay 
          loop 
          muted 
          playsInline
          style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
        />
      </div>

      {/* Info footer */}
      <div style={{ padding: 24, background: 'linear-gradient(to top, rgba(13,14,20,1), rgba(13,14,20,0))' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: T.text }}>Clip #{clip.index}</span>
          <span style={{ fontSize: 13, background: T.accentDim, color: T.accent, padding: '4px 10px', borderRadius: 6, fontWeight: 700 }}>
            {clip.final_score.toFixed(1)} Score
          </span>
        </div>
        <p style={{ fontSize: 14, color: T.muted, lineHeight: 1.5, margin: 0 }}>
          {clip.reason}
        </p>
      </div>
    </motion.div>
  );
}
