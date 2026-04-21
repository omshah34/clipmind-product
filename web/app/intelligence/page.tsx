/**
 * Page: app/intelligence/page.tsx
 * Purpose: Clip Intelligence Dashboard - Server component with Suspense boundary for useSearchParams.
 */

import { Suspense } from "react";
import IntelligenceContent from "./intelligence-content";

function IntelligenceLoading() {
  return (
    <div className="page" style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh" }}>
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: 32, marginBottom: 16 }}>⏳</div>
        <div style={{ fontSize: 14, color: "var(--muted)" }}>Loading Analytics...</div>
      </div>
    </div>
  );
}

export default function IntelligencePage() {
  return (
    <Suspense fallback={<IntelligenceLoading />}>
      <IntelligenceContent />
    </Suspense>
  );
}
