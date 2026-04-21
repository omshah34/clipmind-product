/**
 * File: app/sequences/page.tsx
 * Purpose: Clip Sequences page - Multi-clip narrative editor and publisher.
 *          Server component with Suspense boundary for useSearchParams.
 */

import { Suspense } from "react";
import SequencesContent from "./sequences-content";

export default function SequencesPage() {
  return (
    <Suspense fallback={<div className="page" style={{ textAlign: "center", color: "var(--muted)", paddingTop: 60 }}>Loading...</div>}>
      <SequencesContent />
    </Suspense>
  );
}
