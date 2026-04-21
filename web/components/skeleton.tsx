/**
 * File: web/components/skeleton.tsx
 * Purpose: Provides universal loading state visualizations avoiding stark jumps in rendering.
 */

export function Skeleton({ 
  width = "100%", 
  height = "20px", 
  borderRadius = "4px",
  style = {}
}) {
  return (
    <div 
      className="skeleton-pulse"
      style={{
        width,
        height,
        borderRadius,
        background: "linear-gradient(90deg, #1a1c23 0px, #2a2d39 40px, #1a1c23 80px)",
        backgroundSize: "200% 100%",
        ...style
      }}
    >
      <style>{`
        .skeleton-pulse {
          animation: skeletonLoad 1.5s infinite ease-in-out;
        }
        @keyframes skeletonLoad {
          0% { background-position: -200% 0; }
          100% { background-position: 200% 0; }
        }
      `}</style>
    </div>
  );
}
