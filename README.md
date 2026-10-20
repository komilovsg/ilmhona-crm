# ilmhona CRM

CRM for the ilmhona skills accelerator (two branches: Душанбе, Истаравшан). Stage 0: sign-in with
temporary passwords, users, roles with a permission matrix, audit log. Spec: `docs/SPEC.md`.

- `apps/api` — FastAPI, SQLAlchemy 2 async, Alembic, Postgres 18 (Python 3.14, uv)
- `apps/web` — Next.js 16, React 19, HeroUI 2, Tailwind 4 (pnpm), Russian only

## Run locally

Needs Docker, uv, pnpm, Node 24.

```sh
make up                       # Postgres on 127.0.0.1:55433
make migrate                  # tables + branches + system roles
(cd apps/api && uv run python -m app.cli create-superadmin --login admin)   # prints a temp password
make api                      # API on :8200   (docs: http://localhost:8200/api/docs)
(cd apps/web && pnpm install) && make web                                   # web on :3200
```

Open http://localhost:3200, sign in as `admin` with the printed password, set your own.
The temporary password is shown once and is valid for 7 days.

`make check` runs lint, type checks and tests of both apps (API tests need `make up`; they use
their own database `ilmhona_test`, override with `TEST_DB_NAME`, server with `DATABASE_URL`).

## Settings (env)

`DATABASE_URL`, `JWT_SECRET`, `COOKIE_SECURE`, `ENV`, `PROXY_SHARED_SECRET` (same value on the
API and the web app; the API then refuses requests that bypass the web proxy), `API_URL` for the
web proxy. `ENV=production` refuses to start without a strong `JWT_SECRET` and
`PROXY_SHARED_SECRET` (32+ characters) and `COOKIE_SECURE=true`. See
`apps/api/app/core/config.py`.
