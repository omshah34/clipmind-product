/**
 * File: web/components/toast.tsx
 * Purpose: Provides global Toast notifications resolving the minimal frontend UX gap.
 */

import { useState, useEffect } from "react";

export type ToastMessage = {
  id: string;
  type: "success" | "error" | "info";
  message: string;
};

export function ToastContainer({ messages, removeToast }: { messages: ToastMessage[], removeToast: (id: string) => void }) {
  return (
    <div style={{
      position: "fixed",
      bottom: 24,
      right: 24,
      display: "flex",
      flexDirection: "column",
      gap: 10,
      zIndex: 9999
    }}>
      {messages.map((toast) => (
        <Toast key={toast.id} toast={toast} removeToast={removeToast} />
      ))}
    </div>
  );
}

function Toast({ toast, removeToast }: { toast: ToastMessage, removeToast: (id: string) => void }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      removeToast(toast.id);
    }, 4000);
    return () => clearTimeout(timer);
  }, [toast.id, removeToast]);

  const bgColors = {
    success: "rgba(0, 200, 83, 0.9)",
    error: "rgba(213, 0, 0, 0.9)",
    info: "rgba(41, 98, 255, 0.9)"
  };

  return (
    <div style={{
      background: bgColors[toast.type],
      color: "#fff",
      padding: "12px 20px",
      borderRadius: "8px",
      boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
      fontSize: "14px",
      fontWeight: 500,
      minWidth: "250px",
      animation: "toastSlide 0.3s ease-out forwards",
      cursor: "pointer",
      display: "flex",
      justifyContent: "space-between"
    }} onClick={() => removeToast(toast.id)}>
      <span>{toast.message}</span>
      <span style={{opacity: 0.7, marginLeft: 10}}>×</span>
      <style>{`
        @keyframes toastSlide {
          from { transform: translateX(100%); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
