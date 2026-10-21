"""Sentry is off without a DSN, and its scrubber leaves no personal data (fake values only)."""

import json

from fastapi.exceptions import RequestValidationError
from sentry_sdk import get_client
from starlette.exceptions import HTTPException

from app.core.errors import NOT_FOUND, DomainError
from app.core.monitoring import before_send, init_sentry, scrub_text


def _event() -> dict:
    return {
        "event_id": "0123456789abcdef0123456789abcdef",
        "timestamp": "2026-10-21T10:00:00.000000Z",
        "request": {
            "method": "POST",
            "url": "https://x.test/api/v1/students?phone=%2B992900000000&q=Test",
            "query_string": "phone=%2B992900000000&q=Test",
            "data": {"name": "Test Person", "phone": "+992 90 000 0000"},
            "cookies": {"ilm_access": "secret-token"},
            "headers": {
                "Cookie": "ilm_access=secret-token",
                "Authorization": "Bearer abc",
                "X-Client-Ip": "203.0.113.5",
                "User-Agent": "UA/1.0",
            },
            "env": {"REMOTE_ADDR": "203.0.113.5"},
        },
        "user": {
            "id": "u-1",
            "email": "person@example.test",
            "username": "tp",
            "ip_address": "1.1.1.1",
        },
        "server_name": "host",
        "extra": {"body": "Test Person"},
        "breadcrumbs": {
            "values": [
                {"category": "query", "message": "call +992900000000", "data": {"sql": "select 1"}}
            ]
        },
        "logentry": {"message": "failed for person@example.test tel 992-90-000-00-00"},
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": "bad phone +992 90 000 0000 / person@example.test",
                    "stacktrace": {"frames": [{"function": "f", "vars": {"name": "Test Person"}}]},
                }
            ]
        },
    }


def test_scrubber_removes_personal_data() -> None:
    out = before_send(_event(), {})  # type: ignore[arg-type]
    assert out is not None
    dump = json.dumps(out)
    for leaked in (
        "992",
        "person@example.test",
        "Test Person",
        "secret-token",
        "Bearer",
        "203.0.113.5",
        "1.1.1.1",
        "tp",
        "select 1",
    ):
        if leaked == "tp":
            assert '"username"' not in dump
        else:
            assert leaked not in dump, leaked
    assert out["user"] == {"id": "u-1"}
    assert out["request"]["headers"] == {"User-Agent": "UA/1.0"}
    assert out["request"]["url"] == "https://x.test/api/v1/students"
    assert out["request"]["query_string"] == "phone=[Filtered]&q=[Filtered]"
    assert out["timestamp"] == "2026-10-21T10:00:00.000000Z"
    assert out["event_id"] == "0123456789abcdef0123456789abcdef"


def test_scrub_text_formats() -> None:
    for phone in ("+992900000000", "+992 (90) 000-00-00", "900000000", "90.000.00.00"):
        assert scrub_text(f"call {phone} now") == "call [Filtered] now"
    assert scrub_text("order 12345 ok") == "order 12345 ok"
    assert scrub_text("a.b+c@d-e.example.test") == "[Filtered]"


def test_expected_errors_are_dropped() -> None:
    for exc in (
        DomainError(NOT_FOUND),
        HTTPException(403),
        RequestValidationError([]),
    ):
        assert before_send({}, {"exc_info": (type(exc), exc, None)}) is None
    boom = HTTPException(500)
    assert before_send({}, {"exc_info": (type(boom), boom, None)}) is not None
    err = ValueError("x")
    assert before_send({}, {"exc_info": (type(err), err, None)}) is not None


def test_disabled_without_dsn() -> None:
    assert init_sentry("") is False
    assert not get_client().is_active()
