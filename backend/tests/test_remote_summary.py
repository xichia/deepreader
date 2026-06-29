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
