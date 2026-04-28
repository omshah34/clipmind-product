"use client";

/**
 * File: app/BodyShell.tsx
 * Purpose: Client-side wrapper for <body> that prevents accidental file-drops
 *          anywhere outside a designated .upload-dropzone element.
 *          Must be a Client Component because it attaches DOM event handlers.
 */

import type { ReactNode } from "react";

interface BodyShellProps {
  children: ReactNode;
}

export default function BodyShell({ children }: BodyShellProps) {
  function onDragOver(e: React.DragEvent<HTMLBodyElement>) {
    if (!(e.target as HTMLElement).closest(".upload-dropzone")) {
      e.preventDefault();
    }
  }

  function onDrop(e: React.DragEvent<HTMLBodyElement>) {
    if (!(e.target as HTMLElement).closest(".upload-dropzone")) {
      e.preventDefault();
    }
  }

  return (
    <body onDragOver={onDragOver} onDrop={onDrop}>
      {children}
    </body>
  );
}
