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
CLIENT_IP_HEADER = "x-client-ip"
OPEN_PATHS = {"/api/health"}
# Set on the scope once the proxy secret matched: only then is X-Client-IP trustworthy.
VIA_PROXY = "ilm_via_proxy"


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
        matched = len(presented) == 1 and matches_any(presented[0], self.secrets)
        if scope["path"] not in OPEN_PATHS and not matched:
            await _problem(Request(scope), PROXY_REQUIRED)(scope, receive, send)
            return
        # The request came through the trusted web proxy: X-Client-IP it set may be believed.
        scope = {**scope, VIA_PROXY: matched}
        await self.app(scope, receive, send)


def client_ip(request: Request) -> str:
    """The caller's address for the login lockout, or "" when there is none.

    Behind the proxy (secret matched, `VIA_PROXY` on the scope) the address is the single
    `X-Client-IP` the web proxy derived from Vercel's own header and set after dropping any the
    browser sent, so a forged X-Forwarded-For cannot steer the per-address lockout. Without a
    secret (local development, tests) it is the direct peer. A client-supplied X-Client-IP is
    never believed on its own: a direct caller is refused by the proxy middleware first."""
    if request.scope.get(VIA_PROXY):
        host = request.headers.get(CLIENT_IP_HEADER, "")
    else:
        host = request.client.host if request.client else ""
    try:
        return str(ip_address(host))
    except ValueError:
        return ""
