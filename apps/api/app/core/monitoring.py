"""Error monitoring (Sentry), off unless SENTRY_DSN is set. See docs/ops/monitoring.md.

The database holds real personal data, so nothing leaves the process unscrubbed: no request
bodies, no cookies, no query-string values, only a short header allowlist, no user but the
internal id, no local variables, and any phone number or e-mail inside a string is replaced.
"""

import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, urlsplit, urlunsplit

import sentry_sdk
from fastapi.exceptions import RequestValidationError
from sentry_sdk.types import Event, Hint
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings

FILTERED = "[Filtered]"
SAFE_HEADERS = frozenset(
    {"accept", "accept-language", "content-length", "content-type", "host", "user-agent"}
)
# Expected client errors (401/403/404/409/422/428 ...): never worth an alert.
IGNORED = (RequestValidationError,)
# Event fields that are structure, not user text (ids and timestamps look like numbers).
_STRUCTURAL = frozenset(
    {
        "event_id",
        "timestamp",
        "start_timestamp",
        "release",
        "environment",
        "platform",
        "level",
        "type",
        "trace_id",
        "span_id",
        "parent_span_id",
        "sdk",
        "modules",
    }
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# 9+ digits, optionally with + ( ) - . or spaces between them: a phone number in any format
_PHONE = re.compile(r"(?<![\w.])\+?\d(?:[\s().-]{0,2}\d){8,}(?![\w])")


def scrub_text(value: str) -> str:
    return _PHONE.sub(FILTERED, _EMAIL.sub(FILTERED, value))


def _scrub(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, Mapping):
        return {k: v if k in _STRUCTURAL else _scrub(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_scrub(v) for v in value]
    return value


def _query(raw: str) -> str:
    return "&".join(f"{k}={FILTERED}" for k, _ in parse_qsl(raw, keep_blank_values=True))


def _request(request: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"method": request.get("method")}
    if url := request.get("url"):
        parts = urlsplit(str(url))
        out["url"] = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    if request.get("query_string"):
        out["query_string"] = _query(str(request["query_string"]))
    headers = request.get("headers") or {}
    out["headers"] = {k: v for k, v in headers.items() if str(k).lower() in SAFE_HEADERS}
    return out  # no data, cookies, env


def scrub_event(event: Event) -> Event:
    """Everything personal removed from one event or transaction."""
    out: dict[str, Any] = dict(event)
    if "request" in out:
        out["request"] = _request(out["request"])
    user = out.get("user")
    if user:
        out["user"] = {"id": user["id"]} if user.get("id") else {}
    crumbs = (out.get("breadcrumbs") or {}).get("values") or []
    if "breadcrumbs" in out:
        out["breadcrumbs"] = {
            "values": [
                {k: v for k, v in c.items() if k != "data"}  # SQL, URLs, args: not worth the risk
                for c in crumbs
            ]
        }
    for name in ("server_name", "extra", "contexts"):
        out.pop(name, None)
    for frames in (
        v.get("stacktrace") or {} for v in (out.get("exception") or {}).get("values", [])
    ):
        for frame in frames.get("frames", []):
            frame.pop("vars", None)
    return _scrub(out)  # type: ignore[no-any-return]


def before_send(event: Event, hint: Hint) -> Event | None:
    exc = (hint.get("exc_info") or (None, None))[1]
    if isinstance(exc, IGNORED):
        return None
    if isinstance(exc, StarletteHTTPException) and exc.status_code < 500:
        return None
    return scrub_event(event)


def init_sentry(dsn: str | None = None) -> bool:
    dsn = settings.sentry_dsn if dsn is None else dsn
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=settings.env,
        release=settings.render_git_commit or None,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        traces_sample_rate=0.02,
        profiles_sample_rate=0.0,
        before_send=before_send,
        before_send_transaction=lambda event, _hint: scrub_event(event),
    )
    return True
