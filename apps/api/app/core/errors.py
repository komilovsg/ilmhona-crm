"""The error registry: every code the API answers is declared once.

    ROLE_IN_USE = errors.define("role_in_use", 409, "Role is assigned")
    raise DomainError(ROLE_IN_USE, users_count=2)

Every error leaves as `application/problem+json` with a stable `code`; the web shows its Russian
text from `apiErrors` (tests/test_error_registry.py keeps both lists equal).
"""

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger(__name__)
MEDIA_TYPE = "application/problem+json"


class ErrorDef:
    def __init__(self, code: str, status: int, title: str) -> None:
        self.code, self.status, self.title = code, status, title


class ErrorRegistry:
    def __init__(self) -> None:
        self._defs: dict[str, ErrorDef] = {}
        self._constraints: dict[str, ErrorDef] = {}

    def define(self, code: str, status: int, title: str) -> ErrorDef:
        if code in self._defs:
            raise ValueError(f"error code {code!r} is defined twice")
        self._defs[code] = ErrorDef(code, status, title)
        return self._defs[code]

    def on_constraint(self, constraint: str, error: ErrorDef) -> None:
        """A violated DB constraint answers as `error` instead of a 500."""
        self._constraints[constraint] = error

    def codes(self) -> list[str]:
        return sorted(self._defs)

    def for_constraint(self, name: str | None) -> ErrorDef | None:
        return self._constraints.get(name) if name else None


errors = ErrorRegistry()

VALIDATION_FAILED = errors.define("validation_failed", 422, "Request validation failed")
INTERNAL_ERROR = errors.define("internal_error", 500, "Internal server error")
BAD_REQUEST = errors.define("bad_request", 400, "Malformed request")
NOT_FOUND = errors.define("not_found", 404, "Not found")
METHOD_NOT_ALLOWED = errors.define("method_not_allowed", 405, "Method not allowed")
NOT_AUTHENTICATED = errors.define("not_authenticated", 401, "No valid session")
FORBIDDEN = errors.define("forbidden", 403, "Not allowed")
CSRF_HEADER_MISSING = errors.define("csrf_header_missing", 403, "Missing X-Requested-With header")
CONCURRENT_CHANGE = errors.define("concurrent_change", 409, "Changed by someone else, retry")
# params: version (current), changed_by, changed_at (last audit entry of the row), current (record)
STALE_VERSION = errors.define("stale_version", 409, "Changed by someone else since it was loaded")
VERSION_REQUIRED = errors.define("version_required", 428, "If-Match header with the version")
_BY_STATUS = {e.status: e for e in (BAD_REQUEST, NOT_FOUND, METHOD_NOT_ALLOWED)}


class DomainError(StarletteHTTPException):
    def __init__(self, error: ErrorDef, /, **params: Any) -> None:
        super().__init__(error.status, error.code)
        self.error = error
        self.params = params


def _problem(
    request: Request,
    error: ErrorDef,
    params: dict[str, Any] | None = None,
    errs: list[dict[str, Any]] | None = None,
    status: int | None = None,
) -> Response:
    code = status or error.status
    body = {
        "type": f"urn:ilmhona:problem:{error.code}",
        "title": error.title,
        "status": code,
        "code": error.code,
        "detail": error.code,
        "params": params or {},
        "errors": errs or [],
        "instance": request.url.path,
    }
    return JSONResponse(jsonable_encoder(body), status_code=code, media_type=MEDIA_TYPE)


async def _domain(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, DomainError)
    return _problem(request, exc.error, exc.params)


async def _http(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, StarletteHTTPException)
    return _problem(request, _BY_STATUS.get(exc.status_code, BAD_REQUEST), status=exc.status_code)


async def _validation(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, RequestValidationError)
    errs = [
        {"loc": list(e.get("loc", ())), "code": str(e.get("type", "invalid"))} for e in exc.errors()
    ]
    return _problem(request, VALIDATION_FAILED, errs=errs)


async def _integrity(request: Request, exc: Exception) -> Response:
    assert isinstance(exc, IntegrityError)
    constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
    error = errors.for_constraint(constraint)
    if error is None:
        return await _unhandled(request, exc)
    return _problem(request, error)


async def _unhandled(request: Request, exc: Exception) -> Response:
    log.error(
        "unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path, exc_info=exc
    )
    return _problem(request, INTERNAL_ERROR)


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain)
    app.add_exception_handler(StarletteHTTPException, _http)
    app.add_exception_handler(RequestValidationError, _validation)
    app.add_exception_handler(IntegrityError, _integrity)
    app.add_exception_handler(Exception, _unhandled)
