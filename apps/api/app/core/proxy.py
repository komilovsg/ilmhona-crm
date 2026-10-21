"""Only the web proxy (Vercel) may reach the API (PROXY_SHARED_SECRET, SPEC «Деплой»).

The web app adds `X-Proxy-Secret` server-side to every `/api/*` request it forwards. With a
secret configured, a request without a matching header is refused before anything else runs,
so the API's public URL cannot be used directly (brute force, crafted headers). The health
check stays open for the platform probe and keep-alive. The header is dropped from the scope
either way: nothing downstream ever sees the secret.
"""

import hmac
from collections.abc import Sequence
from ipaddress import ip_address

from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.errors import _problem, errors

PROXY_REQUIRED = errors.define("proxy_required", 403, "Direct API access is not allowed")
HEADER = b"x-proxy-secret"
OPEN_PATHS = {"/api/health"}


def matches_any(presented: bytes, secrets: Sequence[bytes]) -> bool:
    """Constant time over every configured secret (two during a rotation)."""
    ok = False
    for secret in secrets:
        ok |= hmac.compare_digest(presented, secret)
    return ok


class ProxySecretRequired:
    def __init__(self, app: ASGIApp, secrets: Sequence[bytes]) -> None:
        if not secrets:
            raise ValueError("ProxySecretRequired needs at least one secret")
        self.app = app
        self.secrets = tuple(secrets)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        presented = [v for k, v in scope["headers"] if k.lower() == HEADER]
        scope = {**scope, "headers": [(k, v) for k, v in scope["headers"] if k.lower() != HEADER]}
        if scope["path"] not in OPEN_PATHS and not (
            len(presented) == 1 and matches_any(presented[0], self.secrets)
        ):
            await _problem(Request(scope), PROXY_REQUIRED)(scope, receive, send)
            return
        await self.app(scope, receive, send)


def client_ip(request: Request) -> str:
    """The caller's address for the login lockout, or "" when there is none.

    uvicorn (--proxy-headers, FORWARDED_ALLOW_IPS=* on Render) puts the first X-Forwarded-For
    entry into `request.client`; Vercel overwrites that header with the address it saw. This is
    safe only together with PROXY_SHARED_SECRET (every request without it is refused before it
    gets here); without a secret (local development, tests) it is the direct peer."""
    host = request.client.host if request.client else ""
    try:
        return str(ip_address(host))
    except ValueError:
        return ""
