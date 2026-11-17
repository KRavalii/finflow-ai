# Public-demo deployment guide

## Current status (November 16, 2026)

The separate Supabase cloud demo is initialized at revision `0003`, with three
profiles and 17 fictional transactions. The `finflow_reader` login was created
and verified through a separate TLS-verified session-pooler connection. It can
SELECT only the three FinFlow tables, has no effective persistent-data write,
permanent creation, administration, ownership, membership, sequence, or sensitive
schema privileges, and retains inherited TEMPORARY permission as approved.
Shared PUBLIC permissions and existing roles were not changed.

Local production-mode API checks using that runtime role passed: health,
readiness, profiles (including archived), transactions, historical summaries,
exchange rates, assistant, representative CORS checks, and 403 write protection.
These checks do not establish hosted Render/Vercel behavior or the final CORS origin.

Render service creation, credential transfer, repository publication, and deployment
have not been performed and require separate approval. Do not reuse or migrate
the existing local `finflow_db`. Do not upload backups, real records, or
`backend/.env`. The database setup instructions below are for a NEW project;
**do not rerun initialization or role creation against the existing demo**.

## Primary layout: Supabase, Render, then Vercel

All resource creation, cloud initialization, commit/push, and deployments require
separate owner approval. The configuration files are preparation, not deployment.
The public production launcher requires read-only demo mode. Local mode remains
editable and uses the existing `.env`; do not overwrite it with production values.

### 1. Supabase: dedicated fictional demo project

1. After approval, create a **new dedicated Supabase project**, near the intended
   Render region. The database is `postgres`; naming the project `finflow_demo`
   does not rename its database. Never use a project containing personal data.
2. Disable the unused Data API for this project. FastAPI connects to PostgreSQL
   directly; no Supabase client, publishable key, or service-role key is needed.
3. Copy the actual **Session pooler** connection parameters from Connect. Use
   port `5432`, not transaction-pooler port `6543`. Copy the pooler hostname;
   do not infer it from the region. The setup username is `postgres.<project-ref>`;
   the later runtime username is `finflow_reader.<project-ref>`.
4. Obtain the trusted database CA certificate if system roots do not verify the
   endpoint. Keep `sslmode=verify-full`; do not weaken certificate verification.
   A direct `db.<project-ref>.supabase.co:5432` connection is also accepted when
   the setup machine has the required IPv6 access (or project IPv4 support).
5. In a fresh PowerShell setup session, securely enter the **cloud-only** setup
   URL below. URL-encode reserved password characters. Never put the real URL
   in command arguments, shell history, chat, a tracked file, or frontend variables.

Placeholder shape only:

```text
postgresql+psycopg://postgres.<project-ref>:<encoded-setup-password>@<session-pooler-host>:5432/postgres?sslmode=verify-full&sslrootcert=<trusted-CA-path-or-system>
```

From the repository root, **only after cloud database initialization approval**:

```powershell
cd backend
$demoCloudUrl = Read-Host 'Dedicated Supabase demo setup URL' -AsSecureString
$env:DEMO_DATABASE_URL = [System.Net.NetworkCredential]::new('', $demoCloudUrl).Password
try {
    .\.venv\Scripts\python.exe -B prepare_demo.py --confirm-database postgres --confirm-supabase-project <project-ref>
    if ($LASTEXITCODE -ne 0) { throw 'Demo initialization refused or failed.' }
} finally {
    Remove-Item Env:DEMO_DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Variable demoCloudUrl -ErrorAction SilentlyContinue
}
```

Replace `<project-ref>` with the exact 20-character lowercase project reference.
The URL is held in the process environment for this command, not echoed. The
initializer reads **only** `DEMO_DATABASE_URL`, never local `DB_*` or `.env`.
It matches the confirmed database and project to the TLS hostname (and pooler
username), checks `current_database()`, refuses any existing public tables,
then migrates and seeds in one transaction. It never resets a database.
For a refusal, inspect the target and permissions; do not clear existing tables.

Migration chain: `0001` transactions -> `0002` original currencies -> `0003`
profiles. The initializer inserts 17 fictional transactions across three profiles
from `backend/demo_data.json`. Do not run `alembic upgrade head` separately first:
the initializer requires an empty public schema. Never run ordinary Alembic
commands with the local `.env` to initialize the cloud project. No migration
or seed runs during application build or startup.

6. Using the provider's secure role tooling, create a login `finflow_reader`
   with its own password, no owner membership and no elevated role attributes.
   Grant only CONNECT on `postgres`, USAGE on `public`, and SELECT on
   `public.profiles`, `public.transactions`, and `public.alembic_version`.
   Verify effective permissions: no schema CREATE, INSERT, UPDATE, DELETE,
   TRUNCATE, sequence access, ownership, or inherited writable membership.
   `default_transaction_read_only=on` is useful defense in depth. A read-only
   default alone is not a substitute for restricted grants. Keep setup credentials
   out of the Render service.

   For the existing demo, this role is already verified. Shared TEMPORARY remains
   inherited; do not revoke shared PUBLIC grants. The read-only guarantee applies
   to persistent FinFlow data and does not remove temporary-table permission.

### 2. Render: native Python backend

After approved repository publication, create a Python Web Service with:

| Setting | Value |
| --- | --- |
| Root directory | `backend` |
| Build command | `python -m pip install -r requirements.lock` |
| Start command | `python run_prod.py` |
| Health check | `/api/readiness` |
| Auto-deploy | Disable if each release requires approval |

Use the native Python runtime, not the root Dockerfile, for this split layout.
Production startup requires the exact runtime username: `finflow_reader.<project-ref>`
for Supabase session pooling, or `finflow_reader` for direct/other hosting.
Administrator accounts and other usernames are rejected before serving requests.
This guard does not change development settings or the explicit setup initializer.
Configure these values in Render's environment/secrets UI, not a committed file:

```dotenv
PYTHON_VERSION=3.13.5
APP_ENV=production
FINFLOW_DEMO_MODE=true
FINFLOW_SERVE_FRONTEND=false
FINFLOW_SUPABASE_PROJECT_REF=<project-ref>
DB_HOST=<copied-session-pooler-host>
DB_PORT=5432
DB_NAME=postgres
DB_USER=finflow_reader.<project-ref>
DB_PASSWORD=<read-only-runtime-password>
DB_SSLMODE=verify-full
DB_SSLROOTCERT=/etc/secrets/supabase-ca.crt
CORS_ORIGINS=https://<frontend-project>.vercel.app
```

Upload the same trusted CA that passed local verification as Render Secret File
`supabase-ca.crt`, available at `/etc/secrets/supabase-ca.crt`. System trust failed
in the earlier local check; retain the verified CA and `sslmode=verify-full`.
Keep certificate files outside the repository. Git/Docker ignore rules also
exclude `.pem`, `.crt`, and `.cer` files and the private `.runtime` directory.
Do not upload backend/.env. Render supplies
`PORT`; the production launcher binds `0.0.0.0` on that port without reload.
If the final Vercel origin is unknown, leave CORS empty for the initial API checks
and update it in step 3 before testing the browser. No wildcard is permitted.
The Supabase project reference is explicit target confirmation, not a secret.

The runtime password is stored locally only in
`backend/.runtime/finflow_reader.password.dpapi`, encrypted with Windows DPAPI
for the current Windows user. It cannot be used directly by a Linux cloud host.
After separate credential-transfer approval, a local helper can decrypt it only
in memory and send it directly over verified HTTPS to Render's environment API
as `DB_PASSWORD`, using a Render API token entered through masked private input.
Do not print request/response bodies, authorization headers, passwords, or tokens;
report status only. Do not export a plaintext `.env`, use the clipboard, upload
the DPAPI file, or include credentials in shell arguments, Git, or chat. Transfer
tooling has not been executed or authorized by local preparation approval.

Require HTTP 200 from `/api/health` and `/api/readiness`; readiness must report
`demo_mode: true`. `/api/config` must return `{"demo_mode":true}`. Check
`/api/summary` and a historical exchange-rate request. Allow outbound HTTPS to
`api.frankfurter.dev`; failed rates intentionally hide totals with a 503 rather
than inventing data. The Axios timeout is 15 seconds; sleeping services can
require warming the API and retrying the first frontend request.

### 3. Vercel: React/TypeScript frontend

After deployment approval, import the approved repository revision:

| Setting | Value |
| --- | --- |
| Framework | Vite |
| Root directory | `frontend` |
| Node | Node 22.15.1+ on the 22 line, or Node 24 |
| Install command | `npm ci` |
| Build command | `npm run build` |
| Output directory | `dist` |

Set `VITE_API_BASE_URL=https://<render-service>.onrender.com/api` and
`VITE_DEMO_MODE=true` before the production build. These are public build-time
values; rebuild after changes. Never add database credentials or Supabase keys.
`frontend/vercel.json` supplies the SPA fallback for direct page navigation.
`API_PROXY_TARGET` is only for Vite dev/preview, not production.

Set Render `CORS_ORIGINS` to the actual stable Vercel HTTPS origin with **no
trailing slash**. Multiple explicitly approved origins can be comma-separated;
preview URLs are not automatically allowed. Apply the Render environment update,
then test from the real production frontend. CORS is not authentication.

Before sharing, follow the verification checklist below, including all currencies,
the assistant, direct SPA routes, and server-side 403 write protection. Do not
perform write probes against the editable local server. Confirm the production
link works signed out. The stable Vercel URL is the link for LinkedIn and the README.
Choose All time or August-October 2026 for the fixed fictional fixtures; relative
date questions may legitimately find no records. Review current hosting quotas
and plan terms; no free-tier availability or performance guarantee is implied.

Provider references: [Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[Supabase API security](https://supabase.com/docs/guides/database/secure-data),
[Render Python versions](https://render.com/docs/python-version),
[Render FastAPI](https://render.com/docs/deploy-fastapi),
[Vercel Vite/SPA routing](https://vercel.com/docs/frameworks/frontend/vite).

## Alternative: existing finflow_demo database and combined Docker hosting

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

### Initialize ONLY a new fictional finflow_demo database

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

### Same-origin production build

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
DB_USER=finflow_reader
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

### Other separate React/Vite and FastAPI hosts

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

The hosted database, migrations, fictional seed, and runtime role are complete
and locally verified. No repository publication, Render service creation,
credential transfer, or application deployment has been performed. Docker/Linux
build, Render-to-Supabase TLS and egress, actual frontend CORS, HTTPS health checks,
and free-tier behavior still require validation on the chosen hosts. Local tests
do not establish these. Production enforces the runtime username, but effective
database permissions must continue to be checked when roles or grants change.
Caches are in memory per worker and reset on cold starts. No background job,
external LLM credential, or persistent local disk is needed.

Local development remains editable and unauthenticated. Never expose it by
tunneling, binding publicly, or publishing a development launcher. Production
intentionally refuses `FINFLOW_DEMO_MODE=false`; authenticated public editing
would need a separate security design rather than relaxing that check.
