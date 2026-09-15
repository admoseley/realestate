"""Finished jobs carry their results, and background failures land on the job."""
import pytest

import jobs


def test_completed_jobs_carry_their_result(migrated_db):
    job_id = jobs.create_job()
    jobs.complete_job(job_id, "Analysis complete", report_id=3,
                      result={"deal": {"address": "1 Main St"}, "warning": None})

    job = jobs.get_job(job_id)
    assert job["status"] == "done"
    assert job["percent"] == 100
    assert job["report_id"] == 3
    assert job["result"] == {"deal": {"address": "1 Main St"}, "warning": None}


def test_run_job_passes_the_job_id_and_arguments(migrated_db):
    job_id = jobs.create_job()

    def work(received_id, message):
        jobs.complete_job(received_id, message)

    jobs.run_job(job_id, "Should not fail", work, "all good")
    assert jobs.get_job(job_id)["message"] == "all good"


def test_expected_job_errors_are_shown_as_is(migrated_db):
    job_id = jobs.create_job()

    def work(_job_id):
        raise jobs.JobError("Recipient address was rejected by the mail server.")

    jobs.run_job(job_id, "Share failed", work)

    job = jobs.get_job(job_id)
    assert job["status"] == "error"
    assert job["message"] == "Recipient address was rejected by the mail server."


def test_unexpected_errors_are_logged_and_recorded_without_raising(migrated_db, caplog):
    job_id = jobs.create_job()

    def work(_job_id):
        raise RuntimeError("boom")

    jobs.run_job(job_id, "Spot check failed", work)  # must not raise

    assert jobs.get_job(job_id)["message"] == "Spot check failed: boom"
    assert any(record.exc_info for record in caplog.records)


@pytest.mark.parametrize("status", ["done", "error"])
def test_job_status_exposes_result_through_the_api(client, status):
    job_id = jobs.create_job()
    if status == "done":
        jobs.complete_job(job_id, "Sent", result={"recipient": "a@example.com", "count": 1})
    else:
        jobs.fail_job(job_id, "nope")

    body = client.get(f"/api/jobs/{job_id}").json()
    assert body["status"] == status
    assert body["result"] == ({"recipient": "a@example.com", "count": 1} if status == "done" else None)
