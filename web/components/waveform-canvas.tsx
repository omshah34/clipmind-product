// File: web/components/waveform-canvas.tsx
'use client';

import { useRef, useEffect } from "react";

export function WaveformCanvas({ samples }: { samples: number[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    // Gap 359: Detect Device Pixel Ratio (DPR) for high-DPI/Retina support
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();

    // Set physical pixel size for internal buffer
    canvas.width  = rect.width  * dpr;
    canvas.height = rect.height * dpr;

    // Scale CSS display size
    canvas.style.width  = `${rect.width}px`;
    canvas.style.height = `${rect.height}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Scale context to draw in CSS pixels but render at native resolution
    ctx.scale(dpr, dpr);

    drawWaveform(ctx, samples, rect.width, rect.height);
  }, [samples]);

  // Handle resize to re-calculate dimensions
  useEffect(() => {
    const handleResize = () => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      ctx?.clearRect(0, 0, canvas.width, canvas.height);
      // The samples dependency in the main effect will trigger the re-draw
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div className="waveform-wrapper" style={{ width: "100%", padding: "8px 0" }}>
      <canvas 
        ref={canvasRef} 
        style={{ width: "100%", height: "120px", display: "block" }} 
      />
    </div>
  );
}

function drawWaveform(ctx: CanvasRenderingContext2D, samples: number[], w: number, h: number) {
  ctx.clearRect(0, 0, w, h);
  
  // Design: Gradient teal waveform
  const gradient = ctx.createLinearGradient(0, 0, 0, h);
  gradient.addColorStop(0, "#00d9c0");
  gradient.addColorStop(1, "#00a894");
  
  ctx.strokeStyle = gradient;
  ctx.lineWidth = 2;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  
  ctx.beginPath();
  const step = w / (samples.length - 1);
  
  samples.forEach((amp, i) => {
    const x = i * step;
    // Map amp (usually 0-1) to vertical center
    const y = (h / 2) - (amp * (h * 0.4));
    
    if (i === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  
  ctx.stroke();
  
  // Fill the bottom for a "mountain" look
  ctx.lineTo(w, h);
  ctx.lineTo(0, h);
  ctx.fillStyle = "rgba(0, 217, 192, 0.1)";
  ctx.fill();
}
