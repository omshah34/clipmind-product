"use client";

import React from "react";

export default function PerformanceSummaryCards({ data }: { data: any }) {
  const formatNumber = (num: number | null): string => {
    if (num === null || num === undefined) return "0";
    if (num >= 1000000) return (num / 1000000).toFixed(1) + "M";
    if (num >= 1000) return (num / 1000).toFixed(1) + "K";
    return num.toLocaleString();
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 24 }}>
      {/* Total Views Card */}
      <div className="panel" style={{ 
        background: "linear-gradient(135deg, rgba(82, 113, 255, 0.05), rgba(0, 0, 0, 0))",
        borderTop: "4px solid #4facfe"
      }}>
        <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 8, fontWeight: 500 }}>Total Views</div>
        <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-1px" }}>
          {formatNumber(data.total_views)}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 12 }}>
          Across <strong>{data.total_clips}</strong> published clips
        </div>
      </div>

      {/* Engagement Card */}
      <div className="panel" style={{ 
        background: "linear-gradient(135deg, rgba(236, 72, 153, 0.05), rgba(0, 0, 0, 0))",
        borderTop: "4px solid #ec4899"
      }}>
        <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 8, fontWeight: 500 }}>Avg Engagement</div>
        <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-1px" }}>
          {data.avg_engagement ? (data.avg_engagement * 100).toFixed(1) + "%" : "0%"}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 12 }}>
           <strong>{formatNumber(data.total_likes)}</strong> total reactions
        </div>
      </div>

      {/* Viral Hits Card */}
      <div className="panel" style={{ 
        background: "linear-gradient(135deg, rgba(240, 147, 251, 0.05), rgba(0, 0, 0, 0))",
        borderTop: "4px solid #f093fb"
      }}>
        <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 8, fontWeight: 500 }}>Viral Milestones</div>
        <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-1px", color: "var(--accent)" }}>
          {data.viral_hits || 0}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 12 }}>
          Clips exceeding <strong>10.0</strong> AI score
        </div>
      </div>

      {/* Accuracy Card */}
      <div className="panel" style={{ 
        background: "linear-gradient(135deg, rgba(0, 255, 0, 0.05), rgba(0, 0, 0, 0))",
        borderTop: "4px solid #00ff00"
      }}>
        <div style={{ fontSize: 13, color: "var(--muted)", marginBottom: 8, fontWeight: 500 }}>Validated Content</div>
        <div style={{ fontSize: 32, fontWeight: 700, letterSpacing: "-1px" }}>
          {data.validated_hits || 0}
        </div>
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 12 }}>
          Engagement matches AI prediction
        </div>
      </div>
    </div>
  );
}
