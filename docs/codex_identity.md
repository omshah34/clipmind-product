# ClipMind Codex Identity

## Product Summary

ClipMind is an AI SaaS product that turns long-form videos into short, vertical, ready-to-post clips for YouTube Shorts, Instagram Reels, and TikTok.

The main value is not basic video trimming. The main value is selecting the best moments automatically using transcript-aware AI scoring. A creator should be able to upload a 60-minute video and receive 3 strong, caption-burned, vertically formatted clips without touching a timeline editor.

---

## Primary Users

- Podcasters
- YouTubers
- Interview creators
- Personal brand creators
- Agencies repurposing long-form content

---

## Core Problem

Creators have long videos, but manually finding strong short-form moments takes too much time. ClipMind reduces that entire workflow to:

```
Upload video → process in background → return the best 3 clips
```

---

## Input Constraints

All uploaded videos must meet these requirements before processing begins:

```
Accepted formats:     MP4, MOV
Maximum file size:    2 GB
Maximum duration:     90 minutes
Minimum duration:     2 minutes
```

If a file violates any constraint, the backend must reject it immediately at upload time with a clear error message. Do not queue invalid files for processing.

---

## Output Specifications

Every exported clip must meet these exact technical specs:

```
Resolution:           1080 x 1920 (9:16 vertical)
Video codec:          H.264
Audio codec:          AAC
Format:               MP4
Minimum clip length:  25 seconds
Maximum clip length:  60 seconds
Caption style:        Bold, centered, word-level animated
```

"Vertical format" means a 9:16 crop at 1080x1920. This must be enforced by FFmpeg at export time, not assumed.

---

## MVP Goal

The first version of ClipMind must:

- Accept one uploaded MP4 or MOV video
- Process the video asynchronously in the background
- Find the top 3 viral clip candidates using AI scoring
- Export each clip in 1080x1920 vertical format
- Burn in captions with accurate word-level timing
- Let the user preview and download the final clips

---

## Core Workflow

```
1.  User uploads a source video via the frontend.
2.  Backend validates file format, size, and duration.
3.  Backend stores the original file in object storage.
4.  Backend creates a job record and returns job_id immediately.
5.  Celery worker picks up the job from the queue.
6.  FFmpeg extracts audio from the source video.
7.  Whisper API transcribes audio with word-level timestamps.
8.  LLM scores transcript segments across 5 dimensions.
9.  System selects the top qualifying clip candidates.
10. FFmpeg cuts each selected clip from the source video.
11. FFmpeg crops each clip to 9:16 vertical format.
12. Captions are rendered and burned into each clip.
13. Final clips are exported, stored, and marked ready.
14. Frontend displays clips for preview and download.
```

---

## Job Architecture

ClipMind must use fully asynchronous processing. Video jobs must never block a normal API request.

**On upload:**
- Validate the file immediately
- Store the file in object storage
- Create a job record in the database with status `uploaded`
- Return `job_id` to the frontend instantly

**Background processing:**
- A Celery worker picks up the job
- Each pipeline stage updates the job status in the database
- The frontend polls `/jobs/{job_id}/status` every 4 seconds until status is `completed` or `failed`
- Do not poll faster than every 4 seconds — this will hammer the backend unnecessarily

### Job States

```
uploaded           File received and stored, not yet queued
queued             Job is waiting for a worker
extracting_audio   FFmpeg is pulling audio from the source video
transcribing       Whisper API is processing the audio
detecting_clips    LLM is scoring transcript segments
cutting_video      FFmpeg is cutting the selected clips
rendering_captions Captions are being burned into each clip
exporting          Final clips are being packaged and stored
completed          All clips are ready for preview and download
failed             Pipeline stopped — error reason and stage stored
retrying           Job is being retried after a recoverable failure
cancelled          Job was cancelled by the user or system
```

### Failure Handling

- If any stage fails, the job must be marked `failed` immediately.
- The job record must store: the stage where it failed, the error message, and a timestamp.
- Transient failures (network timeouts, API rate limits) should trigger a retry up to 3 times before marking `failed`.
- The frontend must show the failure reason clearly, not a generic error.

---

## Database Schema

All job state must be stored in a single `jobs` table. Codex must use exactly these column names across all files — models, routes, workers, and services.

### jobs table

```
id                    UUID            primary key, auto-generated
status                VARCHAR         current job state (see Job States)
source_video_url      TEXT            storage URL of the original uploaded file
audio_url             TEXT            storage URL of the extracted audio file
transcript_json       JSONB           full Whisper output with word-level timestamps
clips_json            JSONB           array of selected clip objects with scores and URLs
failed_stage          VARCHAR         nullable — name of the stage where failure occurred
error_message         TEXT            nullable — human-readable error detail
retry_count           INTEGER         number of retry attempts so far, default 0
prompt_version        VARCHAR         version of clip detection prompt used (e.g. "v4")
estimated_cost_usd    DECIMAL(10,6)   pre-job cost estimate based on video duration
actual_cost_usd       DECIMAL(10,6)   real cost recorded after job completes
created_at            TIMESTAMP       when the job record was created
updated_at            TIMESTAMP       last time any field on this record changed
```

### SQL Migration

This is the exact SQL to create the jobs table. Use this in the migration file. Do not write a different CREATE TABLE anywhere in the codebase.

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS jobs (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    status              VARCHAR(50)     NOT NULL DEFAULT 'uploaded',
    source_video_url    TEXT            NOT NULL,
    audio_url           TEXT,
    transcript_json     JSONB,
    clips_json          JSONB,
    failed_stage        VARCHAR(50),
    error_message       TEXT,
    retry_count         INTEGER         NOT NULL DEFAULT 0,
    prompt_version      VARCHAR(20)     NOT NULL DEFAULT 'v4',
    estimated_cost_usd  DECIMAL(10,6)   NOT NULL DEFAULT 0,
    actual_cost_usd     DECIMAL(10,6)   NOT NULL DEFAULT 0,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
```

Also add a trigger to auto-update `updated_at` on every row change:

```sql
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER jobs_updated_at
BEFORE UPDATE ON jobs
FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

### clips_json structure

Each item in the `clips_json` array must follow this exact shape:

```json
{
  "clip_index": 1,
  "start_time": 82.4,
  "end_time": 134.1,
  "duration": 51.7,
  "clip_url": "https://storage.../clip_1.mp4",
  "hook_score": 8.5,
  "emotion_score": 7.0,
  "clarity_score": 9.0,
  "story_score": 6.5,
  "virality_score": 7.5,
  "final_score": 7.85,
  "reason": "Opens with a bold contrarian claim about money that stops scrolling."
}
```

---

## Pydantic Models

These are the canonical Pydantic models for `api/models/job.py`. Every route, worker, and service must import from this file. Do not redefine these models elsewhere.

```python
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


class ClipResult(BaseModel):
    clip_index: int
    start_time: float
    end_time: float
    duration: float
    clip_url: str
    hook_score: float
    emotion_score: float
    clarity_score: float
    story_score: float
    virality_score: float
    final_score: float
    reason: str


class ClipSummary(BaseModel):
    """Lightweight version returned in status polling responses."""
    clip_index: int
    clip_url: str
    duration: float
    final_score: float
    reason: str


class JobRecord(BaseModel):
    """Full DB row shape. Used internally in workers and services."""
    id: uuid.UUID
    status: str
    source_video_url: str
    audio_url: Optional[str] = None
    transcript_json: Optional[dict] = None
    clips_json: Optional[List[ClipResult]] = None
    failed_stage: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    prompt_version: str = "v4"
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    """Response shape for POST /upload."""
    job_id: uuid.UUID
    status: str
    created_at: datetime


class JobStatusResponse(BaseModel):
    """Response shape for GET /jobs/{job_id}/status."""
    job_id: uuid.UUID
    status: str
    failed_stage: Optional[str] = None
    error_message: Optional[str] = None
    clips: Optional[List[ClipSummary]] = None


class JobClipsResponse(BaseModel):
    """Response shape for GET /jobs/{job_id}/clips."""
    job_id: uuid.UUID
    clips: List[ClipResult]


class ErrorResponse(BaseModel):
    """Standard error shape for all 4xx responses."""
    error: str
    message: str
```

---

## API Contract

All endpoints must follow this contract exactly. Frontend and backend must agree on these shapes — do not invent additional fields.

---

### POST /upload

Accepts a video file and creates a processing job.

**Request:**
```
Content-Type: multipart/form-data
Body: file (MP4 or MOV, max 2GB)
```

**Response 200:**
```json
{
  "job_id": "uuid-here",
  "status": "uploaded",
  "created_at": "2024-01-01T00:00:00Z"
}
```

**Response 400 (validation failure):**
```json
{
  "error": "invalid_file",
  "message": "File exceeds maximum allowed size of 2GB."
}
```

Possible error codes: `invalid_format`, `file_too_large`, `duration_too_short`, `duration_too_long`

---

### GET /jobs/{job_id}/status

Returns current job state. Frontend polls this endpoint every 4 seconds until status is `completed` or `failed`.

**Response — job in progress:**
```json
{
  "job_id": "uuid-here",
  "status": "transcribing",
  "failed_stage": null,
  "error_message": null,
  "clips": null
}
```

**Response — job completed:**
```json
{
  "job_id": "uuid-here",
  "status": "completed",
  "failed_stage": null,
  "error_message": null,
  "clips": [
    {
      "clip_index": 1,
      "clip_url": "https://storage.../clip_1.mp4",
      "duration": 51.7,
      "final_score": 7.85,
      "reason": "Opens with a bold contrarian claim."
    }
  ]
}
```

**Response — job failed:**
```json
{
  "job_id": "uuid-here",
  "status": "failed",
  "failed_stage": "transcribing",
  "error_message": "Whisper API timeout after 3 retries.",
  "clips": null
}
```

---

### GET /jobs/{job_id}/clips

Returns full clip details including all scores. Only valid when status is `completed`.

**Response 200:**
```json
{
  "job_id": "uuid-here",
  "clips": [
    {
      "clip_index": 1,
      "start_time": 82.4,
      "end_time": 134.1,
      "duration": 51.7,
      "clip_url": "https://storage.../clip_1.mp4",
      "hook_score": 8.5,
      "emotion_score": 7.0,
      "clarity_score": 9.0,
      "story_score": 6.5,
      "virality_score": 7.5,
      "final_score": 7.85,
      "reason": "Opens with a bold contrarian claim about money that stops scrolling."
    }
  ]
}
```

**Response 409 (job not completed):**
```json
{
  "error": "job_not_ready",
  "message": "Job is still processing. Current status: cutting_video"
}
```

---

## AI Scoring Rules

Each candidate segment from the transcript must be scored across 5 dimensions:

| Dimension           | Description                                                   |
|---------------------|---------------------------------------------------------------|
| Hook Strength       | Does the segment open with something that stops a scroll?     |
| Emotional Energy    | Is there excitement, controversy, surprise, or strong opinion?|
| Story Completeness  | Does it have a mini arc — problem, insight, or resolution?    |
| Standalone Clarity  | Is it fully understandable without watching the full video?   |
| Virality Potential  | Would this make someone stop, watch, and share?               |

Each dimension is scored 0–10. The final score is a weighted average:

```
final_score = (
  hook_strength      * 0.30 +
  emotional_energy   * 0.25 +
  standalone_clarity * 0.20 +
  story_completeness * 0.15 +
  virality_potential * 0.10
)
```

### Selection Rules

- A clip is only selected if its `final_score >= 6.5`.
- If fewer than 3 clips meet the threshold, return only the ones that qualified. Never force 3 weak clips to fill the quota.
- Selected clips must not overlap in source timestamps.
- Prefer clips that start with a strong spoken hook over clips that start mid-thought.

---

## Transcript Chunking Strategy

Long videos produce transcripts too large to send to the LLM in a single API call. The clip detector must chunk the transcript before scoring.

### Rules

- Split the full transcript into overlapping chunks of 5 minutes each.
- Each chunk must overlap with the next by 60 seconds to avoid missing clips that span a chunk boundary.
- Send each chunk to the LLM as a separate API call.
- Collect all candidate clips returned across all chunks.
- De-duplicate and remove any overlapping candidates before final scoring.
- Apply the selection rules to the full merged candidate list.

### Chunk format sent to LLM

Each chunk must be formatted as plain text with timestamps before each line:

```
[00:00] Today I want to talk about the biggest mistake I made
[00:03] when I started my first business and lost everything
[00:07] Most people think the problem is money but it is not
[00:11] The real problem is that nobody told me about this one thing
...
```

Do not send raw Whisper JSON to the LLM. Format it as readable timestamped text before the call.

---

## Clip Detection Prompt Rules

The LLM prompt used for clip detection is a core product asset.

- The active prompt version must be stored in config, not hardcoded in application logic.
- Every job must log which prompt version was used.
- When clip quality regressions occur, prompt version history must allow tracing which version caused them.
- Prompt files live in `/prompts/`, versioned as `clip_detection_v1.txt`, `clip_detection_v2.txt`, etc.
- The active version is set via environment variable: `CLIP_PROMPT_VERSION=v4`.

The prompt must instruct the LLM to:
- Return structured JSON only — no prose, no markdown fences, no explanation outside the JSON
- Include all required score fields and a `reason` string for each candidate
- Reject segments shorter than 25 seconds or longer than 60 seconds
- Return an empty array if no segments meet the quality threshold — never fabricate results

### clip_detection_v1.txt — canonical prompt

This is the exact content of `prompts/clip_detection_v1.txt`. Do not rewrite this prompt
unless creating a new versioned file. This prompt is the active default.

```
You are a viral short-form content strategist. Your job is to find the best clips
from a transcript that would perform well as YouTube Shorts, Instagram Reels, or TikToks.

You will be given a transcript chunk with timestamps. Analyze it and return candidate
clips that meet all of the following criteria:

- Duration between 25 and 60 seconds
- Opens with a strong hook (bold claim, surprising fact, controversy, or strong opinion)
- Contains emotional energy — excitement, frustration, strong conviction, or humor
- Is fully understandable without watching the rest of the video
- Has a clear mini arc — it sets up something and delivers on it

Score each candidate clip on these five dimensions, each from 0 to 10:
- hook_score: how strongly the clip opens
- emotion_score: emotional energy and intensity throughout
- clarity_score: how well it stands alone without context
- story_score: how complete the mini arc feels
- virality_score: overall scroll-stopping potential

Compute final_score as:
  (hook_score * 0.30) + (emotion_score * 0.25) + (clarity_score * 0.20) +
  (story_score * 0.15) + (virality_score * 0.10)

Only include clips with final_score >= 6.5.

Return ONLY a JSON array. No prose. No markdown. No explanation outside the JSON.
If no clips qualify, return an empty array [].

Each item in the array must have exactly these fields:
{
  "start_time": <float, seconds>,
  "end_time": <float, seconds>,
  "hook_score": <float>,
  "emotion_score": <float>,
  "clarity_score": <float>,
  "story_score": <float>,
  "virality_score": <float>,
  "final_score": <float>,
  "reason": "<one sentence explaining why this clip is strong>"
}

Here is the transcript chunk:

{transcript_chunk}
```

---

## FFmpeg Command Reference

Codex must use these exact FFmpeg commands. Do not invent alternatives.

### Extract audio from video

```bash
ffmpeg -i input.mp4 -vn -acodec mp3 -q:a 2 audio.mp3
```

### Cut a clip by timestamp (no re-encode, fast)

```bash
ffmpeg -i input.mp4 -ss 82.4 -to 134.1 -c copy clip_raw.mp4
```

### Crop to 9:16 vertical (1080x1920) with center crop

```bash
ffmpeg -i clip_raw.mp4 \
  -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920" \
  -c:v libx264 -crf 23 -preset fast \
  -c:a aac -b:a 128k \
  clip_vertical.mp4
```

### Burn in SRT captions using FFmpeg subtitle filter

```bash
ffmpeg -i clip_vertical.mp4 \
  -vf "subtitles=captions.srt:force_style='FontName=Arial,FontSize=22,Bold=1,\
Alignment=2,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'" \
  -c:v libx264 -crf 23 -preset fast \
  -c:a aac -b:a 128k \
  clip_final.mp4
```

### Full pipeline in one FFmpeg pass (crop + captions)

```bash
ffmpeg -i clip_raw.mp4 \
  -vf "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,\
subtitles=captions.srt:force_style='FontName=Arial,FontSize=22,Bold=1,\
Alignment=2,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'" \
  -c:v libx264 -crf 23 -preset fast \
  -c:a aac -b:a 128k \
  clip_final.mp4
```

### Notes on FFmpeg usage

- Always use `-c copy` for the initial cut to avoid quality loss from re-encoding.
- Re-encode only once — during the final crop and caption pass.
- `-crf 23` is the quality setting. Lower = better quality, larger file. Do not go above 28.
- `-preset fast` balances speed and compression. Do not use `ultrafast` — quality degrades noticeably.
- The SRT file must be generated from Whisper word-level timestamps before this command runs.

---

## Caption Rendering Rules

Captions are a required part of the output, not optional.

- Use word-level timestamps from Whisper to generate a properly timed SRT file per clip.
- Each SRT entry should contain 3–5 words maximum for readability on mobile.
- Render captions as bold, centered white text with a dark outline, burned directly into the video frame using the FFmpeg subtitle filter above.
- Font size 22 in the FFmpeg command maps to approximately correct mobile-readable size at 1080x1920. Do not reduce it.
- Do not deliver .srt or .vtt files to the user — captions must be burned into the final MP4.

### SRT generation from Whisper output

Convert Whisper word-level timestamps to SRT format before the FFmpeg pass:

```python
def words_to_srt(words: list, max_words_per_line: int = 4) -> str:
    entries = []
    i = 0
    index = 1
    while i < len(words):
        chunk = words[i:i + max_words_per_line]
        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        text = " ".join(w["word"].strip() for w in chunk)
        entries.append(f"{index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n")
        index += 1
        i += max_words_per_line
    return "\n".join(entries)


def format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"
```

The SRT timestamps must be relative to the start of the clip, not the source video. Subtract `clip.start_time` from all word timestamps before generating the SRT.

---

## Cost Awareness

Each job consumes real API costs. These must be tracked per user and per job:

```
Whisper API:    ~$0.006 per minute of audio
LLM scoring:    ~1 API call per transcript chunk (typically 3–10 chunks per video)
```

- Estimate cost before the job starts based on video duration and expected chunk count.
- Record actual cost after each API call and accumulate it on the job record.
- Store both in `estimated_cost_usd` and `actual_cost_usd` columns.
- This data is required before billing can be implemented. Do not skip it in the MVP.

---

## Dependencies — requirements.txt

This is the exact content of `requirements.txt`. Do not add packages not listed here unless a new feature explicitly requires them. Pin all versions.

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
celery==5.3.6
redis==5.0.4
pydantic==2.7.1
python-multipart==0.0.9
openai==1.30.1
supabase==2.4.6
psycopg2-binary==2.9.9
sqlalchemy==2.0.30
alembic==1.13.1
ffmpeg-python==0.2.0
httpx==0.27.0
python-dotenv==1.0.1
tenacity==8.3.0
```

### Package notes

- `openai` — used for both Whisper transcription and LLM clip scoring via the same client.
- `tenacity` — used for retry logic on Whisper and LLM API calls. Do not write manual retry loops.
- `ffmpeg-python` — Python wrapper around FFmpeg. Use it to build FFmpeg commands programmatically. The underlying system `ffmpeg` binary must also be installed.
- `supabase` — used for object storage (file upload/download). Not used as the database ORM.
- `sqlalchemy` + `psycopg2-binary` — used for all database reads and writes via SQLAlchemy Core (not ORM).
- `alembic` — used for database migrations. The SQL migration in this document maps to the initial Alembic migration file.
- `python-multipart` — required by FastAPI to handle `multipart/form-data` file uploads.

---

## Recommended Tech Stack

| Layer               | Tool                                       |
|---------------------|--------------------------------------------|
| Frontend            | Next.js                                    |
| Backend API         | FastAPI                                    |
| Background Jobs     | Celery + Redis                             |
| Transcription       | OpenAI Whisper API                         |
| Clip Detection      | LLM (GPT-4o or Claude) via prompt scoring  |
| Video Processing    | FFmpeg                                     |
| Caption Rendering   | FFmpeg subtitle filter (SRT burned in)     |
| Object Storage      | Supabase Storage                           |
| Database            | PostgreSQL via SQLAlchemy + Alembic        |
| Job Status Polling  | REST polling on `/jobs/{job_id}/status`    |

---

## Project Structure

```
clipmind/
├── api/
│   ├── main.py                   # FastAPI app entry point
│   ├── routes/
│   │   ├── upload.py             # POST /upload
│   │   └── jobs.py               # GET /jobs/{job_id}/status and /clips
│   └── models/
│       └── job.py                # Pydantic models — import from here only
├── workers/
│   ├── celery_app.py             # Celery configuration
│   └── pipeline.py              # Full pipeline orchestrator
├── services/
│   ├── storage.py                # Upload and download from Supabase Storage
│   ├── transcription.py          # Whisper API wrapper
│   ├── clip_detector.py          # Chunking, LLM scoring, segment selection
│   ├── video_processor.py        # FFmpeg audio extraction and clip cutting
│   ├── caption_renderer.py       # SRT generation and FFmpeg caption burning
│   └── cost_tracker.py           # Estimate and record API costs per job
├── db/
│   ├── connection.py             # SQLAlchemy engine and session setup
│   └── queries.py                # All raw SQL queries — no inline SQL elsewhere
├── migrations/
│   └── 001_create_jobs_table.sql # Initial migration using the SQL defined above
├── prompts/
│   └── clip_detection_v1.txt     # Canonical versioned LLM prompt
├── config.py                     # All settings loaded from environment variables
├── requirements.txt              # Pinned dependencies as defined above
└── .env.example                  # Template for required environment variables
```

---

## Environment Variables

```
OPENAI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql://user:password@localhost:5432/clipmind
STORAGE_BUCKET=clipmind-videos
CLIP_PROMPT_VERSION=v4
MAX_UPLOAD_SIZE_MB=2048
MAX_VIDEO_DURATION_MINUTES=90
TRANSCRIPT_CHUNK_MINUTES=5
TRANSCRIPT_CHUNK_OVERLAP_SECONDS=60
POLLING_INTERVAL_SECONDS=4
```

---

## Product Quality Bar

Clip quality is the primary product risk. Infrastructure that works but selects boring moments is a failed product.

The system must prioritize, in order:

1. Strong hook at the start of the clip
2. Emotional or opinionated content in the body
3. Standalone clarity — understandable without the full video
4. Accurate captions with correct timing
5. Clean 9:16 vertical output with no black bars or distortion
6. Fast, reliable background processing with clear status feedback

If clip selection is consistently weak, the product fails regardless of how well the pipeline runs. Prompt iteration is the highest-leverage engineering activity in the early product.

---

## MVP Non-Goals

Do not build these in the first version:

- Auto-posting to social platforms
- Team or agency collaboration features
- Advanced analytics or clip performance tracking
- Complex billing or subscription management
- Clip customization UI (trimming, font changes, color themes)
- Multi-language caption support
- Batch video uploads

Validate clip quality with real creators before adding any of these.

---

## Build Principles For Codex

When working on ClipMind, follow these principles:

- Optimize for end-to-end MVP delivery first — one working vertical slice beats five half-built features
- Keep each pipeline stage independent and separately testable
- Keep prompt logic modular — prompts live in files, not strings inside code
- Make every processing stage observable via job status updates and logs
- Treat prompts and scoring evaluation data as first-class product assets
- Store cost and prompt version on every job record from day one
- Validate inputs strictly at the upload boundary — never let invalid files enter the queue
- Prefer simple, readable service files over clever abstractions in the MVP
- Use the exact FFmpeg commands defined in this document — do not invent alternatives
- All column names, field names, and API response keys must match this document exactly
- All Pydantic models must be imported from `api/models/job.py` — never redefined inline
- All database queries must live in `db/queries.py` — never write inline SQL in routes or workers
- Use `tenacity` for all API retry logic — do not write manual retry loops

---

## First Milestone

Ship this exact thin vertical slice first. Nothing else.

```
Upload one valid video
→ validate and store it
→ process the full pipeline in background
→ chunk transcript and score with LLM
→ return 3 strong clips (or fewer if quality threshold not met)
→ burn captions and crop to 9:16
→ preview and download in the UI
```

This milestone proves the product works end-to-end. All other features wait until this is solid and clips feel genuinely good to real creators.