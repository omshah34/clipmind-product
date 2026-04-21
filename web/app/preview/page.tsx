import { Suspense } from "react";
import PreviewContent from "./preview-content";

function PreviewLoading() {
  return (
    <div className="flex items-center justify-center min-h-screen">
      <div className="text-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
        <p className="mt-4 text-gray-600">Loading preview...</p>
      </div>
    </div>
  );
}

export default function PreviewPage() {
  return (
    <Suspense fallback={<PreviewLoading />}>
      <PreviewContent />
    </Suspense>
  );
}
