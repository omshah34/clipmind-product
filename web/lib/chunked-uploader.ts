/**
 * File: lib/chunked-uploader.ts
 * Purpose: Gap 240 — ETag-verified resumable chunked upload.
 *
 * Problem solved
 * ──────────────
 * The previous `uploadFileToSignedUrl` helper did a single PUT of the entire
 * file body. On a flaky network the request would time-out partway through,
 * forcing the user to restart the whole upload from scratch.
 *
 * This module splits the file into fixed-size chunks (default 8 MB), uploads
 * each chunk separately, records the ETag returned by the server, and on any
 * retry verifies whether each part was already committed via the `/verify`
 * endpoint before re-sending. Only missing or corrupted parts are re-uploaded.
 *
 * Session state is persisted in `sessionStorage` so a page refresh within the
 * same browser session can resume from the last good chunk.
 *
 * Backend contract (handled by api/routes/upload.py multipart endpoints)
 * ───────────────────────────────────────────────────────────────────────
 *   POST /api/v1/upload/multipart/init
 *     body: { filename, size_bytes, total_parts }
 *     → { upload_id, part_urls: string[] }   (one presigned URL per part)
 *
 *   PUT <part_url>                             (signed upload for each part)
 *     → ETag in response header
 *
 *   POST /api/v1/upload/multipart/verify
 *     body: { upload_id, part_number, etag }
 *     → { verified: boolean }
 *
 *   POST /api/v1/upload/multipart/complete
 *     body: { upload_id, parts: Array<{ part_number, etag }> }
 *     → { source_video_url }
 */

import { API_BASE_URL } from "./api";

// ── Constants ─────────────────────────────────────────────────────────────────

/** Default chunk size: 8 MB (matches Supabase multipart minimum). */
const DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024;

/** Maximum number of times to retry a failed chunk upload. */
const MAX_PART_RETRIES = 3;

/** Base delay (ms) for exponential backoff on part failures. */
const RETRY_BASE_DELAY_MS = 1_000;

// ── Types ─────────────────────────────────────────────────────────────────────

export type ChunkedUploadSession = {
  uploadId: string;
  filename: string;
  totalParts: number;
  /** ETag keyed by 1-based part number (persisted in sessionStorage). */
  committedParts: Record<number, string>;
};

export type UploadProgressCallback = (params: {
  uploadedParts: number;
  totalParts: number;
  uploadedBytes: number;
  totalBytes: number;
}) => void;

// ── SessionStorage helpers ────────────────────────────────────────────────────

const SESSION_KEY_PREFIX = "cm_multipart_";

function saveSession(session: ChunkedUploadSession): void {
  try {
    sessionStorage.setItem(
      `${SESSION_KEY_PREFIX}${session.uploadId}`,
      JSON.stringify(session)
    );
  } catch {
    // sessionStorage unavailable (SSR / private browsing) — continue without persistence
  }
}

function loadSession(uploadId: string): ChunkedUploadSession | null {
  try {
    const raw = sessionStorage.getItem(`${SESSION_KEY_PREFIX}${uploadId}`);
    return raw ? (JSON.parse(raw) as ChunkedUploadSession) : null;
  } catch {
    return null;
  }
}

function clearSession(uploadId: string): void {
  try {
    sessionStorage.removeItem(`${SESSION_KEY_PREFIX}${uploadId}`);
  } catch {
    /* ignore */
  }
}

// ── Backend helpers ───────────────────────────────────────────────────────────

async function initMultipartUpload(
  filename: string,
  sizeBytes: number,
  totalParts: number
): Promise<{ upload_id: string; part_urls: string[] }> {
  const response = await fetch(`${API_BASE_URL}/upload/multipart/init`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename, size_bytes: sizeBytes, total_parts: totalParts }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(
      (err as { message?: string }).message ?? "Failed to initialise multipart upload."
    );
  }
  return response.json();
}

async function verifyPart(
  uploadId: string,
  partNumber: number,
  etag: string
): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/upload/multipart/verify`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ upload_id: uploadId, part_number: partNumber, etag }),
    });
    if (!response.ok) return false;
    const data = (await response.json()) as { verified?: boolean };
    return data.verified === true;
  } catch {
    return false;
  }
}

async function completeMultipartUpload(
  uploadId: string,
  parts: Array<{ part_number: number; etag: string }>
): Promise<string> {
  const response = await fetch(`${API_BASE_URL}/upload/multipart/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ upload_id: uploadId, parts }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(
      (err as { message?: string }).message ?? "Failed to complete multipart upload."
    );
  }
  const data = (await response.json()) as { source_video_url: string };
  return data.source_video_url;
}

// ── Part upload with ETag verification & retry ────────────────────────────────

async function uploadPart(
  partUrl: string,
  chunk: Blob,
  attempt = 1
): Promise<string> {
  const response = await fetch(partUrl, {
    method: "PUT",
    headers: { "Content-Type": "application/octet-stream" },
    body: chunk,
  });

  if (!response.ok) {
    if (attempt < MAX_PART_RETRIES) {
      await new Promise((r) =>
        setTimeout(r, RETRY_BASE_DELAY_MS * 2 ** (attempt - 1))
      );
      return uploadPart(partUrl, chunk, attempt + 1);
    }
    throw new Error(`Part upload failed after ${MAX_PART_RETRIES} attempts (HTTP ${response.status}).`);
  }

  // S3 / Supabase returns the ETag in the response header.
  const etag =
    response.headers.get("etag") ??
    response.headers.get("ETag") ??
    "";

  if (!etag) {
    // Some reverse-proxies strip the ETag. Fall back to a client-side hash.
    console.warn("[chunked-uploader] Server did not return ETag for part — using client-side hash fallback.");
    const buffer = await chunk.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
  }

  // Strip surrounding quotes that S3 adds (e.g. `"d41d8cd98f00..."` → `d41d8cd98f00...`)
  return etag.replace(/^"|"$/g, "");
}

// ── Main public API ───────────────────────────────────────────────────────────

/**
 * Upload `file` in fixed-size chunks with ETag-based resumability (Gap 240).
 *
 * @param file            The File to upload.
 * @param existingSession Optional session to resume. Omit for a fresh upload.
 * @param onProgress      Called after each committed chunk.
 * @param chunkSize       Bytes per chunk. Defaults to 8 MB.
 * @returns               The canonical `source_video_url` produced by the server.
 */
export async function uploadFileChunked(
  file: File,
  existingSession?: string, // uploadId of a previously started session to resume
  onProgress?: UploadProgressCallback,
  chunkSize: number = DEFAULT_CHUNK_SIZE
): Promise<string> {
  const totalParts = Math.ceil(file.size / chunkSize);

  // ── 1. Initialise or resume session ─────────────────────────────────────────
  let session: ChunkedUploadSession;
  let partUrls: string[];

  if (existingSession) {
    // Try to reload persisted progress
    const saved = loadSession(existingSession);
    if (saved && saved.filename === file.name && saved.totalParts === totalParts) {
      session = saved;
      // Re-init to get fresh presigned URLs (they may have expired)
      const { upload_id, part_urls } = await initMultipartUpload(
        file.name,
        file.size,
        totalParts
      );
      partUrls = part_urls;
      // Keep upload_id stable if the server returns the same session
      session = { ...session, uploadId: upload_id };
    } else {
      // Saved session is stale / mismatched — start fresh
      const { upload_id, part_urls } = await initMultipartUpload(
        file.name,
        file.size,
        totalParts
      );
      session = { uploadId: upload_id, filename: file.name, totalParts, committedParts: {} };
      partUrls = part_urls;
    }
  } else {
    const { upload_id, part_urls } = await initMultipartUpload(
      file.name,
      file.size,
      totalParts
    );
    session = { uploadId: upload_id, filename: file.name, totalParts, committedParts: {} };
    partUrls = part_urls;
  }

  saveSession(session);

  // ── 2. Upload each missing / unverified part ──────────────────────────────
  let uploadedBytes = Object.keys(session.committedParts).length * chunkSize;

  for (let i = 0; i < totalParts; i++) {
    const partNumber = i + 1; // 1-based
    const existingEtag = session.committedParts[partNumber];

    // ETag verification: if we have a stored ETag, ask the server to confirm
    // the part is intact before skipping the re-upload.
    if (existingEtag) {
      const verified = await verifyPart(session.uploadId, partNumber, existingEtag);
      if (verified) {
        onProgress?.({
          uploadedParts: Object.keys(session.committedParts).length,
          totalParts,
          uploadedBytes,
          totalBytes: file.size,
        });
        continue; // Part already committed and ETag-verified — skip.
      }
      // Verification failed: ETag mismatch or part missing on server — re-upload.
      console.warn(`[chunked-uploader] ETag verification failed for part ${partNumber} — re-uploading.`);
    }

    // Slice the file into a chunk
    const start = i * chunkSize;
    const end = Math.min(start + chunkSize, file.size);
    const chunk = file.slice(start, end);

    // Upload with retry + ETag capture
    const etag = await uploadPart(partUrls[i], chunk);

    // Persist ETag immediately after each successful part
    session.committedParts[partNumber] = etag;
    saveSession(session);

    uploadedBytes += chunk.size;
    onProgress?.({
      uploadedParts: Object.keys(session.committedParts).length,
      totalParts,
      uploadedBytes: Math.min(uploadedBytes, file.size),
      totalBytes: file.size,
    });
  }

  // ── 3. Complete the multipart upload ─────────────────────────────────────
  const parts = Object.entries(session.committedParts).map(([partNum, etag]) => ({
    part_number: parseInt(partNum, 10),
    etag,
  }));

  const sourceVideoUrl = await completeMultipartUpload(session.uploadId, parts);

  // Clean up session storage now that the upload is committed
  clearSession(session.uploadId);

  return sourceVideoUrl;
}

/**
 * Determine whether a file should use chunked upload vs. single-PUT.
 *
 * Files ≥ 100 MB benefit from resumability. Smaller files are not
 * worth the overhead of multipart initialisation.
 */
export function shouldUseChunkedUpload(file: File): boolean {
  return file.size >= 100 * 1024 * 1024; // 100 MB threshold
}
