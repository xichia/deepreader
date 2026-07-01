import deepreader.summarise.artifact_importer as artifact_importer_module
import deepreader.summarise.remote_client as remote_client_module
from deepreader.storage.repositories import list_document_summaries, list_job_steps
from deepreader.api.routes_jobs import job_out
from deepreader.summarise.artifact_importer import import_summary_artifact
from deepreader.summarise.service import SummaryJobRunner
from deepreader.storage.models import Document, DocumentRecord, RecordSummary


def _create_document_with_records(db_session, count=2):
    document = Document(title="test", source_filename="test.txt", source_type="txt", source_hash="doc_hash")
    db_session.add(document)
    db_session.flush()
    records = []
    for index in range(count):
        record = DocumentRecord(
            document_id=document.id,
            stable_id=f"stable_{index}",
            record_type="paragraph",
            order_index=index,
            source_text=f"Source text {index}",
            source_hash=f"record_hash_{index}",
            metadata_json={},
        )
        db_session.add(record)
        records.append(record)
    db_session.commit()
    return document, records


class FakeRemoteSummaryClient:
    def __init__(self, *, status="completed", fail_last=False, provider="mock"):
        self.status = status
        self.fail_last = fail_last
        self.provider = provider
        self.submitted_records = []
        self.document_id = None
        self.submit_calls = 0
        self.artifact_calls = 0
        self.job_id = "remote-job-1"

    def submit_job(self, document_id, records):
        self.submit_calls += 1
        self.document_id = document_id
        self.submitted_records = records
        self.job_id = f"remote-job-{self.submit_calls}"
        return self.job_id

    def get_job_status(self, job_id):
        assert job_id == self.job_id
        failed_records = 1 if self.status == "failed" and self.fail_last else 0
        completed_records = len(self.submitted_records) - failed_records
        return {
            "status": self.status,
            "completed_records": completed_records,
            "failed_records": failed_records,
            "total_records": len(self.submitted_records),
            "stats": {"provider": self.provider, "completed_batches": int(not failed_records)},
            "error": "Provider quota exhausted" if failed_records else None,
        }

    def get_job_artifact(self, job_id):
        assert job_id == self.job_id
        self.artifact_calls += 1
        artifact = []
        for index, record in enumerate(self.submitted_records):
            failed = self.fail_last and index == len(self.submitted_records) - 1
            artifact.append(
                {
                    "document_id": self.document_id,
                    "record_id": record["record_id"],
                    "stable_id": record["stable_id"],
                    "source_hash": record["source_hash"],
                    "summary_text": "" if failed else f"Summary for {record['record_id']}",
                    "summary_style": "one_sentence",
                    "provider": "error" if failed else self.provider,
                    "model": "gemini-2.5-flash" if self.provider == "gemini" else "mock-deterministic-v1",
                    "template_version": "v1",
                    "status": "failed" if failed else "completed",
                    "error_code": "provider_rate_limited" if failed else None,
                    "message": "Gemini quota exhausted after retries" if failed else None,
                    "usage": {},
                }
            )
        return artifact

def test_import_summary_artifact(db_session):
    # Setup dummy document and records
    doc = Document(title="test", source_filename="test.txt", source_type="txt", source_hash="doc_hash")
    db_session.add(doc)
    db_session.commit()
    
    rec = DocumentRecord(
        document_id=doc.id,
        stable_id="stable_1",
        record_type="paragraph",
        order_index=0,
        source_text="Hello world",
        source_hash="rec_hash",
        metadata_json={}
    )
    db_session.add(rec)
    db_session.commit()
    
    # Import valid artifact
    artifact = [{
        "document_id": str(doc.id),
        "record_id": rec.stable_id,
        "stable_id": rec.stable_id,
        "source_hash": "rec_hash",
        "summary_text": "Valid summary.",
        "summary_style": "one_sentence",
        "provider": "mock",
        "model": "test-model",
        "template_version": "v1",
        "status": "completed",
    }]
    
    imported = import_summary_artifact(db_session, doc.id, artifact)
    assert imported["imported"] == 1
    
    summary = db_session.query(RecordSummary).filter_by(record_id=rec.id).first()
    assert summary is not None
    assert summary.summary_text == "Valid summary."
    assert summary.provider == "mock"

def test_import_artifact_rejects_wrong_document_id(db_session):
    doc = Document(title="test", source_filename="test.txt", source_type="txt", source_hash="doc_hash")
    db_session.add(doc)
    db_session.commit()
    
    artifact = [{
        "document_id": "9999", # wrong
        "record_id": "1",
        "stable_id": "1",
        "source_hash": "rec_hash",
        "summary_text": "Valid summary.",
        "status": "completed",
    }]
    imported = import_summary_artifact(db_session, doc.id, artifact)
    assert imported["imported"] == 0

def test_import_artifact_rejects_unknown_record_id(db_session):
    doc = Document(title="test", source_filename="test.txt", source_type="txt", source_hash="doc_hash")
    db_session.add(doc)
    db_session.commit()
    
    artifact = [{
        "document_id": str(doc.id),
        "record_id": "9999", # wrong
        "stable_id": "9999",
        "source_hash": "rec_hash",
        "summary_text": "Valid summary.",
        "status": "completed",
    }]
    imported = import_summary_artifact(db_session, doc.id, artifact)
    assert imported["imported"] == 0

def test_import_artifact_rejects_source_hash_mismatch(db_session):
    doc = Document(title="test", source_filename="test.txt", source_type="txt", source_hash="doc_hash")
    db_session.add(doc)
    db_session.commit()
    
    rec = DocumentRecord(
        document_id=doc.id,
        stable_id="stable_1",
        record_type="paragraph",
        order_index=0,
        source_text="Hello world",
        source_hash="rec_hash",
        metadata_json={}
    )
    db_session.add(rec)
    db_session.commit()
    
    artifact = [{
        "document_id": str(doc.id),
        "record_id": rec.stable_id,
        "stable_id": rec.stable_id,
        "source_hash": "wrong_hash",
        "summary_text": "Valid summary.",
        "status": "completed",
    }]
    imported = import_summary_artifact(db_session, doc.id, artifact)
    assert imported["imported"] == 0


def test_import_artifact_rejects_stable_id_mismatch(db_session):
    document, records = _create_document_with_records(db_session, count=1)
    artifact = [{
        "document_id": str(document.id),
        "record_id": records[0].stable_id,
        "stable_id": "wrong-stable-id",
        "source_hash": records[0].source_hash,
        "summary_text": "Valid summary.",
        "provider": "gemini",
        "status": "completed",
    }]

    imported = import_summary_artifact(db_session, document.id, artifact)

    assert imported["imported"] == 0
    assert imported["failed"] == 1


def test_import_artifact_rejects_duplicate_record_ids(db_session):
    document, records = _create_document_with_records(db_session, count=1)
    line = {
        "document_id": str(document.id),
        "record_id": records[0].stable_id,
        "stable_id": records[0].stable_id,
        "source_hash": records[0].source_hash,
        "summary_text": "Valid summary.",
        "provider": "mock",
        "status": "completed",
    }

    imported = import_summary_artifact(db_session, document.id, [line, line])

    assert imported["imported"] == 1
    assert imported["failed"] == 1
    assert imported["failed_record_ids"] == [records[0].stable_id]
    assert db_session.query(RecordSummary).filter_by(record_id=records[0].id).count() == 1


def test_import_artifact_compacts_failed_provider_diagnostics(db_session):
    document, records = _create_document_with_records(db_session, count=8)
    artifact = [
        {
            "document_id": str(document.id),
            "record_id": record.stable_id,
            "stable_id": record.stable_id,
            "source_hash": record.source_hash,
            "summary_text": "",
            "status": "failed",
            "error_code": "provider_rate_limited" if index < 6 else "provider_timeout",
            "message": (
                "api_key=must-not-leak; contents: FULL_SOURCE_MUST_NOT_LEAK"
                if index == 0
                else f"Sanitized provider failure {index}"
            ),
            "provider": "gemini",
            "model": "gemini-3.1-flash-lite",
        }
        for index, record in enumerate(records)
    ]

    imported = import_summary_artifact(
        db_session,
        document.id,
        artifact,
        remote_job_id="remote-diagnostic-job",
    )

    assert imported["failed"] == 8
    assert imported["error_code_counts"] == {
        "provider_rate_limited": 6,
        "provider_timeout": 2,
    }
    assert len(imported["failed_examples"]) == 5
    assert len(imported["errors"]) == 1
    assert "remote-diagnostic-job" in imported["failure_summary"]
    assert "8 failed artifact line(s)" in imported["failure_summary"]
    assert "provider_rate_limited=6" in imported["failure_summary"]
    assert '"stable_id"' in imported["failure_summary"]
    assert '"provider": "gemini"' in imported["failure_summary"]
    assert '"model": "gemini-3.1-flash-lite"' in imported["failure_summary"]
    assert "must-not-leak" not in imported["failure_summary"]
    assert "FULL_SOURCE_MUST_NOT_LEAK" not in imported["failure_summary"]
    assert "Artifact line for record" not in imported["failure_summary"]


def test_remote_summary_runner_imports_once_and_uses_checkpoints(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)
    client = FakeRemoteSummaryClient()
    importer_calls = 0
    real_importer = artifact_importer_module.import_summary_artifact

    def counting_importer(*args, **kwargs):
        nonlocal importer_calls
        importer_calls += 1
        return real_importer(*args, **kwargs)

    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)
    monkeypatch.setattr(artifact_importer_module, "import_summary_artifact", counting_importer)

    first_job = SummaryJobRunner().run_for_document(db_session, document.id)
    second_job = SummaryJobRunner().run_for_document(db_session, document.id)
    summaries = list_document_summaries(db_session, document.id)

    assert first_job.status == "completed"
    assert second_job.status == "completed"
    assert first_job.completed_steps == len(records)
    assert second_job.completed_steps == len(records)
    assert all(step.attempt_count == 1 for step in list_job_steps(db_session, first_job.id))
    assert all(step.attempt_count == 1 for step in list_job_steps(db_session, second_job.id))
    assert len(summaries) == len(records)
    assert all(summary.summariser_name == "mock" for summary in summaries)
    assert client.submit_calls == 1
    assert client.artifact_calls == 1
    assert importer_calls == 1


def test_remote_gemini_runner_uses_provider_specific_checkpoints(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)
    client = FakeRemoteSummaryClient(provider="gemini")

    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setenv("SUMMARY_SERVICE_PROVIDER", "gemini")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    first_job = SummaryJobRunner().run_for_document(db_session, document.id)
    second_job = SummaryJobRunner().run_for_document(db_session, document.id)
    summaries = list_document_summaries(db_session, document.id)

    assert first_job.status == "completed"
    assert second_job.status == "completed"
    assert client.submit_calls == 1
    assert len(summaries) == len(records)
    assert all(summary.summariser_name == "gemini" for summary in summaries)


def test_remote_summary_runner_preserves_failed_artifact_state(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)
    client = FakeRemoteSummaryClient(status="failed", fail_last=True)

    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    job = SummaryJobRunner().run_for_document(db_session, document.id)
    steps = list_job_steps(db_session, job.id)
    summaries = list_document_summaries(db_session, document.id)

    assert job.status == "failed"
    assert job.completed_steps == 1
    assert job.failed_steps == 1
    assert [step.status for step in steps] == ["completed", "failed"]
    assert all(step.attempt_count == 1 for step in steps)
    assert len(summaries) == 1
    assert summaries[0].record_id == records[0].id
    assert "remote-job-1" in job.error_message
    assert "provider_rate_limited=1" in job.error_message
    assert job.remote_job_id == "remote-job-1"
    assert job.remote_progress_json["remote_status"] == "failed"
    assert job.remote_progress_json["remote_completed_records"] == 1
    assert job.remote_progress_json["remote_failed_records"] == 1
    failed_step = next(step for step in steps if step.status == "failed")
    assert "provider_rate_limited" in failed_step.error_message
    assert "Gemini quota exhausted after retries" in failed_step.error_message

    payload = job_out(job)
    assert payload.remote_job_id == "remote-job-1"
    assert payload.remote_status == "failed"
    assert payload.remote_total_records == 2
    assert payload.remote_stats["provider"] == "mock"


def test_env_configured_remote_summary_polling_values(monkeypatch):
    from deepreader.summarise.service import get_remote_max_polls, get_remote_poll_interval
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "150")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "1.5")
    assert get_remote_max_polls() == 150
    assert get_remote_poll_interval() == 1.5


def test_invalid_polling_env_values(monkeypatch):
    from deepreader.summarise.service import get_remote_max_polls, get_remote_poll_interval
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "not_an_int")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "not_a_float")
    assert get_remote_max_polls() == 60
    assert get_remote_poll_interval() == 2.0

    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "-5")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "-2.5")
    assert get_remote_max_polls() == 60
    assert get_remote_poll_interval() == 2.0


def test_remote_summary_timeout_path_marks_job_failed(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)
    client = FakeRemoteSummaryClient(status="running")

    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "1")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "0.001")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    job = SummaryJobRunner().run_for_document(db_session, document.id)
    steps = list_job_steps(db_session, job.id)

    assert job.status == "failed"
    assert "did not finish before the polling timeout" in job.error_message
    assert "remote-job-1" in job.error_message
    assert all(step.status == "failed" for step in steps)


def test_remote_summary_retry_reuses_completed_job(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)
    client_1 = FakeRemoteSummaryClient(status="running")
    client_2 = FakeRemoteSummaryClient(status="completed")

    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "1")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "0.001")

    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client_1)
    runner = SummaryJobRunner()
    job = runner.run_for_document(db_session, document.id)
    assert job.status == "failed"

    # client_2 needs to know what records client_1 submitted so it can return them in the artifact
    client_2.submitted_records = client_1.submitted_records
    client_2.document_id = client_1.document_id
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client_2)
    retried_job = runner.retry_failed_steps(db_session, job.id)

    assert retried_job.status == "completed"
    assert client_2.submit_calls == 0
    assert client_2.artifact_calls == 1


def test_remote_summary_retry_submits_new_job_if_reuse_fails(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)
    client_1 = FakeRemoteSummaryClient(status="running")

    class BrokenStatusClient(FakeRemoteSummaryClient):
        def get_job_status(self, job_id):
            if job_id == "remote-job-1":
                raise ValueError("Job not found in memory")
            return {"status": "completed"}

        def submit_job(self, document_id, records):
            self.submit_calls += 1
            self.document_id = document_id
            self.submitted_records = records
            self.job_id = "remote-job-2"
            return self.job_id

        def get_job_artifact(self, job_id):
            assert job_id == "remote-job-2"
            return super().get_job_artifact(job_id)

    client_2 = BrokenStatusClient(status="completed")

    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "1")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "0.001")

    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client_1)
    runner = SummaryJobRunner()
    job = runner.run_for_document(db_session, document.id)
    assert job.status == "failed"

    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client_2)
    retried_job = runner.retry_failed_steps(db_session, job.id)

    assert retried_job.status == "completed"
    assert client_2.submit_calls == 1
    assert client_2.artifact_calls == 1


def test_remote_summary_polling_paused_to_completed(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)

    class SequenceRemoteClient:
        def __init__(self):
            self.calls = 0
            self.submitted_records = []
            self.document_id = None
        def submit_job(self, document_id, records):
            self.document_id = document_id
            self.submitted_records = records
            return "remote-seq-1"
        def get_job_status(self, job_id):
            self.calls += 1
            # 1, 2, 3: paused
            # 4: running
            # 5: completed
            if self.calls <= 3:
                status = "paused"
            elif self.calls == 4:
                status = "running"
            else:
                status = "completed"
            return {
                "status": status,
                "completed_records": len(self.submitted_records),
                "failed_records": 0,
                "total_records": len(self.submitted_records),
                "stats": {"provider": "mock"},
                "error": None,
            }
        def get_job_artifact(self, job_id):
            return [
                {
                    "document_id": self.document_id,
                    "record_id": record["record_id"],
                    "stable_id": record["stable_id"],
                    "source_hash": record["source_hash"],
                    "summary_text": f"Summary for {record['record_id']}",
                    "summary_style": "one_sentence",
                    "provider": "mock",
                    "status": "completed",
                }
                for record in self.submitted_records
            ]

    client = SequenceRemoteClient()
    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    # max polls is 2, but we have 3 paused polls, so if paused polls counted, it would fail/timeout.
    # Because it succeeds, it proves paused polls do not exhaust the budget.
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "2")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "0.001")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    job = SummaryJobRunner().run_for_document(db_session, document.id)
    assert job.status == "completed"
    assert client.calls == 5


def test_remote_summary_polling_cancelled_skips_import(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)

    class CancelledRemoteClient:
        def __init__(self):
            self.submitted_records = []
            self.artifact_called = False
        def submit_job(self, document_id, records):
            self.submitted_records = records
            return "remote-cancel-1"
        def get_job_status(self, job_id):
            return {
                "status": "cancelled",
                "completed_records": 0,
                "failed_records": 0,
                "total_records": len(self.submitted_records),
                "stats": {},
                "error": None,
            }
        def get_job_artifact(self, job_id):
            self.artifact_called = True
            return []

    client = CancelledRemoteClient()
    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "5")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "0.001")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    job = SummaryJobRunner().run_for_document(db_session, document.id)
    assert job.status == "cancelled"
    assert not client.artifact_called
    # Unfinished steps are accounted as skipped (not failed) on cancel.
    steps = list_job_steps(db_session, job.id)
    assert len(steps) > 0
    assert all(step.status == "skipped" for step in steps)
    assert all(step.error_code == "job_cancelled" for step in steps)
    assert all("cancelled" in (step.error_message or "").lower() for step in steps)


def test_remote_summary_polling_respects_local_cancellation(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session)

    # We need a client that triggers local cancellation during get_job_status
    class CancellingRemoteClient:
        def __init__(self, db_session):
            self.db_session = db_session
            self.job = None
            self.artifact_called = False
        def submit_job(self, document_id, records):
            # Find the job in DB
            from deepreader.storage.models import Job
            self.job = self.db_session.query(Job).filter_by(document_id=document_id).order_by(Job.id.desc()).first()
            return "remote-local-cancel-1"
        def get_job_status(self, job_id):
            # Cancel job locally
            if self.job:
                self.job.status = "cancelled"
                self.db_session.commit()
            return {
                "status": "running",
                "completed_records": 0,
                "failed_records": 0,
                "total_records": 1,
                "stats": {},
                "error": None,
            }
        def get_job_artifact(self, job_id):
            self.artifact_called = True
            return []

    client = CancellingRemoteClient(db_session)
    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "5")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "0.001")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    job = SummaryJobRunner().run_for_document(db_session, document.id)
    assert job.status == "cancelled"
    assert not client.artifact_called


def test_remote_summary_cancel_during_import_preserves_cancelled(db_session, monkeypatch):
    """Local cancellation during artifact import must not be overwritten by remote completion."""
    document, records = _create_document_with_records(db_session)

    class CompletedClient:
        def __init__(self):
            self.submitted_records = []
            self.document_id = None
            self.artifact_called = False
        def submit_job(self, document_id, records_to_send):
            self.document_id = document_id
            self.submitted_records = records_to_send
            return "remote-race-1"
        def get_job_status(self, job_id):
            return {
                "status": "completed",
                "completed_records": len(self.submitted_records),
                "failed_records": 0,
                "total_records": len(self.submitted_records),
                "stats": {"provider": "mock"},
                "error": None,
            }
        def get_job_artifact(self, job_id):
            self.artifact_called = True
            return [
                {
                    "document_id": self.document_id,
                    "record_id": record["record_id"],
                    "stable_id": record["stable_id"],
                    "source_hash": record["source_hash"],
                    "summary_text": f"Summary for {record['record_id']}",
                    "summary_style": "one_sentence",
                    "provider": "mock",
                    "status": "completed",
                }
                for record in self.submitted_records
            ]

    client = CompletedClient()
    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "5")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "0.001")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    real_importer = artifact_importer_module.import_summary_artifact

    def racing_importer(session, document_id, artifact, **kwargs):
        from deepreader.storage.models import Job
        from deepreader.storage.repositories import (
            JOB_STATUS_CANCELLED,
            mark_unfinished_steps_cancelled,
            refresh_job_progress,
            set_job_status,
        )
        local_job = (
            session.query(Job)
            .filter_by(document_id=document_id)
            .order_by(Job.id.desc())
            .first()
        )
        if local_job is not None:
            set_job_status(session, local_job, JOB_STATUS_CANCELLED)
            mark_unfinished_steps_cancelled(session, local_job)
            refresh_job_progress(session, local_job)
            session.commit()
        return real_importer(session, document_id, artifact, **kwargs)

    monkeypatch.setattr(
        artifact_importer_module, "import_summary_artifact", racing_importer
    )

    job = SummaryJobRunner().run_for_document(db_session, document.id)

    assert client.artifact_called
    assert job.status == "cancelled"
    assert job.status not in {"completed", "failed"}
    steps = list_job_steps(db_session, job.id)
    assert len(steps) > 0
    assert all(step.status not in {"pending", "running", "paused"} for step in steps)


def test_remote_summary_runner_maps_skipped_artifact_to_skipped_step(db_session, monkeypatch):
    document, records = _create_document_with_records(db_session, count=2)

    class SkippedClient:
        def __init__(self):
            self.submitted_records = []
            self.document_id = None
            self.artifact_called = False
        def submit_job(self, document_id, records_to_send):
            self.document_id = document_id
            self.submitted_records = records_to_send
            return "remote-skip-1"
        def get_job_status(self, job_id):
            return {
                "status": "completed",
                "completed_records": 1,
                "failed_records": 0,
                "total_records": len(self.submitted_records),
                "stats": {"provider": "mock"},
                "error": None,
            }
        def get_job_artifact(self, job_id):
            self.artifact_called = True
            artifact = []
            for index, record in enumerate(self.submitted_records):
                if index == 0:
                    artifact.append({
                        "document_id": self.document_id,
                        "record_id": record["record_id"],
                        "stable_id": record["stable_id"],
                        "source_hash": record["source_hash"],
                        "summary_text": f"Summary for {record['record_id']}",
                        "summary_style": "one_sentence",
                        "provider": "mock",
                        "status": "completed",
                    })
                else:
                    artifact.append({
                        "document_id": self.document_id,
                        "record_id": record["record_id"],
                        "stable_id": record["stable_id"],
                        "source_hash": record["source_hash"],
                        "summary_text": "",
                        "status": "skipped",
                        "error_code": "empty_summary",
                        "message": "Paragraph was empty or unreadable",
                        "provider": "mock",
                    })
            return artifact

    client = SkippedClient()
    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    job = SummaryJobRunner().run_for_document(db_session, document.id)
    steps = list_job_steps(db_session, job.id)
    summaries = list_document_summaries(db_session, document.id)

    assert job.status == "completed"
    assert job.completed_steps == 1
    assert job.skipped_steps == 1
    assert job.failed_steps == 0

    completed_step = next(step for step in steps if step.status == "completed")
    skipped_step = next(step for step in steps if step.status == "skipped")
    assert skipped_step is not None
    assert skipped_step.error_code == "empty_summary"
    assert skipped_step.error_message == "Paragraph was empty or unreadable"
    assert skipped_step.finished_at is not None

    # No RecordSummary row is persisted for the skipped record.
    skipped_record = records[1]
    assert (
        db_session.query(RecordSummary)
        .filter_by(record_id=skipped_record.id)
        .count()
        == 0
    )
    # Exactly one summary is persisted for the completed record.
    assert len(summaries) == 1
    assert summaries[0].record_id == records[0].id


def test_remote_summary_cancel_maps_unfinished_to_skipped_job_cancelled(db_session, monkeypatch):
    """Remote cancellation polling accounts unfinished steps as skipped/job_cancelled, not failed."""
    from deepreader.storage.repositories import get_job

    document, records = _create_document_with_records(db_session, count=3)

    class PartialCancelledRemoteClient:
        def __init__(self):
            self.submitted_records = []
            self.document_id = None
            self.artifact_called = False

        def submit_job(self, document_id, records_to_send):
            self.document_id = document_id
            self.submitted_records = records_to_send
            return "remote-partial-cancel-1"

        def get_job_status(self, job_id):
            return {
                "status": "cancelled",
                "completed_records": 0,
                "failed_records": 0,
                "total_records": len(self.submitted_records),
                "stats": {},
                "error": None,
            }

        def get_job_artifact(self, job_id):
            self.artifact_called = True
            return []

    client = PartialCancelledRemoteClient()
    monkeypatch.setenv("DEEPREADER_SUMMARY_BACKEND", "remote")
    monkeypatch.setenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "true")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_MAX_POLLS", "5")
    monkeypatch.setenv("DEEPREADER_REMOTE_SUMMARY_POLL_INTERVAL_SECONDS", "0.001")
    monkeypatch.setattr(remote_client_module, "RemoteSummaryClient", lambda: client)

    job = SummaryJobRunner().run_for_document(db_session, document.id)
    assert job.status == "cancelled"
    # Remote-cancel short-circuits before artifact fetch in this ticket.
    assert not client.artifact_called

    refreshed = get_job(db_session, job.id)
    assert refreshed is not None
    assert refreshed.completed_steps == 0
    assert refreshed.failed_steps == 0
    assert refreshed.skipped_steps == len(records)

    steps = list_job_steps(db_session, job.id)
    assert len(steps) == len(records)
    assert all(step.status == "skipped" for step in steps)
    assert all(step.error_code == "job_cancelled" for step in steps)
    assert all("cancelled" in (step.error_message or "").lower() for step in steps)
