/**
 * File: web/components/error-boundary.tsx
 * Purpose: Granular error boundary component (Gap 57).
 *          Prevents a crash in one section (e.g., Charts) from taking down the whole page.
 */

'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  name?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`[ErrorBoundary:${this.props.name || 'Component'}]`, error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div style={{
          padding: 24,
          borderRadius: 16,
          border: '1px dashed #ff6f61',
          background: 'rgba(255, 111, 97, 0.05)',
          color: '#a53c2f',
          textAlign: 'center'
        }}>
          <h4 style={{ margin: '0 0 8px' }}>Something went wrong in {this.props.name || 'this section'}</h4>
          <p style={{ fontSize: 13, margin: '0 0 16px', opacity: 0.8 }}>
            {this.state.error?.message || 'Unknown error'}
          </p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: '8px 16px',
              background: '#a53c2f',
              color: 'white',
              border: 'none',
              borderRadius: 8,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer'
            }}
          >
            Retry
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
