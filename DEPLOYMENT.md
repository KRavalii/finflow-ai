# Public-demo deployment guide

Preparation only: these instructions have not been executed against a hosted
database or hosting account. Do not reuse or migrate the existing local
`finflow_db`. Do not upload backups, real records, or `backend/.env`.

## Recommended free-tier layout

Use an external Neon Free PostgreSQL project with a **new database named
`finflow_demo`**, plus one Render Free Docker web service. The Docker image builds
the Vite frontend and serves it from FastAPI, so `/api` stays on the same HTTPS
origin and no CORS entries are needed. No frontend static-host account is required.

As checked November 14, 2026, [Neon Free](https://neon.com/pricing) offers a
quota-limited free plan without a time limit. [Render Free](https://render.com/docs/free)
supports Docker web services, sleeps after 15 idle minutes, and has usage limits.
Cold starts can delay the first visit. Render's own free PostgreSQL expires after
30 days, so it is not the recommended persistent demo database. Review current
terms and keep free plans/usage caps selected; this guide does not guarantee
unlimited hosting or create any accounts/resources.

## 1. Initialize ONLY the new fictional demo database

Create `finflow_demo` in a separate project, with an owner/setup role. Use the
provider's direct database endpoint for initialization. Put a URL in the
**process environment**, using your secret manager or an interactive secure
entry; do not commit it, paste it into shell history, or put it in command-line
arguments. URL-encode reserved characters in credentials.

Expected shape (placeholders only):

```text
DEMO_DATABASE_URL=postgresql+psycopg://<setup-user>:<encoded-password>@<host>:5432/finflow_demo?sslmode=verify-full&sslrootcert=system
```

If system roots are unsuitable, use the provider's trusted CA file as
`sslrootcert`. Never disable certificate or hostname verification.

From `backend`, with the production lock installed:

```text
python prepare_demo.py --confirm-database finflow_demo
```

The initializer requires the exact demo database name and verified TLS, reads
only `DEMO_DATABASE_URL`, checks the actual database name, and refuses an existing
public schema containing tables. It applies existing migrations through `0003`
and inserts 17 fictional transactions across three profiles in one transaction.
Reruns refuse rather than update, reset, or duplicate records. There is no
auto-seed at build/startup. Remove `DEMO_DATABASE_URL` from the environment afterward.

The fixtures use fixed August–October 2026 dates, fictional descriptions, and
USD/INR/AED originals. Choose All time or those months to explore them; relative
assistant questions use the real current date and may legitimately have no data.
Historical rates still come from Frankfurter; no exchange rates are fabricated.

Create a separate runtime login using the provider's secure role tooling with
CONNECT on `finflow_demo`, USAGE on `public`, and SELECT on `profiles`,
`transactions`, and `alembic_version` only. Do not grant owner membership,
CREATE, INSERT, UPDATE, DELETE, sequence privileges, or schema ownership. Use
this login for the application, keep the setup login out of runtime secrets, and
verify effective privileges. `default_transaction_read_only=on` for the runtime
role is useful defense in depth. All API reads and the assistant work without
write privileges.

## 2. Same-origin production build (recommended)

The root Dockerfile uses Node 22 to run `npm ci` and build the frontend with
`VITE_DEMO_MODE=true` and `VITE_API_BASE_URL=/api`. Its final non-root Python 3.13
image installs `backend/requirements.lock` and starts `backend/run_prod.py`.
The image excludes local environment files, backups, and databases.

After separately reviewing and publishing your repository yourself, create a
Render web service using Docker and the repository root Dockerfile. Select the
Free instance type, disable automatic deploys if you want manual release control,
and configure these server-side environment values in the hosting dashboard:

```dotenv
APP_ENV=production
FINFLOW_DEMO_MODE=true
FINFLOW_SERVE_FRONTEND=true
CORS_ORIGINS=
DB_HOST=<provider-host>
DB_PORT=5432
DB_NAME=finflow_demo
DB_USER=<read-only-runtime-user>
DB_PASSWORD=<runtime-password>
DB_SSLMODE=verify-full
DB_SSLROOTCERT=system
```

Do not commit a filled-in file. The host supplies `PORT`; the launcher binds
`0.0.0.0` without reload. Set the health-check path to `/api/readiness` after
initializing the demo database. FastAPI serves `/`, `/transactions`, `/analytics`,
and `/assistant` with the SPA entry point and `/assets` as static files. Unknown
API paths return 404 rather than HTML. TLS terminates at the hosting provider.

For an optional local container build (no database changes):

```text
docker build -t finflow-demo .
```

Run only with separate demo secrets supplied securely. Starting the image without
the required demo settings fails; it never initializes a database.

## 3. Alternative: separate React/Vite and FastAPI hosts

For a static frontend host such as Render Static Sites:

- Root directory: `frontend`.
- Node runtime: Node 22 (22.15.1+) or Node 24.
- Build command: `npm ci && npm run build`.
- Publish directory: `dist`.
- Build environment: `VITE_DEMO_MODE=true` and
  `VITE_API_BASE_URL=https://<backend-host>/api`.
- Configure an SPA rewrite from `/*` to `/index.html` (status 200), after any
  provider-specific API proxy rules. Rebuild when `VITE_*` values change.

For a native Python backend service:

- Root directory: `backend`; runtime Python 3.13.
- Build command: `python -m pip install -r requirements.lock`.
- Start command: `python run_prod.py`.
- Set the server values above, except `FINFLOW_SERVE_FRONTEND=false` and
  `CORS_ORIGINS=https://<exact-frontend-host>` with no trailing slash.
- Use `/api/readiness` for readiness monitoring.

The API URL must use HTTPS; no secret belongs in a `VITE_*` variable. CORS permits
specified browser origins but is not authentication. The server's demo write
guard applies even to direct requests without an Origin header.

If your static host supports a same-origin reverse proxy, route `/api/*` to the
backend while preserving `/api`, place that rule before the SPA fallback, and
build with `VITE_API_BASE_URL=/api`. `API_PROXY_TARGET` in `vite.config.ts` only
affects Vite dev/preview; it is not a deployed proxy configuration. See the
provider's routing documentation before selecting this alternative.

## 4. Verification before sharing

- Confirm `/api/health` and `/api/readiness` return 200; readiness reports demo mode.
- Confirm `/api/config` returns `{"demo_mode":true}` and the UI labels fictional,
  read-only data with disabled transaction editing and no profile manager.
- Verify profiles, charts, filtering, all supported currencies, and the read-only
  assistant. Browse directly to all SPA routes to check rewrites.
- With an intentionally invalid body such as `{}`, verify POST/PUT/PATCH/DELETE
  to transaction/profile endpoints return **403**, not validation errors or 2xx.
  Do not test destructive requests against local mode. Ensure no writable
  alternate backend instance is exposed.
- Verify a historical lookup through the actual backend runtime:
  `/api/exchange-rates?base=USD&quote=AED&rate_date=2026-10-09`.
- Verify historical summaries through the frontend's actual API route:
  `/api/summary?reporting_currency=AED&rate_policy=historical&profile_id=1`.
- Check startup/request logs privately for TLS, schema, or upstream failures.
  Never log connection URLs or credentials. If rates are unavailable, repair
  connectivity or provider availability; do not substitute latest rates.
- Keep PostgreSQL publicly inaccessible where supported, or enforce verified TLS
  and provider access restrictions. Configure platform rate limits and usage
  caps where available; the app has no distributed request limiter.

## Known limits and next steps

No hosting account, hosted DB, migration, seeding, push, or deployment has been
performed as part of preparation. Hosted PostgreSQL setup, effective read-only
role permissions, Docker/Linux build, TLS, CORS, egress, and free-tier behavior
must be validated on the chosen host. Local unit tests do not establish these.
Caches are in memory per worker and reset on cold starts. No background job,
external LLM credential, or persistent local disk is needed.

Local development remains editable and unauthenticated. Never expose it by
tunneling, binding publicly, or publishing a development launcher. Production
intentionally refuses `FINFLOW_DEMO_MODE=false`; authenticated public editing
would need a separate security design rather than relaxing that check.
