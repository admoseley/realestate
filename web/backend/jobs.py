import uuid
from typing import Optional

# In-memory job tracker: {job_id: {status, percent, message, report_id}}
_jobs: dict[str, dict] = {}


def create_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {"status": "pending", "percent": 0, "message": "Queued…", "report_id": None}
    return job_id


def update_job(job_id: str, status: str, percent: int, message: str, report_id: Optional[int] = None):
    if job_id in _jobs:
        _jobs[job_id] = {
            "status":    status,
            "percent":   percent,
            "message":   message,
            "report_id": report_id or _jobs[job_id].get("report_id"),
        }


def get_job(job_id: str) -> Optional[dict]:
    return _jobs.get(job_id)


def fail_job(job_id: str, error: str):
    update_job(job_id, "error", 0, error)
