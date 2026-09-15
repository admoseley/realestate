import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    # python-dotenv is a development dependency (requirements-dev.txt), so the
    # app must not require it. In production, settings are real environment
    # variables, with secrets from Key Vault references, and the image has no
    # .env file. (uvicorn[standard] installs python-dotenv there anyway.)
    pass
else:
    load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from database import DatabaseUnavailable, engine, run_migrations
from jobs import fail_orphaned_jobs, get_job
from models import JobStatus
from routers import sheriff_sale, spot_check, reports, debug, share, deals

log = logging.getLogger(__name__)

# How long startup waits for the database. Startup isn't subject to the
# 45-second proxy limit, so it can outlast a full serverless resume.
STARTUP_DB_WAIT_SECONDS = 180


def _migrate_when_database_ready() -> None:
    deadline = time.monotonic() + STARTUP_DB_WAIT_SECONDS
    while True:
        try:
            run_migrations()
            return
        except DatabaseUnavailable:
            if time.monotonic() >= deadline:
                raise
            log.warning("Database is still starting; retrying migrations")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Migrations run in-process at startup. That's safe because the API runs as
    # a single instance; scaling out would need a separate migration step.
    if os.getenv("RUN_MIGRATIONS", "true").lower() != "false":
        _migrate_when_database_ready()
    orphaned = fail_orphaned_jobs()
    if orphaned:
        log.warning("Marked %d unfinished job(s) from a previous run as failed", orphaned)
    yield


app = FastAPI(title="Estella Wilson Properties — Analysis API", lifespan=lifespan)

_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173")
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins     = _allowed_origins,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
    # Browsers hide non-safelisted response headers from cross-origin callers.
    # The frontend reads Retry-After to decide whether a 503 means "database
    # resuming, try again", so it has to be exposed while the frontend and API
    # are on different origins (Netlify → Render, and local setups without the
    # Vite proxy). Behind Static Web Apps they share an origin and CORS is moot.
    expose_headers    = ["Retry-After"],
)


@app.exception_handler(DatabaseUnavailable)
async def database_unavailable(_request: Request, exc: DatabaseUnavailable):
    # Usually the serverless database resuming from auto-pause. The frontend
    # retries 503 responses; Retry-After tells it how long to wait.
    return JSONResponse(status_code=503, content={"detail": str(exc)}, headers={"Retry-After": "10"})


app.include_router(sheriff_sale.router)
app.include_router(spot_check.router)
app.include_router(reports.router)
app.include_router(debug.router)
app.include_router(share.router)
app.include_router(deals.router)


@app.get("/api/health")
def health():
    """Liveness/readiness probe. Deliberately never queries the database, so
    container health checks can't wake it or keep it from auto-pausing."""
    return {"status": "ok"}


@app.get("/api/health/db")
def health_db():
    """Wake the database and confirm it can serve queries. The frontend calls
    this before loading data; it returns 503 while the database resumes."""
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def poll_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobStatus(job_id=job_id, **job)
