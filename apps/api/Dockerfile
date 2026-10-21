# Two stages: uv and the build run in the first; the runtime image is the plain slim Python with
# the finished virtualenv and the app (no uv, no pip cache, no tests, no migrations: those run
# from the repo in the deploy workflow, docs/ops/deploy.md).
FROM python:3.14-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
# the app's own bytecode too, so a cold start compiles nothing
RUN /app/.venv/bin/python -m compileall -q app

FROM python:3.14-slim-bookworm
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
WORKDIR /app
COPY --from=build /app /app
RUN useradd --system --uid 10001 ilm
USER ilm

# The API only serves, as the restricted runtime role ilm_app. Migrations are a separate
# workflow step with the owner role (docs/ops/deploy.md). Forwarded headers are believed only
# from FORWARDED_ALLOW_IPS (default: localhost); the deploy sets "*" there, which is safe only
# together with PROXY_SHARED_SECRET.
# --timeout-keep-alive: uvicorn closes an idle keep-alive connection after 5 s by default, while
# the Vercel/Next proxy (and Render's balancer) reuse connections for longer: a request sent just
# as the server closed it fails with ECONNRESET. Ours must outlive every client's idle timeout.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8430} --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" --timeout-keep-alive ${KEEPALIVE_TIMEOUT:-120}"]
