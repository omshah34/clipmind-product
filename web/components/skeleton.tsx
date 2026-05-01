import React from 'react';

/* ── Base skeleton block ── */
function Bone({ width = '100%', height = 16, radius = 6, style = {} }: {
  width?: string | number;
  height?: number;
  radius?: number;
  style?: React.CSSProperties;
}) {
  return (
    <div
      className="skeleton-base"
      style={{ width, height, borderRadius: radius, flexShrink: 0, ...style }}
    />
  );
}

/* ── Stat card skeleton ── */
export function StatCardSkeleton() {
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', padding: '18px 20px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '14px' }}>
        <Bone width={80} height={12} radius={4} />
        <Bone width={28} height={28} radius={8} />
      </div>
      <Bone width={90} height={28} radius={6} />
    </div>
  );
}

/* ── Job list row skeleton ── */
export function JobRowSkeleton() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '16px',
      padding: '14px 20px', borderBottom: '1px solid var(--border-subtle)',
    }}>
      <div style={{ flex: 1 }}>
        <Bone width="70%" height={14} radius={4} style={{ marginBottom: 8 }} />
        <div style={{ display: 'flex', gap: '8px' }}>
          <Bone width={56} height={18} radius={99} />
          <Bone width={40} height={18} radius={4} />
        </div>
      </div>
      <div style={{ display: 'flex', gap: '8px' }}>
        <Bone width={40} height={22} radius={99} />
        <Bone width={80} height={22} radius={99} />
      </div>
    </div>
  );
}

export function JobListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', overflow: 'hidden',
    }}>
      {Array.from({ length: rows }).map((_, i) => <JobRowSkeleton key={i} />)}
    </div>
  );
}

/* ── Clip card skeleton ── */
export function ClipCardSkeleton() {
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', overflow: 'hidden',
    }}>
      <Bone width="100%" height={120} radius={0} />
      <div style={{ padding: '12px 14px' }}>
        <Bone width="85%" height={13} radius={4} style={{ marginBottom: 8 }} />
        <Bone width="55%" height={11} radius={4} style={{ marginBottom: 10 }} />
        <div style={{ display: 'flex', gap: '8px' }}>
          <Bone width={40} height={20} radius={99} />
          <Bone width={60} height={20} radius={99} />
        </div>
      </div>
    </div>
  );
}

/* ── Chart skeleton ── */
export function ChartSkeleton({ height = 220 }: { height?: number }) {
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', padding: '20px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
        <Bone width={120} height={14} radius={4} />
        <div style={{ display: 'flex', gap: '6px' }}>
          <Bone width={36} height={26} radius={6} />
          <Bone width={36} height={26} radius={6} />
          <Bone width={36} height={26} radius={6} />
        </div>
      </div>
      {/* Fake bar chart */}
      <div style={{
        display: 'flex', alignItems: 'flex-end',
        gap: '8px', height,
        borderBottom: '1px solid var(--border)',
      }}>
        {[65, 80, 50, 90, 70, 85, 60, 95, 45, 75, 88, 62].map((h, i) => (
          <div
            key={i}
            className="skeleton-base"
            style={{
              flex: 1, height: `${h}%`,
              borderRadius: '4px 4px 0 0',
              animationDelay: `${i * 60}ms`,
            }}
          />
        ))}
      </div>
      <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
        {[40, 36, 44, 38, 42, 36, 40, 38, 44, 36, 40, 38].map((w, i) => (
          <Bone key={i} width={w} height={10} radius={3} style={{ flex: 1, animationDelay: `${i * 40}ms` }} />
        ))}
      </div>
    </div>
  );
}

/* ── Timeline skeleton ── */
export function TimelineSkeleton() {
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', padding: '16px',
    }}>
      {/* Video thumbnail placeholder */}
      <Bone width="100%" height={180} radius={8} style={{ marginBottom: 16 }} />
      {/* Playback controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px', justifyContent: 'center' }}>
        <Bone width={28} height={28} radius={99} />
        <Bone width={44} height={44} radius={99} />
        <Bone width={28} height={28} radius={99} />
      </div>
      {/* Timeline track */}
      <div style={{ position: 'relative', marginBottom: '12px' }}>
        <Bone width="100%" height={48} radius={6} />
        {/* Clip segments overlaid */}
        {[
          { left: '5%', width: '18%' },
          { left: '27%', width: '12%' },
          { left: '44%', width: '22%' },
          { left: '72%', width: '16%' },
        ].map((seg, i) => (
          <div key={i} style={{
            position: 'absolute', top: 4, bottom: 4,
            left: seg.left, width: seg.width,
            background: 'var(--accent-dim)', border: '1px solid var(--accent-glow)',
            borderRadius: 4, animationDelay: `${i * 100}ms`,
          }} />
        ))}
      </div>
      {/* Waveform */}
      <Bone width="100%" height={32} radius={6} />
    </div>
  );
}

/* ── Radar chart skeleton ── */
export function RadarSkeleton() {
  return (
    <div style={{
      background: 'var(--bg-surface)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)', padding: '20px',
      display: 'flex', flexDirection: 'column', alignItems: 'center',
    }}>
      <Bone width={100} height={14} radius={4} style={{ marginBottom: 20 }} />
      <Bone width={200} height={200} radius={99} style={{ opacity: 0.5 }} />
      <div style={{ display: 'flex', gap: '12px', marginTop: '20px' }}>
        {[50, 70, 55, 65, 48].map((w, i) => (
          <Bone key={i} width={w} height={10} radius={4} />
        ))}
      </div>
    </div>
  );
}

/* ── Page header skeleton ── */
export function PageHeaderSkeleton() {
  return (
    <div style={{ marginBottom: '28px' }}>
      <Bone width={200} height={26} radius={6} style={{ marginBottom: 10 }} />
      <Bone width={340} height={14} radius={4} />
    </div>
  );
}

/* ── Full dashboard skeleton ── */
export function DashboardSkeleton() {
  return (
    <div style={{ padding: '32px 36px', maxWidth: 1200 }}>
      <PageHeaderSkeleton />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '14px', marginBottom: '36px' }}>
        {[0, 1, 2, 3].map(i => <StatCardSkeleton key={i} />)}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '24px' }}>
        <JobListSkeleton rows={5} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <Bone width="100%" height={140} radius={12} />
          <Bone width="100%" height={200} radius={12} />
        </div>
      </div>
    </div>
  );
}
