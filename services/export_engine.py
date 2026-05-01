"""
File: services/export_engine.py
Purpose: Omnichannel content transformation. Generates LinkedIn posts, 
         Newsletter drafts, and PDF artifacts from viral video clips.
"""

import json
import logging
import shutil
from html import escape
from pathlib import Path
from typing import Optional, List, Literal
from urllib.parse import urlparse
from sqlalchemy import text

from core.config import settings
from db.repositories.jobs import get_job
from services.openai_client import create_chat_completion, is_llm_available

logger = logging.getLogger(__name__)

ToneType = Literal["professional", "controversial", "growth", "casual"]

class ExportEngine:
    """Consolidated engine for repurposing viral clips into text/document formats."""

    def __init__(self):
        self.model = settings.clip_detector_model

    def generate_sync_bridge_xml(self, job_id: str, format: Literal["premiere", "davinci"] = "premiere") -> str:
        """
        Generates a professional-grade XML for NLE integration.
        - Premiere: Final Cut Pro XML (XMEML v5)
        - DaVinci Resolve: FCPXML (v1.10)
        """
        job = get_job(job_id)
        if not job or not job.clips_json:
            return ""

        fps = 24
        clips = job.clips_json
        source_name = Path(urlparse(job.source_video_url).path).name
        
        # PRO-REQUIREMENT: Absolute paths for local NLE import
        # If it's a URL, we try to use the local cached version if available
        local_source = Path(settings.local_storage_dir) / "sources" / source_name
        media_path = local_source.resolve().as_uri() if local_source.exists() else job.source_video_url

        if format == "davinci":
            return self._generate_davinci_fcpxml(job_id, clips, source_name, media_path, fps)
        else:
            return self._generate_premiere_xmeml(job_id, clips, source_name, media_path, fps)

    def _generate_premiere_xmeml(self, job_id: str, clips: list, source_name: str, media_path: str, fps: int) -> str:
        xml_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="5">
<sequence id="sequence-1">
    <name>ClipMind Viral Cuts - {escape(job_id[:8])}</name>
    <duration>{int(sum(c.get('duration', 0) for c in clips) * fps)}</duration>
    <rate><timebase>{fps}</timebase></rate>
    <media>
        <video>
            <track>"""

        clip_items = []
        current_timeline_start = 0
        for i, clip in enumerate(clips):
            in_frame = int(float(clip.get("start_time", 0)) * fps)
            out_frame = int(float(clip.get("end_time", 0)) * fps)
            duration_frames = out_frame - in_frame
            end_timeline_frame = current_timeline_start + duration_frames
            
            score = clip.get("final_score", 0)
            
            file_meta = f"""
                            <file id="file-1">
                                <name>{escape(source_name)}</name>
                                <pathurl>{escape(media_path)}</pathurl>
                                <rate><timebase>{fps}</timebase></rate>
                            </file>""" if i == 0 else '<file id="file-1"/>'

            item = f"""
                <clipitem id="clipitem-{i+1}">
                    <name>{escape(source_name)} [Clip {i+1}]</name>
                    <duration>{duration_frames}</duration>
                    <rate><timebase>{fps}</timebase></rate>
                    <start>{current_timeline_start}</start>
                    <end>{end_timeline_frame}</end>
                    <in>{in_frame}</in>
                    <out>{out_frame}</out>
                    {file_meta}
                    <labels>
                        <label2>Virality Score: {score}</label2>
                    </labels>
                </clipitem>"""
            clip_items.append(item)
            current_timeline_start = end_timeline_frame

        markers = []
        timeline_cursor = 0
        for clip in clips:
            duration = int((float(clip.get("end_time", 0)) - float(clip.get("start_time", 0))) * fps)
            marker = f"""
        <marker>
            <name>Hook: {escape(str(clip.get('hook_headlines', [''])[0]))}</name>
            <comment>Virality: {clip.get('final_score', 0)}/10 | {escape(str(clip.get('reason', '')))}</comment>
            <in>{timeline_cursor}</in>
            <out>{timeline_cursor + 1}</out>
        </marker>"""
            markers.append(marker)
            timeline_cursor += duration

        xml_footer = f"""
            </track>
        </video>
    </media>
    {"".join(markers)}
</sequence>
</xmeml>"""
        return xml_header + "".join(clip_items) + xml_footer

    def _generate_davinci_fcpxml(self, job_id: str, clips: list, source_name: str, media_path: str, fps: int) -> str:
        """
        DaVinci Resolve Optimized FCPXML 1.10.
        Uses <fcpxml> root as required for modern Blackmagic Design imports.
        """
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<fcpxml version="1.10">
    <resources>
        <format id="r1" name="FFVideoFormat1080p24" frameDuration="1/{fps}s" width="1920" height="1080"/>
        <asset id="a1" name="{escape(source_name)}" src="{escape(media_path)}" start="0s" duration="3600s" hasVideo="1" format="r1"/>
    </resources>
    <library>
        <event name="ClipMind Exports">
            <project name="Viral Sequence - {escape(job_id[:8])}">
                <sequence format="r1" tcStart="0s">
                    <spine>"""
        
        cursor = 0
        for clip in clips:
            start = float(clip.get("start_time", 0))
            end = float(clip.get("end_time", 0))
            dur = end - start
            
            xml += f"""
                        <asset-clip ref="a1" offset="{cursor}s" start="{start}s" duration="{dur}s">
                            <note>Virality Score: {escape(str(clip.get('final_score', 0)))}</note>
                        </asset-clip>"""
            cursor += dur
            
        xml += """
                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>"""
        return xml

    def generate_capcut_bridge_zip(self, job_id: str, clip_index: int) -> Path:
        """
        Feature 1: The 'CapCut Bridge'.
        Creates a ZIP containing the raw trimmed video (no burned-in subtitles)
        and a perfectly timed .srt file for off-platform editing.
        """
        import zipfile
        from services.video_processor import cut_clip
        from services.caption_renderer import write_clip_srt

        job = get_job(job_id)
        if not job or not job.clips_json or clip_index >= len(job.clips_json):
            raise ValueError("Job or clip not found")

        # Handle both Pydantic models and dicts
        clip = job.clips_json[clip_index]
        if hasattr(clip, "model_dump"):
            clip = clip.model_dump()
        elif hasattr(clip, "dict"):
            clip = clip.dict()

        source_name = Path(urlparse(job.source_video_url).path).name
        local_source = Path(settings.local_storage_dir) / "sources" / source_name

        if not local_source.exists():
            raise FileNotFoundError(f"Source video not found locally: {local_source}")

        start_time = float(clip.get("start_time", 0))
        end_time = float(clip.get("end_time", 0))

        export_dir = Path(settings.local_storage_dir) / "exports" / f"capcut_bridge_{job_id}_{clip_index}"
        export_dir.mkdir(parents=True, exist_ok=True)

        raw_clip_path = export_dir / f"clip_{clip_index}_raw.mp4"
        srt_path = export_dir / f"clip_{clip_index}.srt"
        zip_path = export_dir.parent / f"clipmind_capcut_{job_id}_{clip_index}.zip"

        try:
            # 1. Cut the raw clip
            cut_clip(local_source, start_time, end_time, raw_clip_path, validate_duration=False)

            # 2. Generate SRT
            if job.transcript_json:
                write_clip_srt(job.transcript_json, start_time, end_time, srt_path)

            # 3. Zip them together
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                zipf.write(raw_clip_path, raw_clip_path.name)
                if srt_path.exists():
                    zipf.write(srt_path, srt_path.name)
        finally:
            shutil.rmtree(export_dir, ignore_errors=True)

        return zip_path

    async def generate_social_pulse(self, clip_data: dict) -> dict:
        """
        AI-driven viral caption and hashtag suggestions based on 'Social Pulse'.
        Used as the source for Headlines and social copy.
        """
        if not is_llm_available():
            return {
                "headlines": ["Watch this amazing clip!"],
                "caption": "Check out this viral moment! #viral #video",
                "hashtags": ["#viral", "#video"]
            }

        transcript_text = (
            clip_data.get("transcript_text")
            or clip_data.get("caption_text")
            or clip_data.get("current_srt")
            or clip_data.get("transcript")
            or clip_data.get("reason", "")
        )

        prompt = f"""
        You are a Viral Marketing Strategist. 
        Analyze the following clip transcript and contextual metadata.
        Generate a 'Social Pulse' package to maximize retention and scroll-stopping.
        
        Transcript: "{transcript_text}"
        
        Requirements:
        1. 3 Scroll-Stopping Headlines (Short, bold, 3-7 words).
        2. 1 Viral Hook Caption.
        3. 5 Niche-specific Hashtags.

        Return ONLY a JSON object:
        {{
          "headlines": ["...", "...", "..."],
          "caption": "...",
          "hashtags": ["#...", "#..."]
        }}
        """

        completion = create_chat_completion(
            preferred_model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        result = json.loads(completion.response.choices[0].message.content)
        return result

    def _get_clip_data(self, clip_id: str) -> dict:
        """Fetch clip details from the clips_json of its parent job."""
        clip_ref = str(clip_id).strip()
        if not clip_ref:
            raise ValueError("clip_id is required")

        if ":" in clip_ref:
            job_id, clip_index_text = clip_ref.split(":", 1)
            clip_index = int(clip_index_text)
            job = get_job(job_id)
            if not job or not job.clips_json or clip_index >= len(job.clips_json):
                raise ValueError("Clip not found")
            clip = job.clips_json[clip_index]
            return clip.model_dump() if hasattr(clip, "model_dump") else dict(clip)

        if "|" in clip_ref:
            job_id, clip_index_text = clip_ref.split("|", 1)
            clip_index = int(clip_index_text)
            job = get_job(job_id)
            if not job or not job.clips_json or clip_index >= len(job.clips_json):
                raise ValueError("Clip not found")
            clip = job.clips_json[clip_index]
            return clip.model_dump() if hasattr(clip, "model_dump") else dict(clip)

        raise ValueError(
            "clip_id must be encoded as 'job_id:clip_index' or 'job_id|clip_index' for internal lookup"
        )

    async def generate_linkedin_post(
        self, 
        transcript_segment: str, 
        ai_reasoning: str, 
        tone: ToneType = "professional"
    ) -> str:
        """Transform a video transcript into a high-engagement LinkedIn post."""
        if not is_llm_available():
            return f"[Draft] This video discusses: {transcript_segment[:100]}... [VIDEO LINK]"

        prompts = {
            "professional": "Focus on industry insights, leadership, and professional value.",
            "controversial": "Start with a bold, pattern-interrupting statement that challenges the status quo.",
            "growth": "Structure as a 'how-to' or 'lesson learned' with clear takeaways.",
            "casual": "Friendly, relatable, and easy to read. High emoji usage."
        }

        prompt = f"""
        You are a top 1% LinkedIn Content Ghostwriter. 
        Transform the following video clip transcript into a VIRAL LinkedIn post.
        
        Tone Requirement: {prompts.get(tone)}
        
        Transcript Segment:
        "{transcript_segment}"
        
        AI Reasoning for why this is viral:
        "{ai_reasoning}"
        
        Guidelines:
        1. Use a "Hook" in the first line.
        2. Use whitespace for readability.
        3. Include 3-5 high-value bullet points.
        4. End with a thought-provoking question to drive comments.
        5. Add 3-5 relevant hashtags.
        6. Do NOT include links; use the placeholder [VIDEO LINK] at the end.
        
        Return ONLY the post content.
        """

        completion = create_chat_completion(
            preferred_model=self.model,
            messages=[{"role": "system", "content": "You are a LinkedIn Growth Expert."},
                      {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return completion.response.choices[0].message.content.strip()

    async def generate_newsletter_draft(self, job_id: str) -> str:
        """Aggregates all viral clips from a job into a Substack-ready newsletter blurb."""
        job = get_job(job_id)
        if not job or not job.clips_json:
            return "No clips found for this job."

        clips = job.clips_json
        # Limit to top 3-5 clips
        top_clips = sorted(clips, key=lambda x: x.get("final_score", 0), reverse=True)[:5]
        
        summaries = []
        for c in top_clips:
            summaries.append(f"- **{c.get('reason', 'Viral Moment')}**: {c.get('hook_headlines', ['Watch here'])[0]} [VIDEO LINK]")

        if not is_llm_available():
            return "# Weekly Insights\n\n" + "\n".join(summaries)

        prompt = f"""
        You are a newsletter curator for a tech-savvy audience.
        Summarize these viral video clips into a high-value 'Weekly Digest' newsletter draft.
        
        Clips To Feature:
        {json.dumps(top_clips, indent=2)}
        
        Format: Markdown (Substack/Medium optimized).
        Requirements:
        1. Catchy subject line.
        2. Brief intro (2 sentences).
        3. For each clip, provide a 1-sentence 'Why you should care' and a [VIDEO LINK].
        4. Brief outro.
        
        Return ONLY the Markdown content.
        """

        completion = create_chat_completion(
            preferred_model=self.model,
            messages=[{"role": "system", "content": "You are a professional newsletter writer."},
                      {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return completion.response.choices[0].message.content.strip()

        # then merging into a PDF. For this MVP, we focus on text transformation.
        return {"status": "specced", "message": "PDF Carousel generation coming in Phase 4 - Enterprise."}

    async def generate_story_sequence(self, job_id: str, theme: str) -> Path:
        """
        Creates a 'Sequence-Master' narrative.
        Identify clips in a job related to a theme, sort them logistically, and stitch them.
        Gap Exploited: Abrupt one-off clips that lack continuous story context.
        """
        from services.discovery import get_discovery_service
        from services.video_processor import apply_broll_cutaways # We might use this too
        import subprocess
        
        job = get_job(job_id)
        if not job or not job.clips_json:
            raise ValueError("Job not found or has no clips")

        discovery = get_discovery_service()
        clips = job.clips_json
        
        # 1. Semantic Filter: Find clips from THIS job related to the theme
        # For MVP, we'll do a simple text match or use discovery's logic locally
        related_clips = []
        for clip in clips:
            text = " ".join([clip.get("reason", "")] + clip.get("hook_headlines", []))
            # We treat the 'reason' as the primary semantic text for now
            related_clips.append(clip) # For Phase 3 MVP, we use all clips or top N
            
        # 2. Sort by 'Story Continuity' (LLM-based or chronological)
        # Chronological is safer for narrative integrity unless specified otherwise
        related_clips.sort(key=lambda x: x.get("start_time", 0))
        
        # 3. Stitch with FFmpeg concat
        output_dir = Path(settings.local_storage_dir) / "sequences"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"sequence_{job_id[:8]}_{theme}.mp4"
        
        # Concat logic
        # We assume clips are already rendered vertical clips. 
        # In a real pipeline, we'd pull the rendered paths.
        # For this spec, we generate a concat file.
        concat_file = output_dir / f"list_{job_id[:8]}.txt"
        with open(concat_file, "w") as f:
            for clip in related_clips[:3]: # Limit to 3 clips for 'mini-story'
                # Mock path for rendered clip
                clip_path = Path(settings.local_storage_dir) / "clips" / f"clip_{job_id}_{clip.get('clip_index')}.mp4"
                if clip_path.exists():
                    f.write(f"file '{clip_path.resolve().as_posix()}'\n")
        
        if not concat_file.stat().st_size:
            raise ValueError("No rendered clips found to sequence. Render them first.")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path)
        ]
        
        logger.info("Stitching sequence for job %s with theme: %s", job_id, theme)
        subprocess.run(cmd, check=True, capture_output=True)
        
        return output_path

def get_export_engine() -> ExportEngine:
    return ExportEngine()
