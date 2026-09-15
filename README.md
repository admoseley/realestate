# Estella Wilson Properties — Deal Analysis

Internal tool for evaluating residential investment properties in Allegheny County, PA.
It parses sheriff-sale listings and single-property "spot checks", runs flip and
buy-and-hold analysis, and produces branded PDF reports that can be shared by email.

## Features

- **Sheriff sale analysis** — upload the county's sheriff-sale PDF; each property is
  enriched from public county data (Allegheny County assessments, WPRDC) and analyzed
  as a background job with live progress.
- **Spot check** — analyze a single address with optional overrides (FMV, sqft, beds…).
- **Deals dashboard** — persistent list of analyzed properties with thumbs up/down
  favorites, a Free & Clear filter, and inline address editing.
- **Reports history** — every run is saved with a downloadable branded PDF.
- **Share** — email one property or all favorites, with the PDF attached.

## Architecture

| Layer | Tech | Location |
|---|---|---|
| Frontend | React 19, Vite, Tailwind, React Router | `web/frontend` |
| API | FastAPI, SQLAlchemy, ReportLab, `pdftotext` (poppler) | `web/backend` |
| Analysis engine | Pure Python scripts shared by the API and CLI | repo root (`investment_analyzer.py`, `sheriff_sale_analyzer.py`, `spot_check.py`, `generate_pdf_report.py`) |
| Email | Resend | `web/backend/mailer.py` (the only module that sends mail), used by `web/backend/routers/share.py` |

> **Hosting migration in progress.** The app currently runs on Netlify (frontend) and
> Render (API). It is moving to Azure — Static Web Apps with Microsoft sign-in,
> Container Apps, Azure SQL, and Blob Storage — tracked in issues #2–#10.

## Local development

### Backend (Python 3.11)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r web/backend/requirements.txt -r web/backend/requirements-dev.txt
cd web/backend
uvicorn main:app --reload        # http://localhost:8000/docs
```

Sheriff-sale parsing shells out to `pdftotext`, so install poppler locally
(`brew install poppler` on macOS) or use Docker (below).

Configuration is read from environment variables. For local development it
can also come from `web/backend/.env` (git-ignored, so never commit it), which
python-dotenv from `requirements-dev.txt` loads. The production image never
contains a `.env` file: `.dockerignore` excludes it.

| Variable | Purpose |
|---|---|
| `RESEND_API_KEY` | Enables email sharing through Resend. In Azure the value comes from Key Vault |
| `FROM_EMAIL` / `FROM_NAME` | Sender identity for shared reports |
| `SHARE_LIMIT_PER_USER_PER_HOUR` | Shares one signed-in user may send per rolling hour (default `20`) |
| `SHARE_LIMIT_PER_HOUR` | Shares the whole app may send per rolling hour (default `60`) |
| `ENABLE_DEBUG` | `true` turns on `POST /api/debug/analyze-pdf`, which otherwise returns `404` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Sends telemetry to Application Insights (see Observability). Leave unset locally |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (defaults to local Vite ports) |
| `DB_PATH` | SQLite database file for local development (default `reports.db`) |
| `REPORTS_DIR` | Local folder for report PDFs when Blob Storage isn't configured (default `web/backend/reports`) |
| `REPORTS_BLOB_URL` | Store report PDFs in Azure Blob Storage: the container URL, e.g. `https://<account>.blob.core.windows.net/reports`. Authenticates with the managed identity (no storage keys) |
| `AZURE_SQL_CONNECTION_STRING` | Use Azure SQL instead of SQLite. An ODBC connection string **without credentials** (no `UID`, `PWD`, or `Authentication`) — the app signs in with a Microsoft Entra token |
| `AZURE_CLIENT_ID` | Client ID of the user-assigned managed identity used for Azure SQL and Blob Storage. Leave unset locally to use your `az login` session |
| `RUN_MIGRATIONS` | Apply database migrations at startup (default `true`) |

### Database and migrations

Locally the API uses SQLite. In Azure it uses Azure SQL Database (the serverless
free offer) through Microsoft's ODBC Driver 18. That database auto-pauses when
idle, so the API never pools connections, retries briefly while it resumes, and
returns `503` with `Retry-After` if it isn't ready yet.

Schema changes are managed with Alembic and applied automatically at startup:

```bash
cd web/backend
alembic upgrade head                                  # apply migrations
alembic revision --autogenerate -m "describe change"  # after editing models in database.py
alembic check                                         # CI fails if models and migrations differ
```

A `reports.db` created before migrations existed will conflict — delete it
(local SQLite never holds production data).

Health endpoints: `GET /api/health` checks the process only and never touches
the database; `GET /api/health/db` wakes the database and returns `503` while it
resumes.

### Background jobs

Sheriff-sale analysis, spot checks, and shares respond immediately with
`{"job_id": …}` and do the work in the background. Static Web Apps cuts off
proxied API requests after 45 seconds, and county lookups, PDF rendering, and
email delivery can take longer. Poll `GET /api/jobs/{job_id}` until `status` is
`done` or `error`:

| Job | Started by | Available when `done` |
|---|---|---|
| Sheriff sale | `POST /api/sheriff-sale/upload` (multipart PDF) | `report_id` |
| Spot check | `POST /api/spot-check` | `report_id`, `result.deal`, `result.warning` |
| Share one deal | `POST /api/share/property` with `sale_id` | `result.recipient`, `result.count` |
| Share favorites | `POST /api/share/favorites` with `sale_ids` (1–100) | `result.recipient`, `result.count` |

A failed job has `status: "error"` with the reason in `message`. Jobs are
stored in the database, so progress survives an API restart. A job the restart
interrupted is marked failed at startup.

Shares identify deals by `sale_id`, and the API emails the analysis stored in
the deal list, never deal data posted by the browser. Invalid recipients,
unknown deals, and missing email configuration are rejected up front with
`400`, `404`, and `503`.

The frontend's API client (`web/frontend/src/api/client.js`):
- polls jobs one request at a time
- starts waking the database when the app loads
- retries `503` responses that carry `Retry-After`, showing a "Waking up the database…" banner meanwhile

A `503` without `Retry-After` is treated as a real error.

### Security

Sign-in and role checks happen at the edge. Static Web Apps admits only
invited users (`staticwebapp.config.json`, tracked in #9), and the API is
reachable only through its proxy. The API does no access control of its own.
Inside the API:

- **Share emails** contain only stored deal data, looked up by `sale_id`. Every
  interpolated value is HTML-escaped, including the sender's note. Display
  names are stripped of characters that could add recipients or headers, and
  request fields have length limits.
- **Share volume** is capped per rolling hour, both per signed-in user and
  app-wide (`429` when exceeded). The user comes from the
  `x-ms-client-principal` header that Static Web Apps adds. That header is used
  only to attribute jobs (`jobs.created_by`) and key limits, never for access
  control, and the app-wide cap holds even if the header is missing.
- **Uploads** must be named `.pdf`, carry a PDF signature, and be at most 25 MB.
  Static Web Apps refuses bodies over 30 MB.
- **Debug reports** (`/api/debug/*`) return `404` unless `ENABLE_DEBUG=true`.
- **Email** is sent only through `web/backend/mailer.py` (Resend today).

### Observability

Setting `APPLICATIONINSIGHTS_CONNECTION_STRING` turns on the Azure Monitor
OpenTelemetry distro (`web/backend/observability.py`). It records:
- incoming requests
- outgoing HTTP calls (county data, map tiles, Blob Storage)
- exceptions and metrics
- warnings and errors logged through the app's `realestate.*` loggers

Container Apps health probes (`/api/health`) are excluded to keep ingestion
down, while the database wake-up check (`/api/health/db`) is still recorded.
Standard `OTEL_*` environment variables override these defaults. Without a
connection string, nothing is configured.

### Frontend

```bash
cd web/frontend
npm ci
npm run dev                      # Vite proxies /api → http://localhost:8000
```

### Docker (API)

```bash
docker build -t realestate-api .
docker run -p 8000:8000 realestate-api
```

The image runs as an unprivileged user (UID 10001) with a single uvicorn
worker, and contains only the analysis modules, the logo, and `web/backend`.
SQLite and local report PDFs go to `/app/data`, the only writable directory;
mount a volume there to keep local data between runs. The server listens on
`PORT` (default `8000`).

## Tests and linting

```bash
ruff check .                                   # from the repo root
cd web/backend && pytest                       # backend tests
cd web/frontend && npm run lint && npm run build
```

## Continuous integration

`.github/workflows/ci.yml` runs on every pull request and push to `main`:

- **Backend** — ruff + pytest on Python 3.11
- **Frontend** — eslint + production build
- **Docker** — builds the API image and boots it to confirm it serves requests
- **Secrets** — gitleaks scans the full git history

## Contributing

Work follows issue → branch → pull request: open an issue, branch as
`feat/…`, `fix/…`, or `chore/…`, and merge via squash once CI is green.
Never commit secrets, `.env` files, databases, or generated reports.
