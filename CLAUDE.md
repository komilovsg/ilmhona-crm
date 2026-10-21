# ilmhona CRM

CRM for ilmhona skills accelerator (2 branches). Replaces ilmhona-crm.lovable.app.
Spec: `docs/SPEC.md` (data model, rights, metrics, stages). Old system and its bugs: `docs/ANALYSIS.md` (#N = bug number).
Patterns come from `~/Developer/my-hrm` — copy and simplify, don't reinvent. No multi-tenancy, RLS, RabbitMQ, admin app or on-prem here.

## Layout
- `apps/api` — FastAPI, SQLAlchemy 2 async, Alembic, Postgres. Python 3.14, uv.
- `apps/web` — Next.js 16 (App Router), React 19, HeroUI 2, Tailwind 4. Russian only, no i18n library.
- Production: Vercel (web) -> Render (API, `render.yaml`) -> Neon; workflows deploy-api / keepalive / daily / backup. Read `docs/ops/deploy.md` before touching any of it.
- `compose.yaml` — dev Postgres on :55433. API :8200, web :3200 (my-hrm owns 55432/8100/3100 — never touch them).

## Commands
`make up` · `make migrate` · `make test` · `make lint` · `make api` · `make web` · `make check`

## Rules
- Every bug in ANALYSIS.md is prevented by a DB constraint or a single code path, with a test naming the bug (`test_bug_04_…`).
- Every update checks the row version (#25): the client sends the version it loaded in `X-Record-Version`, the endpoint calls `check_version` (`app/core/versioning.py`), a mismatch is 409 `stale_version`; updates apply only the fields sent (PATCH). Web edit forms save through `useVersionedSave` + `ConflictDialog`.
- All numbers shown anywhere come from `app/metrics` only.
- Every endpoint checks permission + scope (branch; instructor sees only own cohorts) on the backend. Every write goes to `audit_log` and reads as a Russian sentence: add the action to `app/audit/sentences.py` (the one formatter).
- Every table has an Excel export through the one shared mechanism: the list module declares `Col`s and a `GET <list>/export` that reuses the list's `where`/select (`app/export.py`), the web uses `ExportButton`. Rights = view of the section, scope applies, every export writes an `export` audit entry; text cells are formula-neutralised, rows capped at 50 000.
- Every page uses the shared loading / empty / error states (`QueryState`, `EmptyState`, `ErrorState`, shape-matched skeletons in `components/Skeletons.tsx`, `LoadingButton`, a `loading.tsx` per route segment). No bare spinners, no layout jumps; check with `pnpm cls` (apps/web/scripts/cls.mjs).
- Next.js 16 differs from older versions: read `apps/web/node_modules/next/dist/docs/` before using an API.
- UI: brand tokens and dark theme from SPEC «Дизайн»; every screen works at 1440 and 390 px, light and dark.
- Repo is public: no secrets, no real personal data (fixtures are fake; old-system exports live in gitignored `import-data/`).
- Git: feature branch → push → owner merges by hand. Never push to `main`, never create/merge PRs.
- Commits: English, lowercase, imperative, ≤50 chars; never mention AI.
- Migrations: never edit one that ran on a shared DB; add a new one.
