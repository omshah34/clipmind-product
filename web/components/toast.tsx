/**
 * File: web/components/toast.tsx
 * Purpose: Provides global Toast notifications with FIFO queuing (Gap 219).
 */

import { useEffect, useMemo } from "react";

export type ToastMessage = {
  id: string;
  type: "success" | "error" | "info";
  message: string;
};

export function ToastContainer({ messages, removeToast }: { messages: ToastMessage[], removeToast: (id: string) => void }) {
  // Gap 219: Implement FIFO queue limited to max 3 visible toasts.
  // We only show the latest 3 toasts. If a 4th arrives, the oldest should be dismissed.
  const visibleMessages = useMemo(() => {
    if (messages.length <= 3) return messages;
    // Keep only the most recent 3
    return messages.slice(-3);
  }, [messages]);

  // Effect to automatically remove oldest toasts if the raw list grows too large
  useEffect(() => {
    if (messages.length > 3) {
      // Remove all but the last 3
      const toRemove = messages.slice(0, messages.length - 3);
      toRemove.forEach(t => removeToast(t.id));
    }
  }, [messages, removeToast]);

  return (
    <div style={{
      position: "fixed", bottom: 24, right: 24,
      display: "flex", flexDirection: "column", gap: 10, zIndex: 9999
    }}>
      {visibleMessages.map((toast) => (
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
      color: "#fff", padding: "12px 20px", borderRadius: "8px",
      boxShadow: "0 4px 12px rgba(0,0,0,0.15)", fontSize: "14px", fontWeight: 500,
      minWidth: "250px", animation: "toastSlide 0.3s ease-out forwards",
      cursor: "pointer", display: "flex", justifyContent: "space-between"
    }} onClick={() => removeToast(toast.id)}>
      <span>{toast.message}</span>
      <span style={{opacity: 0.7, marginLeft: 10}}>×</span>
      <style>{`
        @keyframes toastSlide { from { transform: translateX(100%); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
      `}</style>
    </div>
  );
}
