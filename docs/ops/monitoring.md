# Monitoring

Errors go to Sentry (free plan), outages are caught by GitHub Actions. The database holds real
personal data, so the rule is: **send as little as possible, scrub the rest, and never put a DSN
or token in the repo.**

## Switches (environment only)

| Where | Variable | Effect |
|---|---|---|
| Render (API) | `SENTRY_DSN` | set = API reports errors; empty/absent = Sentry is off (dev, tests) |
| Vercel (web) | `NEXT_PUBLIC_SENTRY_DSN` | set = browser + server report errors; absent = off, the SDK is not even loaded |
| Vercel build | `SENTRY_AUTH_TOKEN` (+ `SENTRY_ORG`, `SENTRY_PROJECT`) | optional: uploads source maps at build; without it nothing is uploaded |

Release = the deployed commit (`RENDER_GIT_COMMIT` for the API, the same value `/api/health`
reports; `VERCEL_GIT_COMMIT_SHA` for the web). Environment = `production`.

## What is sent

Unhandled exceptions with their stack trace (function names, file, line), the request method and
path, the release, browser/OS names, and a few breadcrumbs (navigation, fetch/XHR as method + path +
status). Performance traces are sampled at 2 % (limit 5 %). **Not used:** Session Replay, the
feedback widget, profiling, user feedback, local variables, request/response bodies.

Never reported: expected client errors (API 4xx: 401/403/404/409/422/428, `DomainError`,
validation errors).

## Scrubbing

Applied in the SDK `before_send` / `beforeSend` (API: `app/core/monitoring.py`, web:
`src/lib/monitoring.ts`), so the data never leaves our servers or the browser unscrubbed. Both
sides have unit tests with fake personal data.

- Request bodies, cookies: removed. Query strings: parameter names kept, values `[Filtered]`;
  URLs reduced to path.
- Headers: only `accept`, `accept-language`, `content-length`, `content-type`, `host`,
  `user-agent`. No `Authorization`, `Cookie`, client address, proxy secret.
- User: only the internal user id; no login, name, e-mail, address.
- Breadcrumbs: no console output, no DOM/click/input breadcrumbs, no SQL; fetch URLs keep the
  path only.
- Any string containing a phone number (9+ digits in any format) or an e-mail address is replaced
  with `[Filtered]` (exception messages, log messages, tags).
- Names: every Cyrillic word (also percent-encoded in a URL) is `[Filtered]`; code, SQL and log
  text are English, so this only hits personal data. Latin-spelled names are not detected.
- Database errors: the engine runs with `hide_parameters=True`, and the scrubber also replaces
  `[parameters: …]`, `Failing row contains (…)`, `Key (col)=(…)` and `input_value=…`.
- Any `?query` inside a string (span descriptions, trace data) is cut; `http.query`-style
  attributes are `[Filtered]`.
- Stack-frame local variables, `server_name`, `extra`: removed.

## Browser tunnel `/monitoring`

The browser posts to our own origin so the strict CSP (`connect-src 'self'`) stays untouched and
ad blockers do not drop events. The route (`src/app/monitoring/route.ts`) is public (an error can
happen before login) and forwards an envelope only if its header names exactly our
`NEXT_PUBLIC_SENTRY_DSN`; the target is rebuilt from that DSN and must be under `.sentry.io`.
Limits: 200 KB per request (counted in bytes while streaming, also without a content-length), 30
requests/min per client address (`x-vercel-forwarded-for`, per server instance), everything else
gets 400/413/429. Only the envelope goes upstream: no cookie, auth or forwarding header. A global
cap is not needed: the DSN is public in the bundle, so anyone can post to Sentry directly anyway;
the tunnel adds no reach beyond our own project. The browser SDK is loaded through
`src/lib/sentry-browser.ts` with named imports only, so Session Replay and the feedback widget are
not in the bundle.

## Error boundaries

`src/lib/report-error.ts` exports `reportError(error)`; call it from `error.tsx` /
`global-error.tsx` in a `useEffect`. It loads the SDK lazily and does nothing without a DSN.

## Where alerts go

- Sentry: the project's default issue alert e-mails the project owner on a new issue. Add rules
  in Sentry (Alerts) if more people should get them.
- Uptime: `.github/workflows/uptime.yml` checks `/api/health` through Vercel every 2 hours
  outside 03:00-15:59 UTC (00, 02, 16, 18, 20, 22); `keepalive.yml` does it every 10 minutes
  inside (it also keeps Render awake). A non-200 or no answer in 90 s fails the run and GitHub
  e-mails the repository owner (Settings -> Notifications -> Actions: failed workflows).

## Rotating the DSN

1. Sentry -> Project settings -> Client keys: create a new key, keep the old one enabled.
2. Set the new DSN in Render (`SENTRY_DSN`, redeploy) and Vercel (`NEXT_PUBLIC_SENTRY_DSN`,
   redeploy: it is inlined at build time).
3. After both are live, disable and delete the old key.

A DSN only lets someone *send* events; if it leaks, rotate it and enable "allowed domains" /
rate limits on the key. Rotating `SENTRY_AUTH_TOKEN`: create a new token (scope `project:releases`,
`org:read`), replace it in Vercel, revoke the old one.
