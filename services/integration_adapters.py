"""File: services/integration_adapters.py
Purpose: Adapters for external integrations (Zapier, Make.com, etc)
         Format ClipMind webhooks for different platforms
"""

from __future__ import annotations

import json
from typing import Any


class IntegrationAdapter:
    """Base class for integration adapters."""
    
    def format_event(self, event_type: str, event_data: dict) -> dict:
        """Format a ClipMind event for this integration platform.
        
        Args:
            event_type: Event type (job.completed, clips.generated, etc)
            event_data: ClipMind event payload
        
        Returns:
            Formatted payload for the integration platform
        """
        raise NotImplementedError


class ZapierAdapter(IntegrationAdapter):
    """Adapter for Zapier integration.
    
    Zapier webhooks expect a simpler structure with top-level fields
    mapped to Zap variables.
    """
    
    def format_event(self, event_type: str, event_data: dict) -> dict:
        """Format event for Zapier."""
        
        if event_type == "job.completed":
            return {
                "event": "job.completed",
                "status": event_data.get("status"),
                "job_id": event_data.get("job_id"),
                "clips_count": event_data.get("clips_count"),
                "cost_usd": event_data.get("estimated_cost_usd"),
                "timestamp": event_data.get("timestamp"),
            }
        
        elif event_type == "clips.generated":
            return {
                "event": "clips.generated",
                "job_id": event_data.get("job_id"),
                "clips_count": event_data.get("clips_count"),
                "timestamp": event_data.get("timestamp"),
                "clips": event_data.get("clips", [])[:1],  # Send top clip only for simplicity
            }
        
        elif event_type == "clip.regenerated":
            return {
                "event": "clip.regenerated",
                "job_id": event_data.get("job_id"),
                "clip_index": event_data.get("clip_index"),
                "regen_id": event_data.get("regen_id"),
                "timestamp": event_data.get("timestamp"),
            }
        
        elif event_type == "campaign.created":
            return {
                "event": "campaign.created",
                "campaign_id": event_data.get("campaign_id"),
                "campaign_name": event_data.get("campaign_name"),
                "timestamp": event_data.get("timestamp"),
            }
        
        elif event_type == "campaign.updated":
            return {
                "event": "campaign.updated",
                "campaign_id": event_data.get("campaign_id"),
                "changes": json.dumps(event_data.get("changes", {})),
                "timestamp": event_data.get("timestamp"),
            }
        
        # Default: return as-is
        return event_data


class MakeAdapter(IntegrationAdapter):
    """Adapter for Make.com integration.
    
    Make.com webhooks expect data in a specific structure with
    metadata and payload fields.
    """
    
    def format_event(self, event_type: str, event_data: dict) -> dict:
        """Format event for Make.com."""
        
        if event_type == "job.completed":
            return {
                "event": "job.completed",
                "metadata": {
                    "event_type": event_type,
                    "triggered_at": event_data.get("timestamp"),
                },
                "payload": {
                    "status": event_data.get("status"),
                    "job_id": event_data.get("job_id"),
                    "clips_count": event_data.get("clips_count"),
                    "cost_usd": event_data.get("estimated_cost_usd"),
                }
            }
        
        elif event_type == "clips.generated":
            return {
                "event": "clips.generated",
                "metadata": {
                    "event_type": event_type,
                    "triggered_at": event_data.get("timestamp"),
                },
                "payload": {
                    "job_id": event_data.get("job_id"),
                    "clips_count": event_data.get("clips_count"),
                    "clips": event_data.get("clips", [])[:1],  # Top clip
                }
            }
        
        elif event_type == "clip.regenerated":
            return {
                "event": "clip.regenerated",
                "metadata": {
                    "event_type": event_type,
                    "triggered_at": event_data.get("timestamp"),
                },
                "payload": {
                    "job_id": event_data.get("job_id"),
                    "clip_index": event_data.get("clip_index"),
                    "regen_id": event_data.get("regen_id"),
                }
            }
        
        elif event_type == "campaign.created":
            return {
                "event": "campaign.created",
                "metadata": {
                    "event_type": event_type,
                    "triggered_at": event_data.get("timestamp"),
                },
                "payload": {
                    "campaign_id": event_data.get("campaign_id"),
                    "campaign_name": event_data.get("campaign_name"),
                }
            }
        
        elif event_type == "campaign.updated":
            return {
                "event": "campaign.updated",
                "metadata": {
                    "event_type": event_type,
                    "triggered_at": event_data.get("timestamp"),
                },
                "payload": {
                    "campaign_id": event_data.get("campaign_id"),
                    "changes": event_data.get("changes", {}),
                }
            }
        
        # Default: wrap in standard structure
        return {
            "event": event_type,
            "metadata": {"triggered_at": event_data.get("timestamp")},
            "payload": event_data,
        }


class SlackAdapter(IntegrationAdapter):
    """Adapter for Slack integration (future).
    
    Formats ClipMind events as Slack message blocks.
    """
    
    def format_event(self, event_type: str, event_data: dict) -> dict:
        """Format event for Slack."""
        
        if event_type == "job.completed":
            status = event_data.get("status")
            color = "good" if status == "completed" else "danger"
            
            return {
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": "ClipMind Job Completed",
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Status:*\n{status}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Clips Count:*\n{event_data.get('clips_count')}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Job ID:*\n{event_data.get('job_id')}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Cost:*\n${event_data.get('estimated_cost_usd')}"
                            }
                        ]
                    }
                ]
            }
        
        # Default: simple text message
        return {
            "text": f"ClipMind: {event_type} event fired",
            "blocks": [{
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*ClipMind {event_type}*\n{json.dumps(event_data, indent=2)}"
                }
            }]
        }


def get_adapter(integration_type: str) -> IntegrationAdapter:
    """Get the appropriate adapter for an integration type."""
    adapters = {
        "zapier": ZapierAdapter,
        "make": MakeAdapter,
        "slack": SlackAdapter,
    }
    
    adapter_class = adapters.get(integration_type.lower())
    if not adapter_class:
        raise ValueError(f"Unknown integration type: {integration_type}")
    
    return adapter_class()
