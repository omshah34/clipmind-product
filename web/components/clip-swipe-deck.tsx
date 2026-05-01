// File: web/components/clip-swipe-deck.tsx
'use client';

import { useEffect, useRef } from "react";

export function SwipeDeckVideo({ src, isActive }: { src: string; isActive: boolean }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    const container = containerRef.current;
    if (!video || !container) return;

    // Gap 356: IntersectionObserver to release decoder memory for off-screen videos
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          if (!video.src) {
            video.src = src;
            video.load();
          }
        } else {
          // Release decoder memory — critical for iOS Safari
          video.pause();
          video.removeAttribute("src");
          video.load();
        }
      },
      { threshold: 0.01 }
    );

    observer.observe(container);
    return () => observer.disconnect();
  }, [src]);

  // Handle active state play/pause
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    
    if (isActive && video.src) {
      video.play().catch(() => {
        // Autoplay may be blocked if no user gesture has occurred yet
        console.warn("Autoplay blocked for SwipeDeckVideo");
      });
    } else {
      video.pause();
    }
  }, [isActive]);

  return (
    <div ref={containerRef} className="swipe-video-container" style={{ width: "100%", height: "100%", position: "relative" }}>
      <video
        ref={videoRef}
        playsInline   // Critical for iOS inline playback
        muted
        loop
        preload="none"   // Deferred to IntersectionObserver
        className="w-full h-full object-cover rounded-xl"
        style={{ background: "#000" }}
      />
    </div>
  );
}
