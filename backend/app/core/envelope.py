"""Envelope response helpers (docs/API.md §0.3).

Every 2xx JSON response is wrapped as `{"code": 0, "message": "ok", "data": <payload>}`.
`EnvelopeRoute` applies this automatically; `success()` is available for manual use.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.background import BackgroundTask


class EnvelopeJSONResponse(JSONResponse):
    """JSONResponse that knows it is already enveloped — skipped by EnvelopeRoute."""


def success(data: Any = None, message: str = "ok", status_code: int = 200) -> EnvelopeJSONResponse:
    return EnvelopeJSONResponse(
        status_code=status_code,
        content={"code": 0, "message": message, "data": data},
    )


class EnvelopeRoute(APIRoute):
    """Route class that wraps 2xx JSON responses in the standard envelope.

    - Errors (4xx/5xx) are produced by `core/exceptions` handlers and already enveloped.
    - `204 No Content` and non-JSON responses pass through untouched.
    - Responses produced by `success()` are recognised and left alone.
    """

    def get_route_handler(self):  # noqa: ANN201
        original_handler = super().get_route_handler()

        async def wrapped(request: Request) -> Response:
            response = await original_handler(request)
            return _maybe_wrap(response)

        return wrapped


def _maybe_wrap(response: Response) -> Response:
    if isinstance(response, EnvelopeJSONResponse):
        return response
    if response.status_code >= 400 or response.status_code == 204:
        return response
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return response

    # JSONResponse / Response both expose the serialized body via .body
    raw = getattr(response, "body", None)
    if raw is None:
        return response
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return response

    if isinstance(payload, dict) and "code" in payload and "data" in payload:
        return response

    return EnvelopeJSONResponse(
        status_code=response.status_code,
        content={"code": 0, "message": "ok", "data": payload},
        headers=_safe_headers(response.headers),
        background=response.background if isinstance(response.background, BackgroundTask) else None,
    )


def _safe_headers(original: Any) -> dict[str, str]:
    """Copy headers, dropping ones that will be recomputed for the new body."""
    drop = {"content-length", "content-encoding", "transfer-encoding", "content-type"}
    return {k: v for k, v in original.items() if k.lower() not in drop}
