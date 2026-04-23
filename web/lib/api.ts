/**
 * File: lib/api.ts
 * Purpose: API client utilities. Provides functions for frontend to communicate
 *          with backend endpoints: upload, job status polling, and clip retrieval.
 */

export type UploadResponse = {
  job_id: string;
  status: string;
  created_at: string;
};

export type DirectUploadInitResponse = {
  job_id: string;
  status: string;
  created_at: string;
  upload_url: string;
  source_video_url: string;
};

export type ClipSummary = {
  clip_index: number;
  clip_url: string;
  duration: number;
  final_score: number;
  reason: string;
};

export type JobStatusResponse = {
  job_id: string;
  status: string;
  failed_stage: string | null;
  error_message: string | null;
  clips: ClipSummary[] | null;
};

type ErrorPayload = {
  error: string;
  message: string;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api/v1";
export const API_BASE_URL = `${API_URL}${API_BASE}`;


async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json()) as ErrorPayload;
    throw new Error(payload.message || "Request failed.");
  }
  return (await response.json()) as T;
}


export function probeVideoDuration(file: File): Promise<number> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(video.duration);
    };
    video.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Unable to read the video duration."));
    };
    video.src = url;
  });
}


export async function uploadVideo(
  file: File,
  userId?: string,
  brandKitId?: string,
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  
  const params = new URLSearchParams();
  if (userId) params.append("user_id", userId);
  if (brandKitId) params.append("brand_kit_id", brandKitId);
  
  const url =
    params.size > 0
      ? `${API_BASE_URL}/upload?${params.toString()}`
      : `${API_BASE_URL}/upload`;

  const response = await fetch(url, {
    method: "POST",
    body: formData,
  });

  return readResponse<UploadResponse>(response);
}


export async function uploadVideoFromUrl(
  url: string,
  userId?: string,
  brandKitId?: string,
  language: string = "en",
): Promise<UploadResponse> {
  const response = await fetch(`${API_BASE_URL}/upload/url`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url,
      user_id: userId || null,
      brand_kit_id: brandKitId || null,
      language,
    }),
  });

  return readResponse<UploadResponse>(response);
}


export async function initDirectUpload(
  file: File,
  durationSeconds: number,
  userId?: string,
  brandKitId?: string,
): Promise<DirectUploadInitResponse> {
  const response = await fetch(`${API_BASE_URL}/upload/direct/init`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      filename: file.name,
      size_bytes: file.size,
      duration_seconds: durationSeconds,
      user_id: userId || null,
      brand_kit_id: brandKitId || null,
    }),
  });

  return readResponse<DirectUploadInitResponse>(response);
}


export async function uploadFileToSignedUrl(uploadUrl: string, file: File): Promise<void> {
  const formData = new FormData();
  formData.append("file", file, file.name);

  const response = await fetch(uploadUrl, {
    method: "PUT",
    body: formData,
  });

  if (!response.ok) {
    throw new Error("Browser upload to storage failed.");
  }
}


export async function completeDirectUpload(jobId: string): Promise<UploadResponse> {
  const response = await fetch(`${API_BASE_URL}/upload/direct/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId }),
  });

  return readResponse<UploadResponse>(response);
}


export async function failDirectUpload(jobId: string, message: string): Promise<void> {
  await fetch(`${API_BASE_URL}/upload/direct/fail`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId, message }),
  });
}


export type UserPreferences = {
  user_id: string;
  goals: string[];
  target_platform: string | null;
  preferences_json: Record<string, string | number | boolean | null>;
  onboarding_completed: boolean;
  created_at?: string;
  updated_at?: string;
};

export async function getUserPreferences(userId?: string): Promise<UserPreferences | null> {
  const params = new URLSearchParams();
  if (userId) params.append("user_id", userId);
  const queryString = params.toString();
  const response = await fetch(`${API_BASE_URL}/preferences${queryString ? `?${queryString}` : ""}`, {
    cache: "no-store",
  });
  const data = await readResponse<{ preferences: UserPreferences | null }>(response);
  return data.preferences;
}

export async function saveUserPreferences(
  userId: string,
  payload: {
    goals: string[];
    target_platform?: string | null;
    primary_goal?: string | null;
    metadata?: Record<string, string | number | boolean | null>;
    onboarding_completed?: boolean;
  },
): Promise<UserPreferences> {
  const response = await fetch(`${API_BASE_URL}/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      goals: payload.goals,
      target_platform: payload.target_platform ?? null,
      primary_goal: payload.primary_goal ?? null,
      metadata: payload.metadata ?? {},
      onboarding_completed: payload.onboarding_completed ?? true,
      user_id: userId,
    }),
  });

  const data = await readResponse<{ preferences: UserPreferences }>(response);
  return data.preferences;
}


export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/status`, {
    cache: "no-store",
  });
  return readResponse<JobStatusResponse>(response);
}


// ── Clip streaming / download helpers ─────────────────────────────────────────

/**
 * Returns the full URL for streaming a clip via the backend proxy.
 * Use this as the <video src> so range requests work for seeking.
 */
export function getClipStreamUrl(jobId: string, clipIndex: number): string {
  return `${API_BASE_URL}/jobs/${jobId}/clips/${clipIndex}/stream`;
}

/**
 * Returns the URL that forces a browser file download.
 */
export function getClipDownloadUrl(jobId: string, clipIndex: number): string {
  return `${API_BASE_URL}/jobs/${jobId}/clips/${clipIndex}/download`;
}

/**
 * Programmatically downloads a clip as a file.
 *
 * Uses fetch → Blob → object URL so it works cross-origin (no CORS issues
 * with the <a download> attribute which only works same-origin).
 *
 * Shows a loading state via the optional callbacks.
 */
export async function downloadClip(
  jobId: string,
  clipIndex: number,          // 0-based
  filename: string,
  onStart?: () => void,
  onDone?: () => void,
): Promise<void> {
  onStart?.();
  try {
    const url = getClipDownloadUrl(jobId, clipIndex);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Download failed: ${res.status}`);

    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);

    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);

    // Revoke after a short delay to ensure the download has started.
    setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
  } finally {
    onDone?.();
  }
}


// ── Clip Studio types ─────────────────────────────────────────────────────────

export type ClipPreviewData = {
  job_id: string;
  status: string;
  transcript_words: Array<{ word: string; start: number; end: number }>;
  current_clips: Array<{
    index: number;
    start_time: number;
    end_time: number;
    duration: number;
    final_score: number;
    hook_score: number;
    emotion_score: number;
    clarity_score: number;
    story_score: number;
    virality_score: number;
    reason: string;
    clip_url: string;       // /api/v1/jobs/{id}/clips/{i}/stream
    download_url: string;   // /api/v1/jobs/{id}/clips/{i}/download
  }>;
  regeneration_count: number;
};

export type RegenerateResponse = {
  regen_id: string;
  job_id: string;
  status: string;
  message: string;
};

export type RegenerationResult = {
  regen_id: string;
  requested_at: string;
  completed_at: string;
  weights: Record<string, number>;
  instructions: string | null;
  clips: ClipSummary[]; // Restored type safety here
  status: "pending" | "completed" | "failed";
  error: string | null;
};

export async function getClipPreview(jobId: string): Promise<ClipPreviewData> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/preview`, {
    cache: "no-store",
  });
  return readResponse<ClipPreviewData>(response);
}

export async function regenerateClips(
  jobId: string,
  userId: string,
  clipCount: number = 3,
  customWeights?: Record<string, number>,
  instructions?: string,
): Promise<RegenerateResponse> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/regenerate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${userId}`,
    },
    body: JSON.stringify({
      clip_count: clipCount,
      custom_weights: customWeights,
      instructions: instructions,
    }),
  });
  return readResponse<RegenerateResponse>(response);
}

export async function getHookVariants(
  jobId: string,
  clipIndex: number
): Promise<{ variants: Array<{ start_time: number; label: string; logic: string }> }> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/clips/${clipIndex}/hooks`, {
    cache: "no-store",
  });
  return readResponse<{ variants: Array<{ start_time: number; label: string; logic: string }> }>(response);
}

export async function approveClip(
  jobId: string,
  clipIndex: number,
  userId: string
): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/clips/${clipIndex}/approve`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${userId}`,
    },
  });
  return readResponse<{ status: string; message: string }>(response);
}

export async function discardClip(
  jobId: string,
  clipIndex: number,
  userId: string
): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/clips/${clipIndex}/discard`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${userId}`,
    },
  });
  return readResponse<{ status: string; message: string }>(response);
}

export async function downloadCapcutBridge(
  jobId: string,
  clipIndex: number,
  filename: string,
  onStart?: () => void,
  onDone?: () => void,
): Promise<void> {
  onStart?.();
  try {
    const url = `${API_BASE_URL}/jobs/${jobId}/clips/${clipIndex}/capcut-bridge`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`CapCut Export failed: ${res.status}`);

    const blob = await res.blob();
    const objectUrl = URL.createObjectURL(blob);

    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);

    setTimeout(() => URL.revokeObjectURL(objectUrl), 10_000);
  } finally {
    onDone?.();
  }
}

export async function adjustClipBoundary(
  jobId: string,
  userId: string,
  clipIndex: number,
  newStart: number,
  newEnd: number,
): Promise<{ status: string; message: string }> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/clips/${clipIndex}/adjust`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${userId}`,
    },
    body: JSON.stringify({
      start_time: newStart,
      end_time: newEnd,
    }),
  });
  return readResponse<{ status: string; message: string }>(response);
}

export async function getRegenerations(jobId: string): Promise<{ regenerations: RegenerationResult[] }> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/regenerations`, {
    cache: "no-store",
  });
  return readResponse<{ regenerations: RegenerationResult[] }>(response);
}


// ── Campaign API ──────────────────────────────────────────────────────────────

export type Campaign = {
  id: string;
  name: string;
  description: string | null;
  status: string;
  clip_count: number;
  schedule_config: Record<string, any>;
  created_at: string;
  updated_at: string;
};

export type CampaignListResponse = {
  campaigns: Campaign[];
  total: number;
  limit: number;
  offset: number;
};

export type ScheduleConfig = {
  publish_interval_days?: number;
  publish_hour?: number;
  publish_timezone?: string;
  publish_to_channels?: string[];
  hashtags?: string[];
  caption_template?: string;
  enabled?: boolean;
};

export async function createCampaign(
  userId: string,
  name: string,
  description?: string,
  scheduleConfig?: ScheduleConfig,
): Promise<Campaign> {
  const response = await fetch(`${API_BASE_URL}/campaigns?user_id=${userId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, description, schedule_config: scheduleConfig }),
  });
  return readResponse<Campaign>(response);
}

export async function listCampaigns(
  userId: string,
  limit: number = 20,
  offset: number = 0,
  status?: string,
): Promise<CampaignListResponse> {
  const params = new URLSearchParams({
    user_id: userId,
    limit: limit.toString(),
    offset: offset.toString(),
  });
  if (status) params.append("status", status);
  const response = await fetch(`${API_BASE_URL}/campaigns?${params}`, { cache: "no-store" });
  return readResponse<CampaignListResponse>(response);
}

export async function getCampaign(campaignId: string, userId: string): Promise<Campaign> {
  const response = await fetch(`${API_BASE_URL}/campaigns/${campaignId}?user_id=${userId}`, {
    cache: "no-store",
  });
  return readResponse<Campaign>(response);
}

export async function updateCampaign(
  campaignId: string,
  userId: string,
  updates: Partial<Campaign>,
): Promise<Campaign> {
  const response = await fetch(`${API_BASE_URL}/campaigns/${campaignId}?user_id=${userId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  return readResponse<Campaign>(response);
}

export async function deleteCampaign(campaignId: string, userId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/campaigns/${campaignId}?user_id=${userId}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error("Failed to delete campaign");
}

export type BatchUploadResponse = {
  campaign_id: string;
  uploaded_jobs: string[];
  total_uploaded: number;
  errors: Array<{ filename: string; error: string }>;
  message: string;
};

export async function batchUploadToCampaign(
  campaignId: string,
  userId: string,
  files: File[],
): Promise<BatchUploadResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const response = await fetch(
    `${API_BASE_URL}/campaigns/${campaignId}/upload?user_id=${userId}`,
    { method: "POST", body: formData },
  );
  return readResponse<BatchUploadResponse>(response);
}

export type ClipCalendar = {
  campaign_id: string;
  clips_by_date: Record<string, any[]>;
  total_scheduled_clips: number;
  date_range_start: string;
  date_range_end: string;
};

export async function getCampaignCalendar(
  campaignId: string,
  userId: string,
  daysAhead: number = 30,
): Promise<ClipCalendar> {
  const response = await fetch(
    `${API_BASE_URL}/campaigns/${campaignId}/calendar?user_id=${userId}&days_ahead=${daysAhead}`,
    { cache: "no-store" },
  );
  return readResponse<ClipCalendar>(response);
}

export type CampaignStats = {
  campaign_id: string;
  total_videos_uploaded: number;
  total_clips_detected: number;
  clips_scheduled: number;
  clips_published: number;
  next_publish_date: string | null;
  avg_clip_score: number;
};

export async function getCampaignStats(campaignId: string, userId: string): Promise<CampaignStats> {
  const response = await fetch(
    `${API_BASE_URL}/campaigns/${campaignId}/stats?user_id=${userId}`,
    { cache: "no-store" },
  );
  return readResponse<CampaignStats>(response);
}


// ── Performance API ───────────────────────────────────────────────────────────

export type ClipPerformance = {
  id: string;
  job_id: string;
  clip_index: number;
  platform: string;
  views: number;
  likes: number;
  saves: number;
  shares: number;
  comments: number;
  engagement_score: number;
  save_rate: number;
  share_rate: number;
  comment_rate: number;
  completion_rate: number | null;
  synced_at: string;
};

export type PlatformStats = {
  platform: string;
  total_clips: number;
  total_views: number;
  total_likes: number;
  total_saves: number;
  total_shares: number;
  total_comments: number;
  average_engagement_score: number;
  average_completion_rate: number | null;
};

export type PerformanceSummary = {
  job_id: string;
  total_clips: number;
  platforms: string[];
  total_views: number;
  total_likes: number;
  total_saves: number;
  total_shares: number;
  total_comments: number;
  overall_engagement_score: number;
  average_completion_rate: number | null;
  platform_stats: PlatformStats[];
  top_platform: string;
  best_clip_index: number;
  worst_clip_index: number;
  synced_at: string;
};

export type PerformanceAlert = {
  id: string;
  clip_perf_id: string;
  alert_type: string;
  message: string;
  is_read: boolean;
  created_at: string;
};

export async function getPerformanceSummary(jobId: string, userId: string): Promise<PerformanceSummary> {
  const response = await fetch(`${API_BASE_URL}/performance/jobs/${jobId}`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${userId}` },
  });
  return readResponse<PerformanceSummary>(response);
}

export async function getPerformanceAlerts(
  userId: string,
  unreadOnly: boolean = false,
): Promise<{ alerts: PerformanceAlert[]; total: number; unread_count: number }> {
  const params = new URLSearchParams();
  if (unreadOnly) params.append("unread_only", "true");
  const response = await fetch(`${API_BASE_URL}/performance/alerts?${params.toString()}`, {
    cache: "no-store",
    headers: { Authorization: `Bearer ${userId}` },
  });
  return readResponse<{ alerts: PerformanceAlert[]; total: number; unread_count: number }>(response);
}

export async function markAlertAsRead(alertId: string, userId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/performance/alerts/${alertId}/read`, {
    method: "POST",
    headers: { Authorization: `Bearer ${userId}` },
  });
  if (!response.ok) throw new Error("Failed to mark alert as read");
}
