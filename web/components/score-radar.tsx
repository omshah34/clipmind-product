/**
 * File: components/score-radar.tsx
 * Purpose: 5-dimension radar chart for visualizing clip scores
 *          (hook, emotion, clarity, story, virality).
 *          Based on recharts for easy integration with Next.js components.
 */

import React from 'react';

type ScoreRadarProps = {
  hookScore: number;
  emotionScore: number;
  clarityScore: number;
  storyScore: number;
  viralityScore: number;
  size?: number; // SVG size in pixels
  animationDuration?: number; // Animation duration in milliseconds
};

export function ScoreRadar({
  hookScore,
  emotionScore,
  clarityScore,
  storyScore,
  viralityScore,
  size = 200,
  animationDuration = 500,
}: ScoreRadarProps) {
  // Dimensions in order (clockwise)
  const dimensions = [
    { label: 'Hook', value: hookScore, color: '#FF6B6B' },
    { label: 'Emotion', value: emotionScore, color: '#4ECDC4' },
    { label: 'Clarity', value: clarityScore, color: '#FFE66D' },
    { label: 'Story', value: storyScore, color: '#95E1D3' },
    { label: 'Virality', value: viralityScore, color: '#F38181' },
  ];

  const numDimensions = dimensions.length;
  const angleSlice = (Math.PI * 2) / numDimensions;
  const radius = (size - 40) / 2;

  // Generate points for the polygon (normalized to 0-10 scale)
  const points = dimensions.map((dim, i) => {
    const angle = angleSlice * i - Math.PI / 2;
    const scaledRadius = (dim.value / 10) * radius;
    const x = size / 2 + scaledRadius * Math.cos(angle);
    const y = size / 2 + scaledRadius * Math.sin(angle);
    return `${x},${y}`;
  });

  // Generate axis lines (grid background)
  const axisPoints = dimensions.map((_, i) => {
    const angle = angleSlice * i - Math.PI / 2;
    const x = size / 2 + radius * Math.cos(angle);
    const y = size / 2 + radius * Math.sin(angle);
    return { x, y, angle };
  });

  // Generate labels positioned outside the polygon
  const labelPoints = dimensions.map((dim, i) => {
    const angle = angleSlice * i - Math.PI / 2;
    const labelRadius = radius + 25;
    const x = size / 2 + labelRadius * Math.cos(angle);
    const y = size / 2 + labelRadius * Math.sin(angle);
    return { ...dim, x, y };
  });

  return (
    <div className="flex flex-col items-center gap-3">
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        className="rounded-lg bg-gray-50 border border-gray-200"
        style={{ filter: 'drop-shadow(0 1px 3px rgba(0,0,0,0.1))' }}
      >
        {/* Grid circles (concentric) */}
        {[...Array(5)].map((_, i) => (
          <circle
            key={`grid-${i}`}
            cx={size / 2}
            cy={size / 2}
            r={(((i + 1) / 5) * radius)}
            fill="none"
            stroke="#e5e7eb"
            strokeDasharray="2,2"
            strokeWidth={0.5}
          />
        ))}

        {/* Axis lines */}
        {axisPoints.map((axis, i) => (
          <line
            key={`axis-${i}`}
            x1={size / 2}
            y1={size / 2}
            x2={axis.x}
            y2={axis.y}
            stroke="#d1d5db"
            strokeWidth={0.5}
          />
        ))}

        {/* Score polygon (animated) */}
        <polygon
          points={points.join(' ')}
          fill="rgba(79, 205, 196, 0.3)"
          stroke="#4ECDC4"
          strokeWidth={2}
          style={{
            animation: `fadeIn ${animationDuration}ms ease-in-out`,
          }}
        />

        {/* Score vertices (circles) */}
        {points.map((point, i) => {
          const [x, y] = point.split(',').map(Number);
          return (
            <circle
              key={`vertex-${i}`}
              cx={x}
              cy={y}
              r={3}
              fill={dimensions[i].color}
              stroke="white"
              strokeWidth={1}
            />
          );
        })}

        {/* Labels with scores */}
        {labelPoints.map((label, i) => (
          <g key={`label-${i}`}>
            <text
              x={label.x}
              y={label.y - 2}
              textAnchor="middle"
              fontSize="12"
              fontWeight="600"
              fill="#1f2937"
              className="select-none"
            >
              {label.label}
            </text>
            <text
              x={label.x}
              y={label.y + 12}
              textAnchor="middle"
              fontSize="11"
              fontWeight="500"
              fill={label.color}
              className="select-none"
            >
              {label.value.toFixed(1)}
            </text>
          </g>
        ))}
      </svg>

      {/* Center score display */}
      <div className="text-center">
        <div className="text-2xl font-bold text-gray-900">
          {(
            (hookScore + emotionScore + clarityScore + storyScore + viralityScore) /
            5
          ).toFixed(1)}
        </div>
        <div className="text-xs text-gray-500">Average Score</div>
      </div>

      <style jsx>{`
        @keyframes fadeIn {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}

export default ScoreRadar;
