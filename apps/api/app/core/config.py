"""Settings from the environment (`.env` is ignored by git). Defaults fit local development."""

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-secret-change-me-dev-only-secret"  # noqa: S105


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

    def check(self) -> None:
        if self.env == "production" and (
            self.jwt_secret == DEV_JWT_SECRET or not self.cookie_secure
        ):
            raise RuntimeError("production needs JWT_SECRET and COOKIE_SECURE=true")


settings = Settings()
