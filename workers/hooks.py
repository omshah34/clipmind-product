# File: workers/hooks.py
import logging
from celery import chord, group
from workers.celery_app import celery_app
from workers.pipeline import register_child_task

logger = logging.getLogger(__name__)

@celery_app.task(name="hooks.generate_single")
def generate_single_hook(clip_transcript: str, style: str, job_id: str, variation_idx: int) -> dict:
    """Gap 372: Generate a single viral hook variation."""
    from services.repurpose_engine import generate_hook
    register_child_task(job_id, generate_single_hook.request.id)
    try:
        hook = generate_hook(clip_transcript, style=style)
        return {"style": style, "hook": hook, "variation_idx": variation_idx}
    except Exception as e:
        logger.error(f"Failed to generate hook variation {variation_idx} ({style}): {e}")
        return {"style": style, "hook": None, "variation_idx": variation_idx, "error": str(e)}

@celery_app.task(name="hooks.collect")
def collect_hook_variations(results: list[dict], job_id: str) -> None:
    """Gap 372: Reduce all parallel hook results into DB."""
    from db.repositories.clips import save_hook_variations
    valid_results = [r for r in results if r.get("hook")]
    save_hook_variations(job_id, valid_results)
    logger.info(f"[{job_id}] Collected {len(valid_results)} hook variations")

def dispatch_hook_variations(clip_transcript: str, job_id: str) -> None:
    """
    Fan out hook generation to multiple parallel tasks.
    """
    HOOK_STYLES = ["question", "bold_statement", "story", "contrarian", "stat_lead"]

    # Fan out — all 5 run in parallel
    tasks = group(
        generate_single_hook.si(clip_transcript, style, job_id, i)
        for i, style in enumerate(HOOK_STYLES)
    )
    
    # Collect when all done
    # Note: We use the safe_chord monitor pattern if needed, but for now simple chord
    from workers.pipeline import monitor_chord
    job = chord(tasks)(collect_hook_variations.s(job_id))
    
    # Launch watchdog for the chord
    monitor_chord.apply_async(
        args=[job.id, job_id],
        countdown=60,
        queue="maintenance",
    )
    return job
