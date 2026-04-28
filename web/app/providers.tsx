/**
 * File: app/providers.tsx
 * Purpose: Client-side provider wrapper.
 */

'use client';

import { ReactNode } from 'react';
import { SessionProvider } from 'next-auth/react';
import { AuthProvider } from '@/components/auth-provider';
import { QueryProvider } from '@/components/query-provider';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <QueryProvider>
        <AuthProvider>
          {children}
        </AuthProvider>
      </QueryProvider>
    </SessionProvider>
  );
}
