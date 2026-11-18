"""`Cache-Control: no-store` on every /api/v1 response: personal data must never sit in a browser
or proxy cache (the Next rewrite adds no headers of its own). /api/health may be `no-cache`.
Certificate images and fonts are content-addressed and carry no personal data: they set their own
long private cache."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

OWN_CACHE = ("/api/v1/cert-assets/", "/api/v1/cert-fonts/")


class NoStore:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if path.startswith("/api/v1/") and not path.startswith(OWN_CACHE):
                    headers["Cache-Control"] = "no-store"
                    headers["Pragma"] = "no-cache"
                elif path == "/api/health":
                    headers["Cache-Control"] = "no-cache"
            await send(message)

        await self.app(scope, receive, send_with_headers)
