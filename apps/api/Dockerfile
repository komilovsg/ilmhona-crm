FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev && useradd --system --uid 10001 ilm
USER ilm

# The API only serves, as the restricted runtime role ilm_app. Migrations are a separate
# workflow step with the owner role (docs/ops/deploy.md). Forwarded headers are believed only
# from FORWARDED_ALLOW_IPS (default: localhost); the deploy sets "*" there, which is safe only
# together with PROXY_SHARED_SECRET.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8430} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
