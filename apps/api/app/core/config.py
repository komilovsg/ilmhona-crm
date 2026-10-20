"""Settings from the environment (`.env` is ignored by git). Defaults fit local development."""

import re

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-secret-change-me-dev-only-secret"  # noqa: S105
_STRONG_SECRET = re.compile(r"[\x21-\x7e]{32,}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "development"  # development | test | production
    database_url: str = "postgresql+asyncpg://ilm@localhost:55433/ilmhona"
    jwt_secret: str = DEV_JWT_SECRET
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 30
    cookie_secure: bool = False
    temp_password_days: int = 7
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    # Shared secret the web proxy sends in X-Proxy-Secret (app/core/proxy.py). Comma-separated:
    # two values are accepted while it is rotated. Empty = no check (local development).
    proxy_shared_secret: str = ""

    @property
    def proxy_secrets(self) -> tuple[bytes, ...]:
        return tuple(s.strip().encode() for s in self.proxy_shared_secret.split(",") if s.strip())

    @property
    def api_docs(self) -> bool:
        """Swagger and the OpenAPI schema stay out of production."""
        return self.env != "production"

    def check(self) -> None:
        if self.env != "production":
            return
        if self.jwt_secret == DEV_JWT_SECRET or not _STRONG_SECRET.fullmatch(self.jwt_secret):
            raise RuntimeError("production needs JWT_SECRET: 32+ printable characters")
        if not self.cookie_secure:
            raise RuntimeError("production needs COOKIE_SECURE=true")
        secrets = self.proxy_secrets
        if not secrets or any(not _STRONG_SECRET.fullmatch(s.decode()) for s in secrets):
            raise RuntimeError("production needs PROXY_SHARED_SECRET: 32+ printable characters")


settings = Settings()
