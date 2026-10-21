# Restore drill

Date: 2026-10-21. Dump: `ilmhona-2026-10-21T0315Z.sql.gz.age` (26 656 bytes encrypted, 271 156
bytes plain; about 11 hours old, the only file in `dumps/`). Target: throwaway `postgres:18`
container, never the production database. Plain dump deleted afterwards.

## Steps and timings

| Step | Time |
|---|---|
| Download via `gh api` (raw) | about 1 s |
| `age -d` + `gunzip` | under 1 s |
| Container start until ready | about 6 s |
| Load dump with `psql` | under 1 s (0.2 s on the clean path) |
| Create `ilm_app` and grants | under 1 s |
| Checks and metrics | about 1 s |

Total restore (decrypt to verified): well under a minute.

## Problems found

1. The dump has no owners or grants: `ilm_app` and its privileges must be recreated by hand.
2. `CREATE SCHEMA public` fails on a fresh database (schema exists), so `ON_ERROR_STOP` aborts;
   the documented one-liner did not mention it. Fix: `DROP SCHEMA public` first.
3. The old text said "on an empty database" and gave no role/grant step.

`docs/ops/deploy.md` (Backups) now has the full verified procedure. Re-run with
`ON_ERROR_STOP=1` on the clean path: exit 0.

## Verification

`alembic_version` = `0011` (head). Metrics ran as `ilm_app` in a read-only transaction
(`education_summary`, `finance` from `app.metrics`): totals computed without error.

| Table | Rows |
|---|---|
| app_user | 8 |
| student | 24 |
| cohort | 6 |
| lesson | 202 |
| enrollment | 36 |
| attendance | 844 |
| payment | 71 (65 confirmed, 6 pending) |
| instructor_payout | 10 |
| lead | 24 |
| campaign | 4 |
| audit_log | 13 |

Confirmed payments sum: 35 900.00. Metrics: income 35 900.00, payroll 15 000.00, ads 4 000.00,
profit 16 900.00; 6 cohorts (2 active), 24 active students.

Expected from the real import (students 837, enrollments 881, attendance 5990, payments 624,
confirmed 351 946.07) does NOT match: all 24 students have ids in the reserved demo range
`de000000-...`, so this backup holds only the demo dataset. The real import has not reached
the production database yet. The restore mechanics are proven; the real-data counts are still
to be checked once the import is loaded and a new backup runs.
