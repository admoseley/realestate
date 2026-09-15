"""Job progress is persisted in the database, so it survives restarts."""
import uuid
from datetime import timedelta

import jobs
from database import utcnow


def test_jobs_can_be_counted_by_kind_user_and_time(migrated_db):
    since = utcnow() - timedelta(minutes=1)
    user = f"{uuid.uuid4().hex}@example.com"
    shares_before = jobs.count_jobs_since("share", since)

    jobs.create_job(kind="share", created_by=user)
    jobs.create_job(kind="share")
    jobs.create_job(kind="spot_check", created_by=user)

    assert jobs.count_jobs_since("share", since) == shares_before + 2
    assert jobs.count_jobs_since("share", since, created_by=user) == 1
    assert jobs.count_jobs_since("share", utcnow() + timedelta(minutes=1)) == 0


def test_job_lifecycle(migrated_db):
    job_id = jobs.create_job()
    assert jobs.get_job(job_id) == {
        "status": "pending", "percent": 0, "message": "Queued…", "report_id": None, "result": None,
    }

    jobs.update_job(job_id, "running", 40, "Working", report_id=7)
    assert jobs.get_job(job_id)["report_id"] == 7

    jobs.update_job(job_id, "done", 100, "Finished")
    job = jobs.get_job(job_id)
    assert job["status"] == "done"
    assert job["report_id"] == 7  # kept when a later update doesn't pass one


def test_fail_job_records_the_error(migrated_db):
    job_id = jobs.create_job()
    jobs.fail_job(job_id, "Pipeline error: boom")

    job = jobs.get_job(job_id)
    assert job["status"] == "error"
    assert job["message"] == "Pipeline error: boom"


def test_unknown_job_is_none(migrated_db):
    assert jobs.get_job("does-not-exist") is None


def test_rapid_progress_updates_are_throttled_but_completion_is_not(migrated_db):
    job_id = jobs.create_job()
    jobs.update_job(job_id, "running", 10, "first")
    jobs.update_job(job_id, "running", 20, "second")  # within the interval: skipped
    assert jobs.get_job(job_id)["percent"] == 10

    jobs.update_job(job_id, "done", 100, "all done")  # status changes always write
    assert jobs.get_job(job_id)["status"] == "done"


def test_long_messages_are_truncated_to_the_column_size(migrated_db):
    job_id = jobs.create_job()
    jobs.fail_job(job_id, "x" * 2000)
    assert len(jobs.get_job(job_id)["message"]) == 500


def test_jobs_left_running_by_a_previous_process_are_failed(migrated_db):
    job_id = jobs.create_job()
    jobs.update_job(job_id, "running", 50, "halfway")

    assert jobs.fail_orphaned_jobs() >= 1
    job = jobs.get_job(job_id)
    assert job["status"] == "error"
    assert job["message"] == jobs.ORPHANED_JOB_MESSAGE
