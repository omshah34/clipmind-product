// File: web/components/transcript-timeline.tsx
'use client';

import { useVirtualizer } from "@tanstack/react-virtual";
import { useRef } from "react";

interface Word {
  word: string;
  start: number;
  end: number;
}

export function TranscriptTimeline({ words }: { words: Word[] }) {
  const parentRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: words.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 32,      // Height per word row
    overscan: 10,                // Render 10 items outside viewport
  });

  return (
    <div 
      ref={parentRef} 
      className="transcript-scroll-container"
      style={{ height: "500px", overflow: "auto", background: "var(--bg-surface)", borderRadius: "var(--radius-lg)" }}
    >
      <div 
        style={{ 
          height: virtualizer.getTotalSize(), 
          position: "relative",
          width: "100%" 
        }}
      >
        {virtualizer.getVirtualItems().map((vItem) => {
          const word = words[vItem.index];
          return (
            <div
              key={vItem.key}
              className="timeline-word-row"
              style={{
                position: "absolute",
                top: vItem.start,
                left: 0,
                width: "100%",
                height: vItem.size,
                display: "flex",
                alignItems: "center",
                padding: "0 16px",
                borderBottom: "1px solid var(--border-subtle)"
              }}
            >
              <span className="word-time" style={{ color: "var(--text-muted)", fontSize: "12px", width: "60px" }}>
                {word.start.toFixed(1)}s
              </span>
              <span className="word-text" style={{ fontWeight: 500 }}>
                {word.word}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
