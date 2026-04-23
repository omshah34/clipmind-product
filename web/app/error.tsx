/**
 * File: web/app/error.tsx
 * Purpose: Root error boundary for the App Router.
 *          Handles unexpected runtime errors and "Connection Lost" states (Gap 111).
 */

'use client';

import { useEffect } from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log the error to an error reporting service
    console.error('[Root Error Boundary]', error);
  }, [error]);

  const isConnectionError = 
    error.message?.toLowerCase().includes('fetch') || 
    error.message?.toLowerCase().includes('network') ||
    error.message?.toLowerCase().includes('failed to fetch');

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: '#f6f8fc',
      padding: 20,
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      <div style={{
        maxWidth: 480,
        width: '100%',
        background: 'white',
        borderRadius: 24,
        padding: 40,
        textAlign: 'center',
        boxShadow: '0 20px 50px rgba(16, 32, 51, 0.1)',
        border: '1px solid rgba(16, 32, 51, 0.05)'
      }}>
        <div style={{
          width: 80,
          height: 80,
          background: isConnectionError ? 'rgba(255, 111, 97, 0.1)' : 'rgba(16, 32, 51, 0.05)',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          margin: '0 auto 24px',
          color: isConnectionError ? '#ff6f61' : '#102033'
        }}>
          {isConnectionError ? (
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12.55a11 11 0 0 1 14.08 0" />
              <path d="M1.42 9a16 16 0 0 1 21.16 0" />
              <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </svg>
          ) : (
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          )}
        </div>

        <h1 style={{ fontSize: 24, fontWeight: 800, margin: '0 0 12px', color: '#102033', letterSpacing: '-0.02em' }}>
          {isConnectionError ? 'Connection Lost' : 'Something went wrong'}
        </h1>
        
        <p style={{ fontSize: 16, color: '#5f6b7d', lineHeight: 1.6, margin: '0 0 32px' }}>
          {isConnectionError 
            ? "We're having trouble connecting to the ClipMind servers. Please check your internet connection and try again."
            : "An unexpected error occurred while processing your request. Our team has been notified."}
        </p>

        <div style={{ display: 'flex', gap: 12 }}>
          <button
            onClick={() => reset()}
            style={{
              flex: 1,
              padding: '14px 24px',
              background: '#102033',
              color: 'white',
              borderRadius: 12,
              border: 'none',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'transform 0.2s'
            }}
          >
            Try again
          </button>
          <a
            href="/"
            style={{
              flex: 1,
              padding: '14px 24px',
              background: 'white',
              color: '#102033',
              borderRadius: 12,
              border: '1px solid rgba(16, 32, 51, 0.1)',
              fontWeight: 600,
              textAlign: 'center',
              textDecoration: 'none'
            }}
          >
            Back to home
          </a>
        </div>
      </div>
    </div>
  );
}
