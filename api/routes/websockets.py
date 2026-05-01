"""File: api/routes/websockets.py
Purpose: WebSocket endpoint for real-time pipeline progress.
         Uses Redis Pub/Sub for immediate event delivery without polling.
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.ws_manager import clear_events, get_history, subscribe_events

logger = logging.getLogger(__name__)
router = APIRouter(tags=["websockets"])

# Maximum idle time before the server closes a stale connection
_WS_IDLE_TIMEOUT_SECONDS = 300.0  # 5 minutes


@router.websocket("/ws/jobs/{job_id}")
async def job_status_ws(websocket: WebSocket, job_id: str) -> None:
    """Stream real-time pipeline events for a specific job using Pub/Sub."""
    await websocket.accept()
    logger.info("[ws] Client connected for job=%s", job_id)

    try:
        # 1. Catch-up: Send buffered history first
        history = await get_history(job_id)
        if history:
            for event in history:
                await websocket.send_json(event)

        # 2. Live: Subscribe to Redis Pub/Sub channel
        # We run two tasks: one to listen to Redis, one to listen to client (pings)
        
        async def event_listener():
            try:
                async for event in subscribe_events(job_id):
                    await websocket.send_json(event)
                    if event["type"] in ("completed", "error"):
                        # Small delay to ensure client receives the final event before close
                        await asyncio.sleep(0.5)
                        return
            except Exception as e:
                logger.error("[ws] Event listener error for job=%s: %s", job_id, e)

        async def client_listener():
            try:
                while True:
                    # We only care about pings to keep the connection alive
                    msg = await websocket.receive_json()
                    if isinstance(msg, dict) and msg.get("type") == "ping":
                        await websocket.send_json({"type": "pong", "timestamp": time.time()})
            except WebSocketDisconnect:
                raise
            except Exception:
                pass

        # Wait for either the job to finish or the client to disconnect
        done, pending = await asyncio.wait(
            [
                asyncio.create_task(event_listener()),
                asyncio.create_task(client_listener()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=_WS_IDLE_TIMEOUT_SECONDS
        )

        for task in pending:
            task.cancel()

    except WebSocketDisconnect:
        logger.info("[ws] Client disconnected for job=%s", job_id)
    except Exception as exc:
        logger.warning("[ws] WebSocket error for job=%s: %s", job_id, exc)
    finally:
        try:
            # We don't clear events here because other watchers might still be connected
            await websocket.close()
        except Exception:
            pass
