# Deployment status

See the [root README](../README.md) and [deployment guide](../DEPLOYMENT.md) for current setup. Public production mode requires a separate `finflow_demo` database, verified database TLS, and server-side read-only mode. The existing local database is at revision `0003`. The phase notes below retain implementation history; no startup command applies migrations.

# FinFlow AI backend

## Multi-profile management (revision 0003)

Migration `0003_add_profiles.py` is additive: it creates profiles, inserts one
default My Profile, and associates existing transactions without changing their
original fields. It adds a non-null restricted foreign key and profile/id and
profile/date indexes. Downgrade refuses to discard profile information.
The existing local database was verified at revision `0003`. Nothing applies a migration automatically. Do not run migrations against `finflow_db`
until the owner separately approves the live migration and a backup is verified.

`GET/POST /api/profiles` list/create profiles. GET supports `include_archived`.
`PATCH /api/profiles/{id}` accepts `name` and/or `archived`; no deletion API exists.
The default profile can be renamed but cannot be archived.

Transaction lists, summaries, and assistant queries accept `profile_id` (a
positive profile ID or explicit `all`). Omission resolves to the default profile.
All includes archived profiles. Individual transaction GET/PUT/DELETE require a
concrete profile scope, defaulting to My Profile. POST accepts a concrete
`profile_id` in its body. PUT may include the same ID but cannot move a transaction.
Archived profiles are readable and cannot accept transaction mutations. Profile
rows are locked for writes so archiving serializes against transaction changes.

Filtering applies before pagination, currency conversion, aggregation, and
month comparisons. Reporting responses and assistant answers identify scope.
Only dates/currency pairs go to the existing rate provider. No authentication or
accounts exist: these are profiles within one trusted local workspace, not
access-control boundaries. No new login system is introduced.

At revision 0002, unscoped existing operations remain available through a
compatibility mapping. Profile APIs and explicitly scoped requests return a
clear 409 migration-required response; no scoped request falls back to all data.

Normal tests use isolated SQLite schemas and deterministic mocked exchange rates.
The PostgreSQL tests require `FINFLOW_MIGRATION_TEST_DATABASE=finflow_restore_test`,
refuse the application database, and roll back schema/data changes. The restored
baseline remains revision 0001; tests upgrade it transactionally through 0002 and
0003. Profile migration tests verify every original field, constraints/indexes,
interrupted-migration rollback, and real PostgreSQL API isolation.

For development, prefer the checkout-specific launcher:

```powershell
cd C:\Users\katta\finflow-ai\backend
.\.venv\Scripts\python.exe run_dev.py
```

It starts port 8000 from the correct backend directory, explicitly watches `app/`,
and enables polling when no polling preference is already set. This avoids an
older Uvicorn process continuing to serve a previous Pydantic schema after edits.
If a currency request returns `currency: Extra inputs are not permitted`, inspect
the running `/openapi.json`: `TransactionWrite.properties.currency` must contain
USD, INR and AED. A process without that field is stale or serves another checkout;
restart it with the launcher rather than removing currency or reapplying migrations.

The live server restarted during this repair writes diagnostics to the Git-ignored
`backend/.runtime/` folder. No database credentials are written by the launcher.

Use Python 3.13. From `backend` in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Keep local credentials in `backend/.env` using the keys in `.env.example`.
Set `DB_NAME=finflow_db`; the database must already exist. Process environment
variables override `.env`. Never commit credentials. Connections use Psycopg,
SQLAlchemy sessions, a five-second connection timeout, and hidden SQL parameters.

Existing `/` and `/api/health` endpoints remain unchanged. Health is a static
liveness response, not a database readiness probe. Interactive API docs: `/docs`.

## Transactions

POST and GET `/api/transactions`; GET, PUT and DELETE `/api/transactions/{id}`.
GET list accepts `offset` (default 0) and `limit` (default 50, maximum 100),
ordered by ascending ID. PUT requires all editable fields.

Example POST/PUT body:

```json
{"description":"Groceries","amount":"42.75","category":"Food","transaction_type":"expense","transaction_date":"2026-11-12"}
```

Amounts are positive decimal values with at most 12 integer digits and two
fractional digits; responses serialize them as strings to preserve precision.
Types are `income` or `expense`. IDs and creation timestamps are server generated.
Validation failures return 422, absent records 404, and database failures a
sanitized 503. Failed writes roll back. `created_at` uses PostgreSQL timezone-aware
timestamps. No authentication is implemented; use locally until access control is added.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

API tests use a fresh isolated in-memory SQLite database per test and never
access or clear `finflow_db`. They cover CRUD, validation, missing records,
pagination, existing endpoints, and sanitized database failures. PostgreSQL
migrations and PostgreSQL-specific behavior need separate integration validation.

Run `alembic revision --autogenerate -m "description"` for future schema changes
and review the migration before applying it. Tables are never created automatically
at server startup. The initial migration creates only `transactions` and Alembic's
version table; it does not delete existing tables.

Before the first migration, inspect the existing database tables, constraints,
and Alembic version state using read-only queries. Apply
`alembic upgrade head` only after confirming the existing schema is compatible.
If a transactions table already exists or migration history differs from this
project, reconcile the schema and migration history before proceeding; do not
drop tables, clear data, or blindly stamp a revision. A failed authentication
attempt prevents inspection and migrations; correct credentials locally without
sharing them in logs or chat.

## Phase 3: read-only summaries and local assistant

No additional packages, database tables, or migrations are required. Existing
transaction, root, and health endpoints remain unchanged.

`GET /api/summary` accepts optional ISO `start_date` and `end_date` query
parameters, inclusive. Invalid dates, reversed ranges, and unknown parameters
return 422. With no dates, all recorded transactions are included, including
future-dated entries. The response contains decimal-string `income`, `expenses`,
`net_balance`, transaction count, ranked `spending_by_category`, `monthly_trends`,
and deterministic `insights`. Monetary values have two fractional digits.
Original decimal amounts are converted and rounded individually, then summed with
Python Decimal arithmetic; floating-point monetary calculations are never used. Category shares and change percentages use half-up
rounding to two decimal places; rounded category shares may not sum to exactly 100.

The service issues one data SELECT of dates, categories, types, original amounts and currencies. It does not load
descriptions, IDs, or creation timestamps. Monthly trends list only months with
recorded transactions; they do not fabricate observations for missing months.
`partial_months` indicates that a selected boundary is partial or that the range
includes the current incomplete month. USD is the default reporting currency. USD, INR and AED originals are supported
after migration 0002; schema 0001 remains compatible as USD-only storage.

Month-over-month insights compare the last two complete calendar months, based
on America/Chicago's current date. A historical end date moves that comparison
back to the latest complete month at or before it. Comparison months are whole
months and intentionally ignore `start_date`; they can extend outside the
selected summary range. A current/future end date never compares the incomplete
current month. Missing months have zero recorded totals and explicit record
counts; this cannot distinguish no activity from unrecorded activity. A zero
previous total yields `null` percentage change instead of division by zero.

`POST /api/assistant/query` accepts a JSON `query` (1–500 nonblank characters)
and optional `start_date`/`end_date`. It is a read-only operation despite using
POST. The response includes `provider: "rule_based"`, a status (`answered`,
`no_data`, or `unsupported`), a message, and the aggregate summary when relevant.
Supported example questions:

- What are my total expenses?
- Summarise my finances / summarize my finances
- Give me a financial summary
- How much did I spend this month?
- How much did I earn last month?
- What is my net balance?
- What is my biggest spending category?
- How did expenses change last month?
- How did income change last month?

Financial-summary questions accept both British and American spelling, bare
“summarise” / “summarize”, and variations such as “show me a financial summary”
or “give me a summary of my finances”. Answers include income, expenses, net
balance, the top three spending categories, the reporting period and record
count, all supplied by the existing summary service. Empty periods return
`no_data` with zero recorded totals and a clear missing-data explanation;
income-only periods explain that no expenses were recorded. Missing transactions
are never inferred. The dashboard's all-time view and an unfiltered assistant
summary use the same transaction dataset. For monthly parity, use matching full
month start/end dates; a natural-language “this month” query instead stops at
today, so future-dated entries in that month are excluded.

Relative “this month” means month-to-date, and “last month” means the previous
complete calendar month. Use either explicit date controls or relative phrases;
combining them is rejected as unsupported to avoid ambiguous answers. Unknown
questions, unsupported qualifiers (including category-specific queries), multiple
intents, arbitrary years, forecasts, and write requests return guidance without
guessing. This is English phrase matching, not a general language model or advice.

The `AssistantProvider` protocol receives only an intent and validated aggregate
summary; it cannot access the database session, credentials, or individual rows.
The only configured implementation is local `RuleBasedProvider`. There are no
external HTTP/LLM calls, credentials, telemetry, or chat persistence. Any future
external provider requires an explicit separate implementation and approval of
its aggregate data contract; never pass database configuration or raw records.

Tests in `tests/test_financial.py` cover aggregates, decimal precision, inclusive
dates, partial and missing months, percentage rounding, zero baselines, natural
language boundaries, read-only SQL behavior, and sanitized database failures.
They use isolated SQLite data; real PostgreSQL integration is checked separately
using read-only transactions, without seeding or changing production records.

## Phase 4 migration safety checkpoint

Revision `0002` adds `transactions.currency` (`VARCHAR(3) NOT NULL DEFAULT 'USD'`)
with a USD/INR/AED check constraint. Existing amounts and all other fields stay
unchanged. Downgrade removes only this new column/constraint, and refuses to run
if any non-USD currency information would be lost. Neither direction drops a
table or resets transaction data. A five-second lock timeout bounds lock waits.

Historical phase-4 checkpoint: `finflow_db` was at revision **`0002`**, following explicit approval,
backup verification, and isolated upgrade/downgrade tests. Its original USD
transaction and amount were verified unchanged. Application models and UI support
both schemas: installations still at 0001 retain USD-only writes and return 409
for non-USD saves. Migration creation/test execution never applies production
migrations automatically; future database changes still require approval.

Migration integration tests require explicit opt-in and accept only the database
named `finflow_restore_test`, which must differ from the configured application
database. They expect the verified restored baseline: one transaction and revision
`0001`. They run actual PostgreSQL upgrades, downgrades, constraint checks, and
INR/AED rollback guards inside transactions that are always rolled back, leaving
the restored database at its original baseline. Temporary rows use explicit
negative IDs so sequence values are not advanced.

From `backend`, run the opt-in checks without changing `.env`:

```powershell
.\.venv\Scripts\python.exe -c "import os, pytest; os.environ['FINFLOW_MIGRATION_TEST_DATABASE']='finflow_restore_test'; raise SystemExit(pytest.main(['tests/test_currency_migration.py','-q']))"
```

Normal test runs skip these PostgreSQL checks unless explicitly enabled.


## Phase 4 application features (introduced at revision 0002)

No migration runs automatically. At the phase-4 checkpoint, the explicitly approved `0002` migration had
been applied to `finflow_db`. Application storage inspects the PostgreSQL schema per
session, uses USD-only compatibility mapping at 0001, and automatically uses the
currency column at 0002. Original `amount` and `currency` are never rewritten by
reporting. POST defaults omitted currency to USD; PUT preserves currency when
omitted. Invalid codes are rejected. Non-USD writes at schema 0001 return 409.

The summary query and assistant JSON accept `reporting_currency` (USD/INR/AED,
default USD) and `rate_policy` (historical/latest, default historical). Transaction
lists optionally accept the same parameters to include `converted_amount`,
`reporting_currency`, `conversion` evidence, or a `conversion_error`; the original
amount/code remain unchanged. Plain transaction reads work even when FX is down.
`GET /api/exchange-rates?base=USD&quote=INR` returns latest rates; add
`rate_date=2026-10-30` for historical rates. Frontend components never contact
Frankfurter directly.

Only pairs and dates go to https://api.frankfurter.dev/v2. HTTPX parses rates as
Decimal. Every transaction is multiplied and rounded half-up to two fractional
digits before aggregating categories, trends, balances and comparisons. All
three supported currencies have two fractional minor-unit digits. Each lookup
returns requested date, actual publication date, fetched timestamp, source,
and cache status. Identity conversions are exactly 1 and make no HTTP call.

Historical rates must be on or before the transaction date, within seven days;
404s look back at most seven days. Future historical conversions are refused
unless no exchange is necessary; choose latest valuation explicitly for future
transactions. Latest results must be within seven days of the current UTC date.
The API is a reference-rate service, not bank settlement or trading quotes.

The bounded process-local cache holds up to 2048 keys: latest TTL one hour,
historical blended TTL 24 hours, failures 30 seconds. Requests are deduplicated
under a bounded lock. Each upstream call times out within five seconds, and each
report/list page has a 12-second lookup budget. A cold large history may exceed
this budget: retry after cached lookups warm up; no partial totals are returned.
Cache contents reset on restart and are not shared among worker processes.
Historical blended rates can be revised by the provider after cache expiry.

Missing or invalid required rates yield a sanitized 503 for summaries/assistant;
original transaction lists remain usable with explicit missing-conversion markers.
No fabricated rate, automatic latest substitution, hardcoded AED peg, or silent
exclusion of transactions is allowed. A report includes actual rate evidence;
conversion policy and dates appear in assistant answers and UI reporting notices.

`tests/test_multicurrency.py` covers mocked provider contracts, precise rounding,
cache expiry, failed rates, schema-0001 compatibility, currency validation and
cross-feature totals. `tests/test_currency_application_postgres.py` adds real
PostgreSQL CRUD/report/assistant checks using the existing opt-in isolated fixture,
transactional test defaults (no serial-sequence increments), and full rollback.
Run all backend tests including isolated integration tests from `backend`:

```powershell
.\.venv\Scripts\python.exe -c "import os, pytest; os.environ['FINFLOW_MIGRATION_TEST_DATABASE']='finflow_restore_test'; raise SystemExit(pytest.main(['tests','-q']))"
```

HTTPX is now declared as an application dependency (it was already installed for
testing). There are no paid services, provider keys or external LLM calls.
