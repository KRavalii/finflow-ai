# Deployment status

See the [root README](../README.md) and [deployment guide](../DEPLOYMENT.md) for current setup. Public builds set `VITE_DEMO_MODE=true`; editing is disabled and the backend independently rejects writes. Local editing remains available. Use `npm ci` and the committed lockfile for reproducible installs.

# FinFlow AI frontend

## Financial profiles

The header selects My Profile (default), another profile, or explicit All Profiles
(including archived). Manage profiles creates custom names such as Mom, Dad,
Brother and Friends, renames profiles, and archives/restores without deleting
transactions. Archived and combined views are read-only. The default cannot be
archived. No additional login or account system is introduced.

Selection persists in `finflow.profile`; missing/archived saved selections fall
back to the default. Each transaction/report/assistant request sends backend
scope. Switching profiles cancels outstanding reads, clears previous results and
assistant conversations, and closes transaction dialogs. Original currencies and
amounts remain independent of reporting preferences.

Migration 0003 requires separate live-database approval. Until applied, profile
controls are disabled with a migration-pending notice, and existing finances
continue using the unscoped single-workspace API. No migration runs from the UI.

If the API says `currency: Extra inputs are not permitted`, keep the currency in
the request. This error means the running backend is serving an older request
schema when the checked-in schema already supports currency. The UI now explains
this case. Restart the backend from `backend` using
`.\.venv\Scripts\python.exe run_dev.py`, then retry; no migration reset is needed.

React + TypeScript + Vite, Tailwind CSS, React Router, Recharts and Axios.
All application records come from the existing FastAPI transaction endpoints.
There are no seeded or fallback financial records. Test fixtures are isolated
under `src/test` and are never imported by production code.

## Run locally (PowerShell)

Start the existing backend in one terminal:

```powershell
cd C:\Users\katta\finflow-ai\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal:

```powershell
cd C:\Users\katta\finflow-ai\frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. If dependencies are already installed, skip `npm.cmd ci`.
Using `npm.cmd` avoids PowerShell script execution policy restrictions.
Use a supported Node 22 release (22.15.1 or newer) or Node 24.

## Configuration

Defaults work locally without creating a frontend environment file:

```dotenv
VITE_API_BASE_URL=/api
API_PROXY_TARGET=http://127.0.0.1:8000
```

To customize, copy `frontend/.env.example` to `frontend/.env.local` and edit it.
Never copy backend database credentials into frontend files. All `VITE_*` values
are public and are embedded in the client build. Restart Vite after changing
environment variables; rebuild for changes to a production client.

The development and preview servers proxy `/api` to FastAPI, without changing
the backend or requiring CORS. An absolute `VITE_API_BASE_URL` must include the
API prefix, for example `https://your-api.example/api`; cross-origin access then
requires server-side CORS configuration. That backend change is not included.

## Pages

- `/`: income, expenses, net balance, recent transactions and real-data charts;
  choose all time or a specific transaction month.
- `/transactions`: description/category search, category/type/date filters,
  pagination, validated create/edit forms, and confirmed deletion.
- `/analytics`: monthly income versus expenses and category spending.

Every list page is fetched from FastAPI (`limit=100`, increasing `offset`) before
displaying totals or applying filters. List order is then newest transaction date
first, breaking ties by newest ID. Pagination and filters are currently performed
on the complete client-side dataset because the existing API has no search,
filter, count or aggregate endpoints. Very large datasets should eventually use
server-side filtering and aggregate APIs. Multi-page reads are not a server-side
snapshot, so concurrent external writes can require another refresh.

PUT sends all editable fields, as required by the current API. Failed mutations
keep the dialog and entered values. A successful mutation reloads transactions;
if that reload fails, the error state asks for a retry without repeating the write.

Amounts retain their original USD/INR/AED codes. Backend reporting converts each
transaction before aggregation; display formatting uses integer cents (`BigInt`).
Recharts requires numeric plotting coordinates; unusually large totals can exceed
floating-point plotting precision, while data tables and tooltips retain exact
decimal values. Dates are displayed without UTC date
shifts. Budgets, authentication and AI predictions remain outside this frontend scope.

## Verify and preview a build

```powershell
cd C:\Users\katta\finflow-ai\frontend
npm.cmd test
npm.cmd run build
npm.cmd run preview
```

Open http://127.0.0.1:4173 with FastAPI running. The build output is `frontend/dist`.
Tests use mocked API responses and never write to PostgreSQL. They cover exact
monetary totals, full API pagination, validation, filtering, loading/error/retry,
mutation forms, delete confirmation, and page navigation.

## Deployment

Serve `dist/` using an SPA fallback to `index.html` for `/transactions` and
`/analytics`. Configure the production web server to reverse-proxy `/api` to
FastAPI. Vite's development/preview proxy is not part of the static build.
This implementation is local only; it does not publish the project or change
PostgreSQL credentials, migrations, backend code, or existing transactions.

## Phase 3: AI Assistant

Visit `/assistant` or choose **AI Assistant** in the sidebar. The reporting
snapshot uses the new read-only `GET /api/summary` endpoint. Apply optional
inclusive start/end dates, or choose All time. Monetary strings are formatted
with the existing integer-cent utilities, including negative balances.

Choose **Summarize my finances** or type “summarise my finances”, “summarize my
finances”, or “give me a financial summary” for one answer covering income,
expenses, net balance, and top spending categories. Each answer states the
reporting period and explains missing records or a lack of expenses. Dashboard
and assistant filters are independent: select the same full-month range to
compare them, or leave both on all time. “This month” means month-to-date in the
assistant, while the dashboard month selector also includes any future-dated
transactions recorded within that month.

Ask one of the suggested questions or type a supported English question about
income, expenses, balance, top spending categories, or complete-month changes.
Questions go to the local FastAPI `/api/assistant/query` endpoint through the
existing Axios configuration and proxy. There is no paid model, external AI
request, or database credential in the frontend. The request contains only the
question and applied reporting dates; no cached transaction rows are sent.

Explicit date controls and relative phrases (“this month” / “last month”) cannot
be combined; clear the dates or remove the relative phrase. Monthly comparison
answers identify their exact months and can include a month before the selected
start date. No-data and unsupported answers are displayed as returned by the
deterministic service rather than generating invented financial claims.

Conversation history is limited to the last 20 messages in component memory;
it is not written to browser storage or the database and is cleared when leaving
the page. Failed questions are preserved for retry. Requests are cancelled on
navigation away. Summary retry, empty states, keyboard navigation, and chat
status announcements are included. The dashboard and analytics now use the same currency-aware backend summary
service as the assistant (updated in Phase 4).

No additional dependency installation or migration is needed. Use the same
backend/frontend run commands above, and rerun `npm.cmd test` and
`npm.cmd run build` for validation. Production SPA fallback must also include
`/assistant`.


## Phase 4 currencies

The shared header selects USD, INR or AED and historical conversion (default)
or explicitly labelled latest valuation. These preferences persist locally in
`finflow.currency` and `finflow.ratePolicy`; no transaction records or credentials
are stored as preferences. Currency locale defaults are en-US, en-IN and en-AE.
Formatting keeps exact integer cents, including Indian lakh/crore grouping and
negative balances. Browser floating-point numbers are used only as chart plotting
coordinates/axis ticks; totals, accessible data tables and tooltips use exact
backend decimal strings.

Dashboard and analytics fetch `/api/summary` for the selected full month or all
time. Assistant requests send the same reporting currency/policy. Explicit dates
must also match for comparisons: ?this month? is month-to-date, while a dashboard
full-month selection includes future-dated records (historical FX for future dates
is unavailable). Transactions retain original amounts/codes, show reporting
equivalents and rate dates, and never sum mixed originals when conversion is
missing. Filters/pagination still work on the loaded transaction list.

Create/edit forms select the original currency independently of the report
selector; editing shows original values, never converted amounts. Currency support was introduced at schema 0002. The existing local database is now at schema 0003.
Installations still at schema 0001 retain USD-only writes and return HTTP 409
for non-USD saves. Nothing applies a migration from the UI.

Rates come only through FastAPI. Missing required rates hide report totals and
offer retry instead of partial sums; raw originals remain readable. In-flight
loads are cancelled when preferences change, stale totals are hidden, and
assistant conversation history is cleared on currency/policy changes to avoid
mixing answers. Policy notices show actual publication dates and historical
fallbacks. See the backend README for cache TTLs and provider limitations.

Run as before, with no frontend package additions:

```powershell
cd C:\Users\katta\finflow-ai\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd C:\Users\katta\finflow-ai\frontend
npm.cmd run dev
```

Open http://127.0.0.1:5173. Run `npm.cmd test` and `npm.cmd run build` for the
frontend checks; `npm.cmd exec tsc -- -b` runs the standalone TypeScript check.
