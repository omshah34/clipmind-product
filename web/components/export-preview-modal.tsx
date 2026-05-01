"use client";

/**
 * File: components/export-preview-modal.tsx
 * Purpose: Modal for previewing exported content with focus trapping (Gap 214).
 */

import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

interface ExportPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  content: string;
  type: "linkedin" | "newsletter";
}

export default function ExportPreviewModal({
  isOpen,
  onClose,
  title,
  content,
  type,
}: ExportPreviewModalProps) {
  const [copied, setCopied] = useState(false);
  const modalRef = useRef<HTMLDivElement>(null);

  // Gap 214: Focus Trap Implementation
  useEffect(() => {
    if (!isOpen) return;

    const modalElement = modalRef.current;
    if (!modalElement) return;

    // Generic selector for focusable elements
    const focusableSelectors = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
    
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;

      const focusableElements = Array.from(modalElement.querySelectorAll<HTMLElement>(focusableSelectors));
      if (focusableElements.length === 0) return;

      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];

      if (e.shiftKey) { // Shift + Tab
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        }
      } else { // Tab
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    // Auto-focus the first element or the modal itself
    const initialFocus = modalElement.querySelector<HTMLElement>(focusableSelectors);
    if (initialFocus) initialFocus.focus();

    window.addEventListener('keydown', handleKeyDown);
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return createPortal(
    <div className="modal-overlay" style={{
      position: "fixed", top: 0, left: 0, right: 0, bottom: 0,
      background: "rgba(0, 0, 0, 0.8)", backdropFilter: "blur(8px)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}>
      <div 
        ref={modalRef}
        className="panel" 
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        style={{
          width: "90%", maxWidth: 600, maxHeight: "80vh",
          display: "flex", flexDirection: "column", gap: 20, padding: 32,
          position: "relative", animation: "slideUp 0.3s ease-out"
        }}
      >
        <button 
          onClick={onClose} 
          aria-label="Close modal"
          style={{
            position: "absolute", top: 20, right: 20,
            background: "none", border: "none", color: "var(--muted)",
            cursor: "pointer", fontSize: 20
          }}
        >
          ×
        </button>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ 
            width: 40, height: 40, borderRadius: 10, 
            background: type === "linkedin" ? "#0A66C2" : "var(--accent)",
            display: "flex", alignItems: "center", justifyContent: "center", color: "white", fontSize: 20
          }}>
            {type === "linkedin" ? "in" : "✉️"}
          </div>
          <div>
            <h2 id="modal-title" style={{ margin: 0, fontSize: 18 }}>{title}</h2>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>Optimized by Intelligence Engine</div>
          </div>
        </div>

        <div style={{ 
          flex: 1, overflowY: "auto", background: "rgba(255, 255, 255, 0.03)", 
          padding: 20, borderRadius: 12, border: "1px solid var(--line)",
          fontFamily: type === "newsletter" ? "monospace" : "inherit",
          fontSize: 14, lineHeight: 1.6, whiteSpace: "pre-wrap", color: "var(--text)"
        }}>
          {content}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
          <button className="button" style={{ background: "rgba(255,255,255,0.1)", color: "var(--text)" }} onClick={onClose}>
            Close
          </button>
          <button className="button" onClick={handleCopy}>
            {copied ? "✓ Copied!" : "Copy to Clipboard"}
          </button>
        </div>
      </div>
      
      <style jsx>{`
        @keyframes slideUp { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>
    </div>,
    document.body
  );
}
