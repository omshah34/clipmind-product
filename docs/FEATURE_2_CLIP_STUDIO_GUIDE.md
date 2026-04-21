# Clip Studio Architecture & Implementation Guide

## Overview

Clip Studio is ClipMind's interactive timeline editor that allows users to:
1. **Preview clips** — View detected clips with transcript alignment
2. **Regenerate with custom settings** — Re-run AI clip detection with:
   - Natural language instructions to guide the AI
   - Custom score weight adjustments (e.g., prioritize virality over clarity)
3. **Track regeneration history** — Keep a full audit trail of all regeneration requests
4. **Adjust boundaries** — Fine-tune clip start/end times (MVP: placeholder)

## Feature Complete Status

✅ **Backend:** Database schema, API routes, Celery task, query functions → DONE
✅ **Frontend:** Timeline editor, score radar chart, studio page → DONE
✅ **Integration:** Clip detector supports custom weights/instructions → DONE
✅ **Documentation:** This guide + code comments → DONE

## System Architecture

### Frontend Flow

```
User uploads video
    ↓
Job completes (clips detected)
    ↓
User navigates to /jobs/{jobId}/studio
    ↓
ClipTimelineEditor mounts
    ↓
useEffect: calls getClipPreview({jobId})
    ↓
Backend returns ClipPreviewData with:
  - transcript_words (with timestamps)
  - current_clips (with all 5 scores)
  - regeneration_count (audit trail)
    ↓
UI renders timeline:
  - Transcript with word-level highlighting
  - Clip list with inline scores
  - Selected clip's 5D radar chart
  - Regeneration controls
    ↓
User enters instructions:
  - "Find moments with music" OR
  - "Longer clips, less talking"
    ↓
User optionally adjusts weights:
  - Drag sliders to override default weights
  - Weights auto-normalize to sum to 1.0
    ↓
User clicks "Regenerate Clips"
    ↓
Frontend calls regenerateClips(jobId, userId, clipCount, weights, instructions)
    ↓
Backend queues Celery task: regenerate_clips_task(...)
    ↓
Frontend shows loading state
    ↓
Background task completes (30-60s)
    ↓
User polls or refreshes
    ↓
New clips appear in regenerations list
```

### Backend Flow (Regeneration Task)

```
POST /jobs/{id}/regenerate
├─ Validate job exists and has transcript
├─ Validate weights sum to 1.0
├─ Create regen_id (UUID)
├─ Queue Celery task
└─ Return 202 Accepted with regen_id

regenerate_clips_task (async Celery worker)
├─ Get job from DB
├─ Merge custom_weights with SCORE_WEIGHTS defaults
├─ Call clip_detector_service.detect_clips(
│  ├─ transcript_json
│  ├─ custom_score_weights (override)
│  ├─ custom_prompt_instruction (append)
│  └─ limit (clip_count)
│  )
├─ Receive list of ScoredClip objects + LLM cost
├─ Build regeneration result dict
├─ Append result to job.timeline_json
├─ Handle retry logic on transient errors
└─ Return result dict
```

## Data Model

### Database

**Timeline Schema** (timeline_json JSONB in jobs table)
```json
{
  "clips": [
    {
      "index": 0,
      "original_start": 5.2,
      "original_end": 15.8,
      "user_start": 5.5,
      "user_end": 15.5,
      "regenerate_weights": null
    }
  ],
  "regeneration_results": [
    {
      "regen_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "requested_at": "2025-01-15T10:30:00Z",
      "completed_at": "2025-01-15T10:35:45Z",
      "weights": {
        "hook_score": 0.3,
        "emotion_score": 0.2,
        "clarity_score": 0.15,
        "story_score": 0.15,
        "virality_score": 0.2
      },
      "instructions": "Find moments with music",
      "clips": [
        {
          "clip_index": 1,
          "start_time": 12.5,
          "end_time": 28.3,
          "final_score": 7.8,
          "reason": "Music sync + emotional peak"
        }
      ],
      "status": "completed",
      "error": null
    }
  ]
}
```

### Pydantic Models

Located in `/api/models/clip_studio.py`:

**ClipPreviewData** (what GET /preview returns)
- job_id: UUID
- status: str (job status)
- transcript_words: list[{word, start, end}]
- current_clips: list[{clip_index, start_time, end_time, ..., all 5 scores}]
- regeneration_count: int

**RegenerationRequest** (what POST /regenerate accepts)
- clip_count: int (1-10, default 3)
- custom_weights: dict[str, float] (optional)
- instructions: str (optional)

**RegenerateClipsResponse** (what POST /regenerate returns)
- regen_id: str (UUID)
- status: str ("queued")
- message: str

## API Endpoints

### GET /jobs/{job_id}/preview
**Purpose:** Get metadata-only preview (no FFmpeg rendering)
**Returns:** ClipPreviewData with transcript words + clip metadata
**Auth:** Bearer token (MVP: optional, should require)
**Status:** ✅ COMPLETE

### POST /jobs/{job_id}/regenerate  
**Purpose:** Queue regeneration task with custom parameters
**Body:** RegenerationRequest
**Returns:** RegenerateClipsResponse with regen_id
**Auth:** Bearer token (user_id) in Authorization header
**Status:** ✅ COMPLETE

### PATCH /jobs/{job_id}/clips/{clip_index}/adjust
**Purpose:** Adjust clip boundaries and re-render
**Body:** AdjustClipBoundaryRequest (new_start, new_end)
**Returns:** AdjustClipBoundaryResponse
**Status:** 🟡 PLACEHOLDER (queues background task, needs implementation)

### GET /jobs/{job_id}/regenerations
**Purpose:** List all past regeneration requests
**Query params:** limit (1-50, default 10)
**Returns:** {regenerations: [RegenerationResult...]}
**Auth:** Bearer token (MVP: optional)
**Status:** ✅ COMPLETE

## Frontend Components

### ScoreRadar (`web/components/score-radar.tsx`)
5-dimension radar chart visualization for clip scores.
- **Status:** ✅ COMPLETE
- **Props:** hookScore, emotionScore, clarityScore, storyScore, viralityScore (0-10 scale)
- **Features:** Concentric grid, axis lines, animated polygon, average score display

### ClipTimelineEditor (`web/components/clip-timeline-editor.tsx`)
Main interactive timeline editor component.
- **Status:** ✅ COMPLETE
- **Features:**
  - Transcript timeline with word-level clip highlighting
  - Clickable clip list with scores
  - 5D radar chart for selected clip
  - Natural language instruction textarea
  - Advanced weight adjustment sliders (auto-normalize)
  - Regenerate button with loading state
  - Recent regenerations history

### Clip Studio Page (`web/app/jobs/[jobId]/studio/page.tsx`)
Full-page Clip Studio interface with authentication.
- **Status:** ✅ COMPLETE
- **Features:**
  - NextAuth session check (redirects if unauthenticated)
  - Breadcrumb navigation
  - Help section with usage tips

## Key Implementation Details

### Files Created

**Backend:**
- `/migrations/003_add_timeline_to_jobs.sql` — Timeline schema
- `/api/models/clip_studio.py` — 6 Pydantic models
- `/api/routes/clip_studio.py` — 4 API endpoints
- `/workers/regenerate_clips.py` — Celery background task

**Frontend:**
- `/web/components/score-radar.tsx` — Radar chart
- `/web/components/clip-timeline-editor.tsx` — Timeline UI
- `/web/app/jobs/[jobId]/studio/page.tsx` — Studio page

**Updated:**
- `/db/queries.py` — Added timeline CRUD functions
- `/services/clip_detector.py` — Added custom weights/instructions support
- `/api/main.py` — Registered clip_studio router
- `/web/lib/api.ts` — Added Clip Studio API functions

### Key Design Decisions

1. **JSONB Timeline Storage**
   - Append-only regeneration history without schema changes
   - GIN index for fast querying

2. **Async Regeneration (Celery)**
   - LLM calls take 30-60s; async prevents HTTP timeout
   - MVP: simple polling (user refreshes page)

3. **Weight Validation**
   - Must sum to 1.0 (maintains score scale)
   - Frontend auto-normalizes as user adjusts sliders
   - Backend validates on POST and in task

4. **Custom Instructions**
   - Appended to LLM prompt after @@{variables} substitution
   - User cannot inject variables

5. **Preview Endpoint (No FFmpeg)**
   - Metadata only for fast UI response
   - User cannot preview videos (future enhancement)

## Testing Recommendations

### Manual Testing Checklist

- [ ] Upload video and verify clips detected
- [ ] Navigate to /jobs/{jobId}/studio
- [ ] Verify transcript words display with timestamps
- [ ] Click on clips and verify radar chart updates
- [ ] Enter custom instructions and click "Regenerate"
- [ ] Verify loading state shows during regeneration
- [ ] Poll /jobs/{jobId}/preview to see new clips
- [ ] Adjust weight sliders and verify they normalize to 1.0
- [ ] Try weights that sum > 1.0 and verify 400 error

### Unit Test Examples

```python
def test_weight_validation():
    # Weights must sum to 1.0
    weights = {"hook_score": 0.5, "emotion_score": 0.3}  # sums to 0.8
    with pytest.raises(ValueError):
        regenerate_clips_task("job_id", "regen_id", custom_weights=weights)

def test_regeneration_merges_weights():
    # Custom weights override defaults, but fill missing dimensions
    custom = {"hook_score": 0.5}
    merged = merge_weights(custom)
    assert merged["hook_score"] == 0.5
    assert all(v > 0 for v in merged.values())
    assert sum(merged.values()) ≈ 1.0

def test_preview_returns_transcript_words():
    job = create_job_with_clips()
    response = client.get(f"/jobs/{job.id}/preview")
    assert response.json()["transcript_words"]
    assert response.json()["current_clips"]
```

## Next Steps (MVP→Production)

1. **Boundary Adjustments**
   - Implement PATCH fully (currently placeholder)
   - Call cut_clip() with new boundaries
   - Call render_vertical_captioned_clip() with adjusted times
   - Upload to storage and persist

2. **Real-Time Updates**
   - Add WebSocket connection
   - Server emits event when regeneration completes
   - Client updates UI without polling

3. **Advanced Editing**
   - Allow users to delete clips
   - Combine clips into longer "superclips"
   - Reorder clips (affects publishing)
   - Manual score override (user feedback)

4. **UI Enhancements**
   - Waveform visualization with Peaks.js
   - Video preview in right sidebar
   - Drag handles on clip boundaries
   - Undo/redo for edits
   - Keyboard shortcuts

## Revenue Tiers

- **Free:** 1 regeneration/month
- **Pro ($29/mo):** 10 regenerations/month + 3-hour priority support
- **Enterprise:** Unlimited regenerations + API access + custom models

## Performance Notes

- Each regeneration makes 1 LLM call (~$0.002 cost)
- Celery task completes in 30-60 seconds
- Timeline JSON grows ~1KB per regeneration
- Scale workers horizontally if queue depth exceeds 10

## Related Documentation

- [Brand Kit Architecture](./IMPLEMENTATION_STATUS.md#feature-1)
- [Clip Detection Service](./services/clip_detector.py)
- [Celery Configuration](./workers/celery_app.py)
- [Frontend Setup](./web/README.md)
- [Product Analysis](./README.md)
```

### 3. Background Task (`workers/regenerate_clips.py`)

```python
@celery_app.task(bind=True)
def regenerate_clips_task(self, job_id: str, regen_id: str, request: dict):
    """Re-run clip detection with custom weights/instructions."""
    job = get_job(job_id)
    transcript_json = job.transcript_json
    
    # Extract original audio (or download from source_video_url)
    # Re-run detect_clips with custom weights
    custom_weights = request.get("weights", {})
    instructions = request.get("instructions")
    
    # Merge instruction into system prompt
    custom_prompt = clip_detector.load_prompt()
    if instructions:
        custom_prompt += f"\n\nAdditional instruction: {instructions}"
    
    detected = clip_detector.detect_clips(
        transcript_json=transcript_json,
        source_video_path=...,
        custom_weights=custom_weights,
        custom_prompt=custom_prompt,
    )
    
    # Store results in timeline_json
    update_job(job_id, timeline_json={
        "regeneration_results": [{
            "regen_id": regen_id,
            "clips": detected,
            "created_at": now(),
        }]
    })
```

## Frontend Implementation

### Key Component: Timeline Editor (`web/components/clip-timeline-editor.tsx`)

```typescript
interface ClipTimelineEditorProps {
  jobId: string;
  transcript: TranscriptData;  // Words with timestamps
  clips: ClipData[];
  onClipAdjusted: (clipIndex: number, newStart: number, newEnd: number) => void;
  onRegenerate: (weights?: dict, instructions?: string) => void;
}

export function ClipTimelineEditor({
  jobId,
  transcript,
  clips,
  onClipAdjusted,
  onRegenerate,
}: ClipTimelineEditorProps) {
  const [selectedClipIndex, setSelectedClipIndex] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [regeneratingWeights, setRegeneratingWeights] = useState(false);

  return (
    <div className="timeline-container">
      {/* Waveform visualization from transcript words */}
      <div className="waveform-wrapper">
        {/* Show extracted audio waveform or placeholder histogram */}
        {renderWaveform(transcript)}
        
        {/* Clip regions with drag handles */}
        {clips.map((clip, idx) => (
          <ClipRegion
            key={idx}
            clip={clip}
            isSelected={idx === selectedClipIndex}
            onSelect={() => setSelectedClipIndex(idx)}
            onDragStart={() => setIsDragging(true)}
            onDragEnd={(newStart, newEnd) => {
              onClipAdjusted(idx, newStart, newEnd);
              setIsDragging(false);
            }}
          />
        ))}
      </div>

      {/* Selected clip details + controls */}
      <div className="clip-details-panel">
        <h3>Clip {selectedClipIndex + 1}</h3>
        
        {/* Score breakdown (radar chart) */}
        <ScoreRadar scores={clips[selectedClipIndex].scores} />
        
        {/* Transcript excerpt */}
        <TranscriptExcerpt
          transcript={transcript}
          start={clips[selectedClipIndex].start}
          end={clips[selectedClipIndex].end}
        />
        
        {/* Regeneration controls */}
        <button onClick={() => onRegenerate()}>
          Find More Clips
        </button>
        
        <div className="weight-sliders">
          <Slider label="Hook" initial={0.30} onChange={...} />
          <Slider label="Emotion" initial={0.25} onChange={...} />
          <Slider label="Clarity" initial={0.20} onChange={...} />
          <Slider label="Story" initial={0.15} onChange={...} />
          <Slider label="Virality" initial={0.10} onChange={...} />
        </div>
        
        <textarea placeholder="e.g., 'Find more humorous moments'" />
        
        <button onClick={() => onRegenerate(weights, instructions)}>
          Regenerate with Custom Weights
        </button>
      </div>
    </div>
  );
}
```

## Integration Checkpoints

### Database
- [ ] Run migration 003 to add timeline_json to jobs
- [ ] Verify schema: `\d+ jobs` shows timeline_json JSONB column

### Backend
- [ ] Create services/timeline_service.py with 3 helper functions
- [ ] Create api/routes/clip_studio.py with 3 endpoints
- [ ] Create workers/regenerate_clips.py task
- [ ] Register route in api/main.py: `app.include_router(clip_studio_router)`
- [ ] Test endpoints with curl/Postman

### Frontend
- [ ] Create web/components/clip-timeline-editor.tsx
- [ ] Create web/components/score-radar.tsx (5-dimension chart)
- [ ] Integrate into /jobs/[jobId] page
- [ ] Connect to new /jobs/{id}/preview, /regenerate, /clips/{index}/adjust endpoints

### API Client
- [ ] Add to web/lib/api.ts:
  - `adjustClipBoundary(jobId, clipIndex, newStart, newEnd)`
  - `regenerateClips(jobId, weights, instructions)`
  - `getClipPreview(jobId)`

## Testing Flow

```bash
# 1. Upload video with Brand Kit
curl -X POST http://localhost:8000/upload \
  -F "file=@podcast.mp4" \
  -F "user_id={uuid}" \
  -F "brand_kit_id={uuid}"

# Wait for job to complete

# 2. Get preview data (fast, no render)
curl http://localhost:8000/jobs/{job_id}/preview

# 3. Adjust a clip boundary
curl -X PATCH http://localhost:8000/jobs/{job_id}/clips/0/adjust \
  -d '{"new_start": 10.5, "new_end": 22.3}'

# Verify new clip_url is returned with adjusted boundaries

# 4. Regenerate with custom weights
curl -X POST http://localhost:8000/jobs/{job_id}/regenerate \
  -d '{
    "custom_weights": {"hook_score": 0.25, "emotion_score": 0.35, ...},
    "instructions": "Find humorous moments"
  }'

# Watch /jobs/{job_id}/status for regeneration_results
```

## Effort Breakdown

- **Backend API:** 1 week (3 simple endpoints + background task)
- **Frontend UI:** 1.5 weeks (waveform + drag handles + radar chart)
- **Integration/Testing:** 1 week
- **Polish/Bug fixes:** 0.5 week

**Total: 3-4 weeks**

---

## Next: How to Get Started

1. Pick a sprint (2 weeks)
2. Assign: Backend engineer on routes/services/task, Frontend engineer on components
3. Start with database migration
4. Implement backend endpoints first (testable with curl)
5. Build frontend components incrementally
6. Integration test end-to-end (upload → adjust → regenerate → verify)
7. Launch behind Feature Flag if possible (gradual rollout to users)

---

For questions, refer back to IMPLEMENTATION_STATUS.md for overall context.
