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

# Gap 61: Maximum idle time before the server closes a stale connection
_WS_IDLE_TIMEOUT_SECONDS = 300.0  # 5 minutes


@router.websocket("/ws/jobs/{job_id}")
async def job_status_ws(websocket: WebSocket, job_id: str) -> None:
    """Stream real-time pipeline events for a specific job.
    
    Gap 61: Idle connections are closed after _WS_IDLE_TIMEOUT_SECONDS of inactivity.
    """
    await websocket.accept()
    logger.info("[ws] Client connected for job=%s", job_id)

    cursor = 0.0        # timestamp cursor — only send events after this
    poll_interval = 0.5 # seconds between polls
    last_activity = time.monotonic()  # Gap 61: track idle time

    try:
        # Send any buffered history first (catch-up for late joiners)
        history = drain_events(job_id, after=0.0)
        if history:
            for event in history:
                await websocket.send_json(event)
            cursor = history[-1]["timestamp"]
            last_activity = time.monotonic()

        # Main event loop
        while True:
            # Gap 61: Close stale connections that have been idle too long
            if time.monotonic() - last_activity > _WS_IDLE_TIMEOUT_SECONDS:
                logger.info("[ws] Closing idle connection for job=%s (no activity for %.0fs)", job_id, _WS_IDLE_TIMEOUT_SECONDS)
                await websocket.close(code=1000, reason="Idle timeout")
                return

            # Check for new events
            new_events = drain_events(job_id, after=cursor)
            for event in new_events:
                await websocket.send_json(event)
                cursor = event["timestamp"]
                last_activity = time.monotonic()  # Gap 61: reset idle clock on activity

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
                        last_activity = time.monotonic()  # Gap 61: ping counts as activity
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
