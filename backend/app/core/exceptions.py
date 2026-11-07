"""Unified application errors and FastAPI exception handlers.

Error-code ranges follow `docs/API.md` §0.3.
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Business error carrying a stable code + HTTP status."""

    def __init__(self, code: int, message: str, status_code: int = 400, data: Any = None) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.data = data
        super().__init__(message)


# Canonical codes (docs/API.md §13)
class Err:
    VALIDATION = 40001
    UNSUPPORTED_FILE = 40002
    FILE_TOO_LARGE = 40003
    BAD_CREDENTIALS = 40101
    TOKEN_EXPIRED = 40102
    TOKEN_INVALID = 40103
    FORBIDDEN = 40301
    AUDIT_IMMUTABLE = 40302
    FALLBACK_NO_TRAIN = 40303
    NOT_FOUND = 40401
    CONFLICT = 40901
    CORRECTION_INVALID = 42201
    INTERNAL = 50001
    DEGRADED = 50301


def success(data: Any = None, message: str = "ok", status_code: int = 200) -> JSONResponse:
    from app.core.envelope import success as _success

    return _success(data, message, status_code)


def failure(code: int, message: str, status_code: int = 400, data: Any = None, request_id: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message, "data": data}
    if request_id:
        body["request_id"] = request_id
    return JSONResponse(status_code=status_code, content=body)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return failure(exc.code, exc.message, exc.status_code, exc.data, _request_id(request))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(f"{'.'.join(str(p) for p in e.get('loc', []))}: {e.get('msg')}" for e in exc.errors())
        return failure(Err.VALIDATION, f"validation error: {detail}", 400, request_id=_request_id(request))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code_map = {400: Err.VALIDATION, 401: Err.TOKEN_INVALID, 403: Err.FORBIDDEN, 404: Err.NOT_FOUND, 409: Err.CONFLICT}
        code = code_map.get(exc.status_code, Err.INTERNAL)
        return failure(code, str(exc.detail), exc.status_code, request_id=_request_id(request))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        return failure(Err.INTERNAL, f"internal error: {exc}", 500, request_id=_request_id(request))
