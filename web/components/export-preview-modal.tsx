"use client";

import React, { useState } from "react";

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

  if (!isOpen) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="modal-overlay" style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: "rgba(0, 0, 0, 0.8)",
      backdropFilter: "blur(8px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1000,
    }}>
      <div className="panel" style={{
        width: "90%",
        maxWidth: 600,
        maxHeight: "80vh",
        display: "flex",
        flexDirection: "column",
        gap: 20,
        padding: 32,
        position: "relative",
        animation: "slideUp 0.3s ease-out"
      }}>
        <button onClick={onClose} style={{
          position: "absolute",
          top: 20,
          right: 20,
          background: "none",
          border: "none",
          color: "var(--muted)",
          cursor: "pointer",
          fontSize: 20
        }}>×</button>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ 
            width: 40, 
            height: 40, 
            borderRadius: 10, 
            background: type === "linkedin" ? "#0A66C2" : "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontSize: 20
          }}>
            {type === "linkedin" ? "in" : "✉️"}
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: 18 }}>{title}</h2>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>
              Optimized by Intelligence Engine
            </div>
          </div>
        </div>

        <div style={{ 
          flex: 1, 
          overflowY: "auto", 
          background: "rgba(255, 255, 255, 0.03)", 
          padding: 20, 
          borderRadius: 12,
          border: "1px solid var(--line)",
          fontFamily: type === "newsletter" ? "monospace" : "inherit",
          fontSize: 14,
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          color: "var(--fg)"
        }}>
          {content}
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
          <button className="button" style={{ background: "rgba(255,255,255,0.1)", color: "var(--fg)" }} onClick={onClose}>
            Close
          </button>
          <button className="button" onClick={handleCopy}>
            {copied ? "✓ Copied!" : "Copy to Clipboard"}
          </button>
        </div>
      </div>
      
      <style jsx>{`
        @keyframes slideUp {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  );
}
