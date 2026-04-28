"""Middleware that assigns request/job correlation IDs."""

from __future__ import annotations

import re
import uuid
from typing import Callable, Awaitable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings
from core.request_context import reset_request_context, set_request_context


_JOB_PATH_RE = re.compile(r"/jobs/(?P<job_id>[^/]+)")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        request_id = request.headers.get(settings.request_context_header) or str(uuid.uuid4())
        trace_id = request.headers.get(settings.trace_context_header) or request_id
        job_id = None
        match = _JOB_PATH_RE.search(request.url.path)
        if match:
            job_id = match.group("job_id")

        tokens = set_request_context(
            request_id=request_id,
            trace_id=trace_id,
            job_id=job_id,
            user_id=request.headers.get("x-user-id"),
            source="api",
        )
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        request.state.job_id = job_id

        try:
            response = await call_next(request)
            response.headers[settings.request_context_header] = request_id
            response.headers[settings.trace_context_header] = trace_id
            return response
        finally:
            reset_request_context(tokens)
