'use client';

import React, { useRef, useEffect } from "react";

// Gap 272: Virtualize with IntersectionObserver — only load video src when in view
export function LazyVideo({ src, poster }: { src: string; poster: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const loadedRef = useRef(false);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !loadedRef.current) {
          video.src = src;           // Load only when visible
          video.preload = "metadata"; // Don't decode — just headers
          loadedRef.current = true;
        } else if (!entry.isIntersecting && loadedRef.current) {
          video.pause();
          video.removeAttribute("src"); // Release decoder memory
          video.load();                 // Force buffer flush
          loadedRef.current = false;
        }
      },
      { rootMargin: "200px" } // preload 200px before entering viewport
    );

    observer.observe(video);
    return () => {
      observer.unobserve(video);
      // Cleanup on unmount — critical for mobile performance
      video.pause();
      video.removeAttribute("src");
      video.load();
    };
  }, [src]);

  return (
    <video
      ref={videoRef}
      poster={poster}
      muted
      playsInline
      className="video-thumb"
      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
    />
  );
}

export default function VideoGrid({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
      gap: '20px',
      padding: '20px 0',
    }}>
      {children}
    </div>
  );
}
