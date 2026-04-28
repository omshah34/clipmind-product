"""Request/job context propagation for logging and event persistence."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
job_id_var: ContextVar[str | None] = ContextVar("job_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
source_var: ContextVar[str | None] = ContextVar("source", default=None)


@dataclass(frozen=True)
class RequestContext:
    request_id: str | None = None
    trace_id: str | None = None
    job_id: str | None = None
    user_id: str | None = None
    source: str | None = None


def set_request_context(
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    job_id: str | None = None,
    user_id: str | None = None,
    source: str | None = None,
) -> tuple[object | None, object | None, object | None, object | None, object | None]:
    """Set the current request/job context and return tokens for reset."""
    tokens = (
        request_id_var.set(request_id),
        trace_id_var.set(trace_id or request_id),
        job_id_var.set(job_id),
        user_id_var.set(user_id),
        source_var.set(source),
    )
    return tokens


def reset_request_context(tokens: tuple[object | None, object | None, object | None, object | None, object | None]) -> None:
    """Reset the current request/job context using tokens from set_request_context."""
    request_id_var.reset(tokens[0])  # type: ignore[arg-type]
    trace_id_var.reset(tokens[1])  # type: ignore[arg-type]
    job_id_var.reset(tokens[2])  # type: ignore[arg-type]
    user_id_var.reset(tokens[3])  # type: ignore[arg-type]
    source_var.reset(tokens[4])  # type: ignore[arg-type]


def current_context() -> RequestContext:
    return RequestContext(
        request_id=request_id_var.get(),
        trace_id=trace_id_var.get(),
        job_id=job_id_var.get(),
        user_id=user_id_var.get(),
        source=source_var.get(),
    )
