export type UploadResponse = {
  job_id: string;
  status: string;
  created_at: string;
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

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";


async function readResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json()) as ErrorPayload;
    throw new Error(payload.message || "Request failed.");
  }
  return (await response.json()) as T;
}


export async function uploadVideo(file: File): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/upload`, {
    method: "POST",
    body: formData,
  });

  return readResponse<UploadResponse>(response);
}


export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const response = await fetch(`${API_BASE_URL}/jobs/${jobId}/status`, {
    cache: "no-store",
  });
  return readResponse<JobStatusResponse>(response);
}
