# ClipMind

ClipMind is an AI-powered clip generator that turns long-form videos into short,
vertical, caption-burned clips for Shorts, Reels, and TikTok.

## MVP Flow

1. Upload one valid MP4 or MOV file
2. Store the source video
3. Queue the job for background processing
4. Extract audio and transcribe with Whisper
5. Score transcript chunks with an LLM
6. Export up to 3 captioned 1080x1920 clips
7. Preview and download the results

## Local Setup

1. Install Python 3.11+
2. Install Node.js 20+
3. Install FFmpeg and ensure `ffmpeg` and `ffprobe` are on `PATH`
4. Copy `.env.example` to `.env`
5. Start infrastructure:

```bash
docker compose up -d
```

6. Install Python dependencies:

```bash
pip install -r requirements.txt
```

7. Run the API:

```bash
uvicorn api.main:app --reload
```

8. Run the Celery worker:

```bash
celery -A workers.pipeline worker --loglevel=info
```

9. Run the web app:

```bash
cd web
npm install
npm run dev
```

## Notes

- The backend stores all job state in the `jobs` table.
- The worker updates status after every pipeline stage.
- The UI polls `/jobs/{job_id}/status` every 4 seconds.
- Prompt files live in `prompts/` and are versioned.
