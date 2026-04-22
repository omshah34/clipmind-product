import sys

with open(r'c:\Users\sshit\Documents\2) projects\clipmind product\api\routes\clip_studio.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_code = """
    # 3. Background fast re-render for dev phase
    def _dev_re_render():
        try:
            from services.caption_renderer import write_clip_srt
            from core.config import settings
            import tempfile
            from pathlib import Path
            
            latest_job = get_job(job_id)
            source_name = Path(latest_job.source_video_url).name
            local_source = Path(settings.local_storage_dir) / "sources" / source_name
            
            if local_source.exists() and getattr(latest_job, "transcript_json", None):
                export_dir = Path(settings.local_storage_dir) / "exports" / f"adj_{job_id}_{clip_index}"
                export_dir.mkdir(parents=True, exist_ok=True)
                srt_path = export_dir / "temp.srt"
                
                write_clip_srt(latest_job.transcript_json, payload.new_start, payload.new_end, srt_path)
                
                with open(srt_path, "r", encoding="utf-8") as f:
                    srt_data = f.read()
                    
                from workers.render_clips import render_edited_clip
                try:
                    # Sync call for dev locally
                    render_edited_clip(
                        render_job_id=str(job_id), 
                        job_id=str(job_id), 
                        clip_index=clip_index, 
                        edited_srt=srt_data
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Dev auto-render failed: {e}")

    background_tasks.add_task(_dev_re_render)
"""

for i, line in enumerate(lines):
    if "new_clip_url = f\"/api/v1/jobs/{job_id}/clips/{clip_index}/stream\"" in line:
        lines.insert(i, new_code + "\n")
        break

with open(r'c:\Users\sshit\Documents\2) projects\clipmind product\api\routes\clip_studio.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
