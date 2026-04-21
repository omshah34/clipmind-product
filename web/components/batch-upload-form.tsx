/**
 * File: components/batch-upload-form.tsx
 * Purpose: Multi-file upload form for batching videos into campaigns.
 */

'use client';

import React, { useState, useRef } from 'react';
import { batchUploadToCampaign } from '@/lib/api';

type BatchUploadFormProps = {
  campaignId: string;
  userId: string;
  onUploadComplete?: (jobIds: string[]) => void;
};

export default function BatchUploadForm({
  campaignId,
  userId,
  onUploadComplete,
}: BatchUploadFormProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<{ [key: string]: number }>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files || []);
    setFiles([...files, ...selected]);
    setError(null);
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  }

  function handleRemoveFile(index: number) {
    setFiles(files.filter((_, i) => i !== index));
  }

  async function handleUpload() {
    if (files.length === 0) {
      setError('No files selected');
      return;
    }

    try {
      setUploading(true);
      setError(null);
      setSuccess(null);

      const response = await batchUploadToCampaign(campaignId, userId, files);

      setSuccess(
        `Uploaded ${response.total_uploaded} video(s). Processing ${response.uploaded_jobs.length} jobs...`,
      );
      setFiles([]);
      setUploadProgress({});

      if (onUploadComplete) {
        onUploadComplete(response.uploaded_jobs);
      }

      if (response.errors.length > 0) {
        console.warn('Upload errors:', response.errors);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  }

  const totalSize = files.reduce((sum, f) => sum + f.size, 0);
  const maxSize = 10 * 1024 * 1024 * 1024; // 10GB limit

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
      <h3 className="mb-4 text-lg font-semibold text-gray-900">Batch Upload Videos</h3>

      {/* File input area */}
      <div
        className="mb-4 rounded-lg border-2 border-dashed border-gray-300 p-6 text-center hover:border-gray-400 transition-colors cursor-pointer"
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="video/*"
          onChange={handleFileSelect}
          className="hidden"
        />
        <div className="text-4xl mb-2">📹</div>
        <p className="font-medium text-gray-900">Click to upload or drag videos here</p>
        <p className="text-sm text-gray-600">Supports MP4, MOV, WebM (max 10GB total)</p>
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="mb-4 space-y-2">
          <div className="flex items-center justify-between">
            <h4 className="font-medium text-gray-900">{files.length} file(s) selected</h4>
            <span className="text-sm text-gray-600">
              {(totalSize / 1024 / 1024).toFixed(1)}MB /{' '}
              {(maxSize / 1024 / 1024 / 1024).toFixed(0)}GB
            </span>
          </div>

          {files.map((file, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between rounded-lg bg-gray-50 p-2"
            >
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium text-gray-900">{file.name}</p>
                <p className="text-xs text-gray-600">
                  {(file.size / 1024 / 1024).toFixed(1)}MB
                </p>
              </div>
              <button
                type="button"
                onClick={() => handleRemoveFile(idx)}
                disabled={uploading}
                className="ml-2 text-red-600 hover:text-red-700 disabled:text-gray-400 text-sm font-medium"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Error/Success messages */}
      {error && (
        <div className="mb-4 rounded-lg bg-red-50 p-3">
          <p className="text-sm text-red-900">{error}</p>
        </div>
      )}

      {success && (
        <div className="mb-4 rounded-lg bg-green-50 p-3">
          <p className="text-sm text-green-900">{success}</p>
        </div>
      )}

      {/* Upload button */}
      <button
        onClick={handleUpload}
        disabled={uploading || files.length === 0 || totalSize > maxSize}
        className="w-full rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
      >
        {uploading ? (
          <span className="flex items-center justify-center">
            <span className="mr-2 h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"></span>
            Uploading...
          </span>
        ) : (
          `Upload ${files.length} video${files.length === 1 ? '' : 's'}`
        )}
      </button>
    </div>
  );
}
