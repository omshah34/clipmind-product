/**
 * File: components/upload-form-with-brand-kit.tsx
 * Purpose: Enhanced upload form that allows selecting a brand kit for clip generation
 * 
 * Features:
 * - Video file selection
 * - Brand kit selector dropdown
 * - Brand kit preview
 * - Integration with existing upload flow
 * 
 * Props:
 * - userId: User identifier (for brand kit API calls)
 * - defaultBrandKitId: Optional default brand kit to select
 * - onUploadStart: Callback when upload starts
 */

"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState, useEffect } from "react";
import {
  completeDirectUpload,
  failDirectUpload,
  getUploadCapabilities,
  initDirectUpload,
  probeVideoDuration,
  uploadFileToSignedUrl,
  uploadVideo,
} from "../lib/api";

interface BrandKit {
  id: string;
  name: string;
  font_name: string;
  font_size: number;
  bold: boolean;
  is_default: boolean;
}

interface UploadFormWithBrandKitProps {
  userId?: string;
  defaultBrandKitId?: string;
  onUploadStart?: () => void;
}

export default function UploadFormWithBrandKit({
  userId,
  defaultBrandKitId,
  onUploadStart,
}: UploadFormWithBrandKitProps) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [brandKits, setBrandKits] = useState<BrandKit[]>([]);
  const [selectedBrandKitId, setSelectedBrandKitId] = useState<string | null>(
    defaultBrandKitId || null
  );
  const [showBrandKitSettings, setShowBrandKitSettings] = useState(false);
  const [loadingBrandKits, setLoadingBrandKits] = useState(false);

  // Load brand kits on mount
  useEffect(() => {
    if (userId) {
      fetchBrandKits();
    }
  }, [userId]);

  const fetchBrandKits = async () => {
    if (!userId) return;
    
    try {
      setLoadingBrandKits(true);
      const response = await fetch("/brand-kits", {
        headers: {
          Authorization: `Bearer ${userId}`,
        },
      });
      
      if (!response.ok) {
        console.warn("Failed to fetch brand kits");
        return;
      }
      
      const data = await response.json();
      const kits = data.brand_kits || [];
      setBrandKits(kits);
      
      // Auto-select first default, or first available
      if (!selectedBrandKitId) {
        const defaultKit = kits.find((b: BrandKit) => b.is_default);
        const firstKit = kits[0];
        if (defaultKit) {
          setSelectedBrandKitId(defaultKit.id);
        } else if (firstKit) {
          setSelectedBrandKitId(firstKit.id);
        }
      }
    } catch (err) {
      console.error("Error fetching brand kits:", err);
    } finally {
      setLoadingBrandKits(false);
    }
  };

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose an MP4 or MOV file before starting the job.");
      return;
    }

    setIsSubmitting(true);
    setError(null);
    let directUploadSession: { job_id: string } | null = null;
    try {
      if (onUploadStart) {
        onUploadStart();
      }

      const uploadCapabilities = await getUploadCapabilities();
      const durationSeconds = await probeVideoDuration(file);

      if (uploadCapabilities.direct_upload) {
        try {
          const session = await initDirectUpload(
            file,
            durationSeconds,
            userId,
            selectedBrandKitId || undefined,
          );
          directUploadSession = { job_id: session.job_id };
          await uploadFileToSignedUrl(session.upload_url, file);
          await completeDirectUpload(session.job_id);
          router.push(`/jobs/${session.job_id}`);
          return;
        } catch (directUploadError) {
          const message =
            directUploadError instanceof Error ? directUploadError.message : "";
          if (directUploadSession) {
            await failDirectUpload(directUploadSession.job_id, message || "Direct upload failed.");
          }
          throw directUploadError;
        }
      }

      const response = await uploadVideo(file, userId, selectedBrandKitId || undefined);
      router.push(`/jobs/${response.job_id}`);
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Upload failed. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="upload-form-container">
      <form className="upload-form" onSubmit={handleSubmit}>
        {/* File Input */}
        <label className="field">
          <div style={{ marginBottom: 8, fontWeight: 700 }}>Source video</div>
          <input
            accept=".mp4,.mov,video/mp4,video/quicktime"
            disabled={isSubmitting}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            type="file"
          />
        </label>

        {/* Brand Kit Selector */}
        {userId && (
          <div className="field" style={{ marginTop: 16, marginBottom: 16 }}>
            <div style={{ marginBottom: 8, fontWeight: 700 }}>
              Brand Kit (Optional)
            </div>
            
            <div style={{ display: "flex", gap: 8 }}>
              <select
                value={selectedBrandKitId || ""}
                onChange={(e) => setSelectedBrandKitId(e.target.value || null)}
                disabled={isSubmitting || loadingBrandKits}
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  borderRadius: "4px",
                  border: "1px solid #ccc",
                  backgroundColor: "#fff",
                  fontSize: "14px",
                }}
              >
                <option value="">
                  {loadingBrandKits ? "Loading..." : "Standard (No brand kit)"}
                </option>
                {brandKits.map((kit) => (
                  <option key={kit.id} value={kit.id}>
                    {kit.name}
                    {kit.is_default ? " (Default)" : ""}
                  </option>
                ))}
              </select>
              
              <button
                type="button"
                onClick={() => setShowBrandKitSettings(true)}
                style={{
                  padding: "8px 16px",
                  borderRadius: "4px",
                  border: "1px solid #ccc",
                  backgroundColor: "#f5f5f5",
                  cursor: "pointer",
                  fontSize: "14px",
                }}
              >
                Manage Kits
              </button>
            </div>

            {selectedBrandKitId && (
              <div
                style={{
                  marginTop: 8,
                  padding: "8px 12px",
                  backgroundColor: "#f0f0f0",
                  borderRadius: "4px",
                  fontSize: "13px",
                  color: "#666",
                }}
              >
                <strong>Preview:</strong> Your captions will be styled with the selected brand kit
              </div>
            )}
          </div>
        )}

        {/* Submit Button */}
        <div className="upload-row">
          <button className="button" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Uploading..." : "Generate clips"}
          </button>
          {file ? <span className="note">{file.name}</span> : null}
        </div>

        {/* Error Display */}
        {error ? <div className="alert">{error}</div> : null}
      </form>

      {/* Brand Kit Settings Modal (Placeholder) */}
      {showBrandKitSettings && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: "rgba(0,0,0,0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              backgroundColor: "white",
              borderRadius: "8px",
              padding: "24px",
              maxWidth: "500px",
              width: "90%",
              maxHeight: "80vh",
              overflowY: "auto",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "16px",
              }}
            >
              <h2 style={{ margin: 0, fontSize: "20px", fontWeight: "bold" }}>
                Manage Brand Kits
              </h2>
              <button
                onClick={() => setShowBrandKitSettings(false)}
                style={{
                  background: "none",
                  border: "none",
                  fontSize: "24px",
                  cursor: "pointer",
                  color: "#999",
                }}
              >
                ✕
              </button>
            </div>

            {/* TODO: Import and render BrandKitSettings component here */}
            <div
              style={{
                padding: "16px",
                backgroundColor: "#f5f5f5",
                borderRadius: "4px",
                textAlign: "center",
                color: "#666",
              }}
            >
              <p>
                Import BrandKitSettings component to enable full brand kit management UI.
              </p>
              <p style={{ fontSize: "12px", marginTop: "8px" }}>
                For now, use the dropdown above to select from existing brand kits.
              </p>
            </div>

            <div style={{ display: "flex", gap: "8px", marginTop: "16px" }}>
              <button
                onClick={() => setShowBrandKitSettings(false)}
                style={{
                  flex: 1,
                  padding: "10px",
                  borderRadius: "4px",
                  border: "1px solid #ccc",
                  backgroundColor: "#f5f5f5",
                  cursor: "pointer",
                  fontSize: "14px",
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
