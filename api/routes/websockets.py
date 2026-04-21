"""File: api/routes/websockets.py
Purpose: WebSocket endpoint for real-time pipeline progress.
         Clients connect to /ws/jobs/{job_id} and receive JSON events
         as the pipeline processes their video in real-time.

Protocol:
    1. Client opens ws://host/api/v1/ws/jobs/{job_id}
    2. Server immediately sends buffered history (catch-up)
    3. Server polls for new events every 500ms and pushes them
    4. Client can send {"type": "ping"} to keep alive
    5. Connection closes when job completes or client disconnects
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.ws_manager import drain_events

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websockets"])


@router.websocket("/ws/jobs/{job_id}")
async def job_status_ws(websocket: WebSocket, job_id: str) -> None:
    """Stream real-time pipeline events for a specific job."""
    await websocket.accept()
    logger.info("[ws] Client connected for job=%s", job_id)

    cursor = 0.0  # timestamp cursor — only send events after this
    poll_interval = 0.5  # seconds between polls

    try:
        # Send any buffered history first (catch-up for late joiners)
        history = drain_events(job_id, after=0.0)
        if history:
            for event in history:
                await websocket.send_json(event)
            cursor = history[-1]["timestamp"]

        # Main event loop
        while True:
            # Check for new events
            new_events = drain_events(job_id, after=cursor)
            for event in new_events:
                await websocket.send_json(event)
                cursor = event["timestamp"]

                # If job completed or errored fatally, close after sending
                if event["type"] in ("completed", "error"):
                    await asyncio.sleep(0.5)  # give client time to process
                    await websocket.close()
                    logger.info("[ws] Client disconnected (job %s %s)", job_id, event["type"])
                    return

            # Listen for client pings (non-blocking, short timeout)
            try:
                msg = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=poll_interval,
                )
                # Handle client messages
                if isinstance(msg, dict):
                    if msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong", "timestamp": time.time()})
            except asyncio.TimeoutError:
                # No client message — that's normal, continue polling
                pass

    except WebSocketDisconnect:
        logger.info("[ws] Client disconnected for job=%s", job_id)
    except Exception as exc:
        logger.warning("[ws] WebSocket error for job=%s: %s", job_id, exc)
        try:
            await websocket.close()
        except Exception:
            pass
