"""
File: services/export_engine.py
Purpose: Omnichannel content transformation. Generates LinkedIn posts, 
         Newsletter drafts, and PDF artifacts from viral video clips.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Literal
from sqlalchemy import text

from core.config import settings
from db.repositories.jobs import get_job
from services.llm_integration import llm_client, is_llm_available

logger = logging.getLogger(__name__)

ToneType = Literal["professional", "controversial", "growth", "casual"]

class ExportEngine:
    """Consolidated engine for repurposing viral clips into text/document formats."""

    def __init__(self):
        self.model = settings.clip_detector_model
        self.client = llm_client

    def generate_premiere_xml(self, job_id: str) -> str:
        """
        Generates a Final Cut Pro XML (XMEML) for integration with Premiere Pro/DaVinci.
        Allows editors to import all viral clips as a single sequence.
        """
        job = get_job(job_id)
        if not job or not job.clips_json:
            return ""

        fps = 24  # Default for social video
        clips = job.clips_json
        source_name = Path(job.source_video_url).name
        source_url = job.source_video_url

        xml_header = f"""<?xml version="1.0" encoding="UTF-8"?>
<xmeml version="5">
<sequence id="sequence-1">
    <name>ClipMind Viral Cuts - {job_id[:8]}</name>
    <duration>{int(sum(c.duration for c in clips) * fps)}</duration>
    <rate><timebase>{fps}</timebase></rate>
    <media>
        <video>
            <track>"""

        xml_footer = """
            </track>
        </video>
    </media>
</sequence>
</xmeml>"""

        clip_items = []
        current_timeline_start = 0
        
        for i, clip in enumerate(clips):
            in_frame = int(clip.start_time * fps)
            out_frame = int(clip.end_time * fps)
            duration_frames = out_frame - in_frame
            end_timeline_frame = current_timeline_start + duration_frames

            # First clip defines the file resource, others reference it
            file_meta = ""
            if i == 0:
                file_meta = f"""
                            <file id="file-1">
                                <name>{source_name}</name>
                                <pathurl>{source_url}</pathurl>
                                <rate><timebase>{fps}</timebase></rate>
                            </file>"""
            else:
                file_meta = '<file id="file-1"/>'

            item = f"""
                <clipitem id="clipitem-{i+1}">
                    <name>{source_name} [Clip {i+1}]</name>
                    <duration>{duration_frames}</duration>
                    <rate><timebase>{fps}</timebase></rate>
                    <start>{current_timeline_start}</start>
                    <end>{end_timeline_frame}</end>
                    <in>{in_frame}</in>
                    <out>{out_frame}</out>
                    {file_meta}
                    <labels>
                        <label2>Virality Score: {clip.final_score}</label2>
                    </labels>
                </clipitem>"""
            
            clip_items.append(item)
            current_timeline_start = end_timeline_frame

        return xml_header + "".join(clip_items) + xml_footer

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

        prompt = f"""
        You are a Viral Marketing Strategist. 
        Analyze the following clip transcript and reasoning.
        Generate a 'Social Pulse' package to maximize retention and scroll-stopping.
        
        Transcript: "{clip_data.get('reason', '')}"
        
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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        result = json.loads(response.choices[0].message.content)
        return result

    def _get_clip_data(self, clip_id: str) -> dict:
        """Fetch clip details from the clips_json of its parent job."""
        from db.queries import engine
        # Since clips are stored in JSON arrays in the jobs table, 
        # we need to find the job that contains this clip_id (in this case, clip_index)
        # Actually, in this project, clips often refer to indices. 
        # For this engine, we assume the API passes the parent job_id and clip_index.
        pass

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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "You are a LinkedIn Growth Expert."},
                      {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()

    async def generate_newsletter_draft(self, job_id: str) -> str:
        """Aggregates all viral clips from a job into a Substack-ready newsletter blurb."""
        job = get_job(job_id)
        if not job or not job.get("clips_json"):
            return "No clips found for this job."

        clips = job["clips_json"]
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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "You are a professional newsletter writer."},
                      {"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content.strip()

    def generate_linkedin_carousel_pdf(self, clip_id: str):
        """
        Placeholder for PDF generation logic (Phase 4 integration).
        For V1, we return a structural metadata map for the frontend to render.
        """
        # Logic here would involve generating images via HTML-to-Canvas or similar,
        # then merging into a PDF. For this MVP, we focus on text transformation.
        return {"status": "specced", "message": "PDF Carousel generation coming in Phase 4 - Enterprise."}

def get_export_engine() -> ExportEngine:
    return ExportEngine()
