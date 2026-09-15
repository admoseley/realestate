"""Background job progress, persisted in the database.

Job state used to live in an in-memory dict, so any restart lost every running
job and polling clients got 404s. It now lives in the ``jobs`` table. The
public functions keep their original signatures, so callers didn't change.

Each call opens and closes its own short session. Jobs run in background tasks
outside any request, and holding a connection open for a multi-minute job
would stop the serverless database from auto-pausing.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Callable, Optional

from database import Job, SessionLocal, utcnow

log = logging.getLogger(__name__)

# Progress arrives about once per enriched property. Writing every update would
# mean a database round trip each time, so interim "running" updates are
# throttled; status changes, new report IDs, and results are always written.
_MIN_PROGRESS_INTERVAL = 2.0
_last_write: dict[str, tuple[float, Optional[int]]] = {}  # job_id -> (time, report_id)

ORPHANED_JOB_MESSAGE = "The server restarted before this job finished. Please run it again."


def create_job(created_by: Optional[str] = None) -> str:
    job_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.add(Job(id=job_id, status="pending", percent=0, message="Queued…", created_by=created_by))
        db.commit()
    return job_id


def _is_throttled(job_id: str, status: str, report_id: Optional[int], result_json: Optional[str]) -> bool:
    last = _last_write.get(job_id)
    if status != "running" or result_json is not None or last is None:
        return False
    last_time, last_report_id = last
    if report_id is not None and report_id != last_report_id:
        return False
    return time.monotonic() - last_time < _MIN_PROGRESS_INTERVAL


def update_job(job_id: str, status: str, percent: int, message: str,
               report_id: Optional[int] = None, result_json: Optional[str] = None):
    if _is_throttled(job_id, status, report_id, result_json):
        return
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return
        job.status     = status
        job.percent    = percent
        job.message    = message[:500]
        job.updated_at = utcnow()
        if report_id is not None:
            job.report_id = report_id
        if result_json is not None:
            job.result_json = result_json
        db.commit()
        written_report_id = job.report_id
    if status in ("done", "error"):
        _last_write.pop(job_id, None)
    else:
        _last_write[job_id] = (time.monotonic(), written_report_id)


def get_job(job_id: str) -> Optional[dict]:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return None
        return {
            "status":    job.status,
            "percent":   job.percent,
            "message":   job.message,
            "report_id": job.report_id,
            "result":    json.loads(job.result_json) if job.result_json else None,
        }


def complete_job(job_id: str, message: str, report_id: Optional[int] = None,
                 result: Optional[dict] = None):
    """Mark a job done, with whatever the client needs to show the outcome.

    ``result`` is what the old synchronous endpoints returned in their response
    body; clients now read it from the job once polling sees ``done``.
    """
    result_json = json.dumps(result, default=str) if result is not None else None
    update_job(job_id, "done", 100, message, report_id=report_id, result_json=result_json)


def fail_job(job_id: str, error: str):
    update_job(job_id, "error", 0, error)


class JobError(Exception):
    """An expected failure, such as a rejected recipient address. Its message is
    shown to the user as-is, and no traceback is logged."""


def run_job(job_id: str, failure_message: str, work: Callable[..., Any], *args: Any) -> None:
    """Run ``work(job_id, *args)`` as a background task and record any failure.

    Nothing propagates. The HTTP response went out before the task started, so
    re-raising would only add a generic "Exception in ASGI application" log line.
    Unexpected errors are logged here with their traceback instead, and the
    job's message tells the polling client what happened.
    """
    try:
        work(job_id, *args)
    except JobError as exc:
        fail_job(job_id, str(exc))
    except Exception as exc:
        log.exception("Job %s failed", job_id)
        fail_job(job_id, f"{failure_message}: {exc}")


def fail_orphaned_jobs() -> int:
    """Mark jobs a previous process left pending or running as failed.

    Called at startup. Safe because the API runs as a single instance: nothing
    else can be executing those jobs.
    """
    with SessionLocal() as db:
        count = (
            db.query(Job)
            .filter(Job.status.in_(("pending", "running")))
            .update(
                {Job.status: "error", Job.message: ORPHANED_JOB_MESSAGE, Job.updated_at: utcnow()},
                synchronize_session=False,
            )
        )
        db.commit()
    return count
