# Deploying ilmhona CRM

```
browser -> Vercel (apps/web, ilmhona-crm.vercel.app)
             -> /api/* rewrite + X-Proxy-Secret -> Render (apps/api, ilmhona-api.onrender.com)
                  -> Neon Postgres (ilmhona-db, direct URL, role ilm_app)
```

Pattern copied from my-hrm, without RLS, RabbitMQ and an admin app.

| Part | Where | Name / id |
|---|---|---|
| Database | Neon (Vercel marketplace), aws-eu-central-1, Postgres 18 | project `ilmhona-db` (`icy-waterfall-82517700`), db `neondb` |
| API | Render free, Frankfurt, Docker | `ilmhona-api` (`srv-dbc1c33ncjis7380m3a0`), `render.yaml` |
| Web | Vercel, root `apps/web`, production branch `main` | `ilmhona-crm` (`prj_91vTa2EjLoxLAwU1v8sdnLk7Amqg`) |
| Backups | private repo `komilovsg/ilmhona-backups` | encrypted dumps |

## What runs when

```
push to main -> ci (green) -> deploy-api: wait for Vercel production deployment of the same sha
                                          -> migrate (owner URL) -> Render deploy hook -> wait for the commit in /api/health
                                          -> check the web's /version sha equals the api sha
                           -> Vercel builds and deploys apps/web by itself (git integration; only main, see apps/web/vercel.json)
every 10 min, 08:00-20:59 Dushanbe  keepalive   curl /api/health through the Vercel URL
every 2 h, 21:00-07:59 Dushanbe     uptime      same check; a non-200 fails the run (e-mail), see monitoring.md
00:30 Dushanbe (19:30 UTC)          daily       python -m app.cli daily (as ilm_app)
01:30 Dushanbe (20:30 UTC)          backup      pg_dump -> age -> ilmhona-backups, last 30 kept
```

All workflows have the least `permissions:` (`contents: read`, or none; `deploy-api` also reads
`deployments` and `statuses`).

### Web before API

Vercel can be rate-limited (Hobby: 100 deployments a day), and an API deployed without its front
breaks saves. So `deploy-api` first polls the GitHub deployments of the commit (environment
`Production`, created by Vercel) every 20 s: `success` lets the migration and the API deploy go on,
`failure`/`error` fails the job («Vercel не выкатил фронт — API не выкатываем»), 20 minutes without a
result fails it too. After the API is live the job reads `<WEB_URL>/version` (repo variable `WEB_URL`,
default `https://ilmhona-crm.vercel.app`; the route returns `VERCEL_GIT_COMMIT_SHA`, public, no
secrets) and fails when it differs from the API's sha. `apps/web/vercel.json` turns off preview
deployments of every branch except `main`.

## Roles in the database

- `neondb_owner` — the owner. DDL only: used by the `migrate` job (`alembic upgrade head`),
  never by the API. Secret `MIGRATION_DATABASE_URL` of the GitHub environment `api-production`.
- `ilm_app` — the runtime role of the API, the daily job and the backup. `LOGIN`, no superuser,
  no create-db/role, no bypass-rls. `SELECT/INSERT/UPDATE/DELETE` on tables and `USAGE/SELECT`
  on sequences of schema `public` (default privileges of the owner cover every table a future
  migration adds), no DDL. `audit_log` is append-only for it (`SELECT, INSERT` only), and
  `alembic_version` is read-only.

One-time setup (done; kept here to rebuild the database from scratch), as `neondb_owner`:

```sql
CREATE ROLE ilm_app LOGIN PASSWORD '<generated>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT CONNECT ON DATABASE neondb TO ilm_app;
GRANT USAGE ON SCHEMA public TO ilm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ilm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE neondb_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ilm_app;
```

Migration 0011 (re)applies the table grants, the append-only `audit_log` and the read-only
`alembic_version` whenever the role exists, so a fresh `alembic upgrade head` rebuilds them.

Use the **direct** (non-pooled) Neon host. SQLAlchemy URLs are
`postgresql+asyncpg://<role>:<password>@<host>/neondb?ssl=require`.

## Secrets and variables

| Where | Name | What |
|---|---|---|
| Render env | `ENV=production`, `COOKIE_SECURE=true`, `FORWARDED_ALLOW_IPS=*` | plain |
| Render env | `DATABASE_URL` | `ilm_app` URL |
| Render env | `JWT_SECRET`, `PROXY_SHARED_SECRET` | 32+ random characters; the app refuses to start in production without them |
| Vercel env (production) | `API_URL` | `https://ilmhona-api.onrender.com` |
| Vercel env (production) | `PROXY_SHARED_SECRET` | same value as on Render (sensitive) |
| GitHub env `api-production` | `MIGRATION_DATABASE_URL` | owner URL (asyncpg form) |
| GitHub env `api-production` | `DATABASE_URL` | `ilm_app` URL, for the daily job |
| GitHub env `api-production` | `RENDER_DEPLOY_HOOK_URL` | Render *Settings -> Deploy Hook* (not available through the API) |
| GitHub env `backup` | `BACKUP_DATABASE_URL` | `ilm_app` URL in libpq form (`postgresql://...?sslmode=require`) |
| GitHub env `backup` | `BACKUP_DEPLOY_KEY` | private half of the write deploy key of `ilmhona-backups` |
| GitHub variables | `BACKUP_AGE_PUBLIC_KEY`, `API_HEALTH_URL`, `WEB_HEALTH_URL` | public |

Both environments accept deployments from `main` only. Rotating `PROXY_SHARED_SECRET`: the API
accepts two comma-separated values, so put `old,new` on Render, change Vercel to `new`, then
drop `old`.

## Forwarded address and the proxy secret

Render's proxy has no fixed address range, so uvicorn runs with `--forwarded-allow-ips=*` and
takes the client address from `X-Forwarded-For` (Vercel overwrites that header with the address
it saw). That is safe **only** together with `PROXY_SHARED_SECRET`: the onrender.com URL is
public and the secret keeps out everyone but the Vercel proxy (`app/core/proxy.py`; only
`/api/health` is open). The login lockout (`app/auth/api.py`) relies on this address: 5 failed
tries lock one (login, address) pair for 15 minutes; a higher per-login ceiling (30 failures
from any addresses together) still locks the login itself.

## Migrations

`alembic upgrade head` with the owner URL in `DATABASE_URL` (`deploy-api.yml`, job `migrate`);
hand-written SQL, one transaction per migration, a re-run at head does nothing. Changes follow
expand -> migrate -> contract: the previous version of the API must keep working on the new
schema while the deploy runs. If `migrate` fails nothing is deployed: fix forward with a new
migration. Never edit a migration that already ran on Neon.

## Deploy hook and health

`autoDeploy: false`: Render deploys only when `deploy-api` posts the hook with `&ref=<sha>`.
`GET /api/health` returns `{"status":"ok","version":"<git sha>"}` (`RENDER_GIT_COMMIT`); the
workflow waits (up to 20 min) until the version equals the commit. Free Render sleeps after 15
minutes without traffic; `keepalive` keeps it awake 08:00-20:59 Asia/Dushanbe, outside that the
first visitor waits for a cold start (about a minute).

## Connections, compression, image

- uvicorn runs with `--timeout-keep-alive ${KEEPALIVE_TIMEOUT:-120}`: its default (5 s) is shorter
  than the idle time the Vercel proxy and Render's balancer keep a connection, and a request sent
  as the server closes it fails with `ECONNRESET`. Keep it above every client's idle timeout.
- Pool (`DB_POOL_SIZE` 5, `DB_MAX_OVERFLOW` 5, `DB_POOL_RECYCLE` 240 s): connections are recycled
  before Neon's idle suspend and pinged on checkout; 10 connections stay far below Neon's cap.
- JSON responses over 1 KB are gzipped (`GZipMiddleware`); xlsx files never are.
- The image is two-stage (`python:3.14-slim`, finished virtualenv + `app/` only, ~345 MB); uv,
  tests, tools and migrations are not in it. Measuring: `apps/api/tools` (`seed_load`, `bench`,
  `explain`, `make_snapshot`, `time_import`, `delay_proxy`) work on a local database only.

## Daily job

`python -m app.cli daily`: cohort statuses from their dates, enrollments of finished cohorts
(`завершил` / `выпускник`), and `login_attempt` / `login_ip_attempt` rows untouched for a day
are deleted. Safe to run any number of times; also *Actions -> daily -> Run workflow*.

## Demo data

`python -m app.cli seed-demo` loads a fake dataset (both branches: users per role, rooms,
courses, cohorts with lessons, students, enrollments, attendance, grades, payments, payouts,
leads, campaigns; all names invented) and prints the demo users' password once.
`python -m app.cli wipe-demo` deletes exactly those rows: every demo row has an id in the
reserved range `de000000-0000-4000-...`, nothing else does. Run against production with
`ENV=production DATABASE_URL=<ilm_app URL> uv run python -m app.cli seed-demo`. A wipe fails
(and changes nothing) if a real row still points at a demo one, e.g. a real payment on a demo
enrollment.

## Backups

`backup.yml` dumps schema `public` (plus the `citext` and `btree_gist` extensions), gzips,
encrypts with `age` to the public key in `BACKUP_AGE_PUBLIC_KEY` and pushes
`dumps/ilmhona-<UTC time>.sql.gz.age` to `komilovsg/ilmhona-backups`; only the newest 30 files
stay in the tree (git history keeps older ones: delete or squash the repo when it grows).
The private key is `~/.config/ilmhona/backup-age-key.txt` on the owner's machine only: keep a
second copy offline, without it the dumps cannot be read. The dump has no owners and no
grants, and it contains `CREATE SCHEMA public` and the two extensions. Restore (drilled, see
`restore-drill.md`):

```
# 1. empty database, the `public` schema removed (the dump creates it)
psql "<owner URL, db postgres>" -c "CREATE DATABASE neondb"
psql "<owner URL>" -c "DROP SCHEMA public"
# 2. data
age -d -i ~/.config/ilmhona/backup-age-key.txt dumps/<file>.sql.gz.age | gunzip \
  | psql "<owner URL>" -v ON_ERROR_STOP=1
# 3. runtime role and grants (same as "Roles in the database"; the dump carries none)
CREATE ROLE ilm_app LOGIN PASSWORD '<generated>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT CONNECT ON DATABASE neondb TO ilm_app;
GRANT USAGE ON SCHEMA public TO ilm_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ilm_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ilm_app;
REVOKE UPDATE, DELETE ON audit_log FROM ilm_app;
REVOKE ALL ON alembic_version FROM ilm_app;
GRANT SELECT ON alembic_version TO ilm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ilm_app;
ALTER DEFAULT PRIVILEGES FOR ROLE <owner> IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO ilm_app;
```

Without step 1 the load prints `schema "public" already exists` (harmless, but fatal with
`ON_ERROR_STOP`). Check with `select version_num from alembic_version` and row counts. The
target must be Postgres 18 (or newer): the dump sets `transaction_timeout`.

## Private app

`robots.txt` is `Disallow: /`, every response carries `X-Robots-Tag: noindex, nofollow`, and the
root layout sets `robots: noindex`.
