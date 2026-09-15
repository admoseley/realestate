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
| Email | Resend | `web/backend/routers/share.py` |

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

Configuration is read from the environment or `web/backend/.env` (git-ignored — never commit it):

| Variable | Purpose |
|---|---|
| `RESEND_API_KEY` | Enables email sharing |
| `FROM_EMAIL` / `FROM_NAME` | Sender identity for shared reports |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins (defaults to local Vite ports) |
| `DB_PATH` | SQLite database file for local development (default `reports.db`) |
| `REPORTS_DIR` | Where generated PDFs are written |
| `AZURE_SQL_CONNECTION_STRING` | Use Azure SQL instead of SQLite. An ODBC connection string **without credentials** (no `UID`, `PWD`, or `Authentication`) — the app signs in with a Microsoft Entra token |
| `AZURE_CLIENT_ID` | Client ID of the user-assigned managed identity used for Azure SQL. Leave unset locally to use your `az login` session |
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
