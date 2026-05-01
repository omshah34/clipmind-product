"use client";

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

/* ── Icons (inline SVG to avoid extra deps) ── */
const Icon = ({ d, size = 18, className = '' }: { d: string; size?: number; className?: string }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round"
    className={className}>
    <path d={d} />
  </svg>
);

const icons = {
  home:       'M3 9.5L12 3l9 6.5V20a1 1 0 01-1 1H4a1 1 0 01-1-1V9.5z M9 21V12h6v9',
  jobs:       'M15 3H9a2 2 0 00-2 2v14a2 2 0 002 2h6M15 3a2 2 0 012 2v14a2 2 0 01-2 2M15 3l3 3M9 7h6M9 11h6M9 15h4',
  studio:     'M15.5 7.5a3 3 0 010 9M8 17l-4.5 2 1-4.5L14 5l3.5 3.5L8 17z',
  campaigns:  'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
  sequences:  'M4 6h16M4 12h16M4 18h7',
  intelligence:'M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z',
  dna:        'M9 3h6M9 21h6M9 3C9 13 15 11 15 21M9 21C9 11 15 13 15 3',
  publish:    'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z',
  team:       'M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75',
  brand:      'M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5',
  settings:   'M12 15a3 3 0 100-6 3 3 0 000 6z M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z',
  collapse:   'M15 18l-6-6 6-6',
  expand:     'M9 18l6-6-6-6',
  upload:     'M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12',
  brain:      'M9.5 2A2.5 2.5 0 0112 4.5v15a2.5 2.5 0 01-4.96-.44 2.5 2.5 0 01-2.96-3.08 3 3 0 01-.34-5.58 2.5 2.5 0 013.32-3.97A2.5 2.5 0 019.5 2zM14.5 2A2.5 2.5 0 0112 4.5v15a2.5 2.5 0 004.96-.44 2.5 2.5 0 002.96-3.08 3 3 0 00.34-5.58 2.5 2.5 0 00-3.32-3.97A2.5 2.5 0 0014.5 2z',
};

const NAV = [
  {
    group: 'Workspace',
    links: [
      { href: '/',              label: 'Dashboard',    icon: 'home'        },
      { href: '/jobs',          label: 'Jobs',         icon: 'jobs'        },
      { href: '/jobs/studio',   label: 'Clip Studio',  icon: 'studio'      },
    ],
  },
  {
    group: 'Content',
    links: [
      { href: '/campaigns',     label: 'Campaigns',    icon: 'campaigns'   },
      { href: '/sequences',     label: 'Sequences',    icon: 'sequences'   },
      { href: '/intelligence',  label: 'Intelligence', icon: 'intelligence'},
      { href: '/dna',           label: 'Content DNA',  icon: 'dna'         },
    ],
  },
  {
    group: 'Publish',
    links: [
      { href: '/publish',       label: 'Publish',      icon: 'publish'     },
      { href: '/preview',       label: 'Preview',      icon: 'studio'      },
    ],
  },
  {
    group: 'Settings',
    links: [
      { href: '/team',          label: 'Team',         icon: 'team'        },
      { href: '/brand-kit',     label: 'Brand Kit',    icon: 'brand'       },
    ],
  },
];

function NavLink({ href, label, icon, collapsed }: {
  href: string; label: string; icon: string; collapsed: boolean;
}) {
  const pathname = usePathname();
  const isActive = pathname === href || (href !== '/' && pathname?.startsWith(href));

  return (
    <Link
      href={href}
      title={collapsed ? label : undefined}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: collapsed ? 0 : '10px',
        padding: collapsed ? '10px' : '8px 12px',
        justifyContent: collapsed ? 'center' : 'flex-start',
        borderRadius: 'var(--radius-md)',
        fontSize: '13.5px',
        fontWeight: isActive ? 500 : 400,
        color: isActive ? 'var(--accent)' : 'var(--text-secondary)',
        background: isActive ? 'var(--accent-dim)' : 'transparent',
        transition: 'all 0.15s ease',
        textDecoration: 'none',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        position: 'relative',
      }}
      onMouseEnter={(e) => {
        if (!isActive) {
          (e.currentTarget as HTMLElement).style.color = 'var(--text-primary)';
          (e.currentTarget as HTMLElement).style.background = 'var(--bg-elevated)';
        }
      }}
      onMouseLeave={(e) => {
        if (!isActive) {
          (e.currentTarget as HTMLElement).style.color = 'var(--text-secondary)';
          (e.currentTarget as HTMLElement).style.background = 'transparent';
        }
      }}
    >
      {isActive && !collapsed && (
        <span style={{
          position: 'absolute', left: 0, top: '20%', bottom: '20%',
          width: '2px', background: 'var(--accent)', borderRadius: '0 2px 2px 0',
        }} />
      )}
      <Icon d={icons[icon as keyof typeof icons]} size={16}
        className={isActive ? 'text-accent' : ''} />
      {!collapsed && <span>{label}</span>}
    </Link>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  // Close mobile menu on navigation
  useEffect(() => { setMobileOpen(false); }, [pathname]);

  const SIDEBAR_W = collapsed ? 60 : 220;

  const sidebarContent = (
    <nav style={{
      width: SIDEBAR_W,
      minWidth: SIDEBAR_W,
      height: '100vh',
      background: 'var(--bg-surface)',
      borderRight: '1px solid var(--border)',
      display: 'flex',
      flexDirection: 'column',
      transition: 'width 0.2s ease, min-width 0.2s ease',
      overflow: 'hidden',
      position: 'sticky',
      top: 0,
    }}>
      {/* Logo */}
      <div style={{
        padding: collapsed ? '20px 0' : '20px 16px',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: collapsed ? 'center' : 'space-between',
        gap: '10px',
        flexShrink: 0,
      }}>
        {!collapsed && (
          <Link href="/" style={{ textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{
              width: 28, height: 28,
              background: 'linear-gradient(135deg, var(--accent), #0D9488)',
              borderRadius: 'var(--radius-md)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Icon d={icons.brain} size={14} className="text-white" />
            </span>
            <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '15px', color: 'var(--text-primary)', letterSpacing: '-0.02em' }}>
              ClipMind
            </span>
          </Link>
        )}
        {collapsed && (
          <span style={{
            width: 28, height: 28,
            background: 'linear-gradient(135deg, var(--accent), #0D9488)',
            borderRadius: 'var(--radius-md)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <Icon d={icons.brain} size={14} />
          </span>
        )}
        {!collapsed && (
          <button
            onClick={() => setCollapsed(true)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--text-tertiary)', padding: '4px', borderRadius: 'var(--radius-sm)',
              display: 'flex', transition: 'color 0.15s',
            }}
            title="Collapse sidebar"
          >
            <Icon d={icons.collapse} size={15} />
          </button>
        )}
        {collapsed && (
          <button
            onClick={() => setCollapsed(false)}
            style={{
              position: 'absolute', right: -10, top: 22,
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              cursor: 'pointer', color: 'var(--text-tertiary)',
              borderRadius: '50%', width: 20, height: 20,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              zIndex: 10, transition: 'color 0.15s',
            }}
            title="Expand sidebar"
          >
            <Icon d={icons.expand} size={11} />
          </button>
        )}
      </div>

      {/* Quick upload */}
      {!collapsed && (
        <div style={{ padding: '12px 12px 0' }}>
          <Link href="/upload" style={{
            display: 'flex', alignItems: 'center', gap: '8px',
            padding: '8px 12px', background: 'var(--accent)', borderRadius: 'var(--radius-md)',
            color: '#fff', fontSize: '13px', fontWeight: 500, textDecoration: 'none',
            transition: 'opacity 0.15s',
          }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.opacity = '0.85'; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.opacity = '1'; }}
          >
            <Icon d={icons.upload} size={14} />
            New upload
          </Link>
        </div>
      )}

      {/* Nav groups */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px', marginTop: '8px' }}>
        {NAV.map((group) => (
          <div key={group.group} style={{ marginBottom: '4px' }}>
            {!collapsed && (
              <p style={{
                fontSize: '10px', fontWeight: 600, letterSpacing: '0.08em',
                color: 'var(--text-tertiary)', textTransform: 'uppercase',
                padding: '8px 12px 4px',
              }}>
                {group.group}
              </p>
            )}
            {collapsed && <div style={{ height: '16px' }} />}
            {group.links.map((link) => (
              <NavLink key={link.href} {...link} collapsed={collapsed} />
            ))}
          </div>
        ))}
      </div>

      {/* Bottom: settings */}
      <div style={{ padding: '8px', borderTop: '1px solid var(--border)', flexShrink: 0 }}>
        <NavLink href="/settings" label="Settings" icon="settings" collapsed={collapsed} />
      </div>
    </nav>
  );

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: 'var(--bg-base)', position: 'relative', width: '100%' }}>
      {/* Desktop sidebar */}
      <div className="hidden md:block" style={{ position: 'relative' }}>
        {sidebarContent}
      </div>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
            zIndex: 40, backdropFilter: 'blur(2px)',
          }}
          onClick={() => setMobileOpen(false)}
        />
      )}
      {mobileOpen && (
        <div style={{ position: 'fixed', left: 0, top: 0, bottom: 0, zIndex: 50 }}>
          {sidebarContent}
        </div>
      )}

      {/* Main content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden' }}>
        {/* Mobile header */}
        <header style={{
          display: 'none', /* shown via media query */
          padding: '14px 20px',
          borderBottom: '1px solid var(--border)',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: 'var(--bg-surface)',
        }}
        className="flex md:hidden"
        >
          <button
            onClick={() => setMobileOpen(true)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-primary)', padding: '4px' }}
          >
            <svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
              <path d="M3 12h18M3 6h18M3 18h18" strokeLinecap="round" />
            </svg>
          </button>
          <span style={{ fontFamily: 'var(--font-display)', fontWeight: 700, fontSize: '15px' }}>ClipMind</span>
          <Link href="/upload" style={{
            padding: '6px 12px', background: 'var(--accent)', borderRadius: 'var(--radius-md)',
            color: '#fff', fontSize: '12px', fontWeight: 500, textDecoration: 'none',
          }}>
            Upload
          </Link>
        </header>

        <main style={{ flex: 1, overflowY: 'auto', overflowX: 'hidden' }}>
          {children}
        </main>
      </div>
    </div>
  );
}
