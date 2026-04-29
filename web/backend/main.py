import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db
from jobs import get_job
from models import JobStatus
from routers import sheriff_sale, spot_check, reports, debug

app = FastAPI(title="Estella Wilson Properties — Analysis API")

_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173")
_allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins     = _allowed_origins,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(sheriff_sale.router)
app.include_router(spot_check.router)
app.include_router(reports.router)
app.include_router(debug.router)


@app.get("/api/jobs/{job_id}", response_model=JobStatus)
def poll_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobStatus(job_id=job_id, **job)


@app.on_event("startup")
def startup():
    init_db()


# Serve React build (production mode)
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
