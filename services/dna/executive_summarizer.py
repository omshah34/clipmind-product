"""File: services/dna/executive_summarizer.py
Purpose: Synthesize DNA learning logs into high-level strategic summaries using LLM.
"""
import logging
from typing import List, Optional
from db.repositories.content_dna import get_dna_logs_for_summary, save_executive_summary
from services.openai_client import create_chat_completion, is_llm_available

logger = logging.getLogger(__name__)

class ExecutiveSummarizer:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    async def generate_summary(self, user_id: str) -> Optional[dict]:
        """Fetch logs from the last 30 days and generate a synthetic strategy summary."""
        if not is_llm_available():
            logger.info("Groq is not configured. Skipping executive summary generation.")
            return None

        # 1. Fetch Windowed Logs
        logs = get_dna_logs_for_summary(user_id, days=30, limit=20)
        if not logs:
            logger.info(f"No DNA logs found for user {user_id} in the last 30 days. Skipping summary.")
            return None

        # 2. Format Logs for LLM
        log_descriptions = []
        log_ids = []
        for l in logs:
            log_ids.append(l["id"])
            desc = f"- {l['created_at'].date()}: {l['log_type']} on '{l['dimension']}' "
            if l['old_value'] and l['new_value']:
                desc += f"({l['old_value']:.2f} -> {l['new_value']:.2f}) "
            desc += f"Reason: {l['reasoning_code']}"
            log_descriptions.append(desc)

        log_context = "\n".join(log_descriptions)

        # 3. LLM Prompt Construction
        prompt = f"""
You are the ClipMind Executive Strategist. You analyze a creator's audience "DNA" shifts to provide high-level strategy.
Below are the significant shifts in weight and milestones detected in the last 30 days:

{log_context}

Task: Write a concise (3-4 sentence) Executive Strategy Summary. 
Focus on:
1. The overall "Pivot": Is the audience moving toward emotional resonance, hook-driven content, or clarity?
2. Actionable advice: What should the creator double down on?
3. Maintain a professional, encouraging, and data-driven tone.

Start with "Strategic Analysis: "
"""

        # 4. LLM Call
        try:
            completion = create_chat_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=256,
            )
            summary_text = completion.response.choices[0].message.content

            # 5. Persist Summary
            return save_executive_summary(user_id, summary_text, log_ids)

        except Exception as e:
            logger.exception(f"Error during Executive Summary generation: {e}")
            return None

def get_executive_summarizer():
    return ExecutiveSummarizer()
