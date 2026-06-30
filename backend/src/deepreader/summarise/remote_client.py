import os
import httpx
import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

class RemoteSummaryClient:
    def __init__(self):
        self.base_url = os.getenv("PARAGRAPH_SUMMARY_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/")
    
    def submit_job(self, document_id: str, records: list[dict[str, Any]]) -> str:
        """Submit a batch of records to the summary service."""
        payload = {
            "document_id": document_id,
            "records": records,
            "summary_style": "one_sentence",
            "priority": "interactive"
        }
        
        try:
            response = httpx.post(f"{self.base_url}/paragraph-summaries", json=payload)
            response.raise_for_status()
            data = response.json()
            return data["job_id"]
        except Exception as exc:
            LOGGER.error("Failed to submit remote summary job: %s", exc)
            raise RuntimeError(f"Remote summary service error: {exc}") from exc

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get current job status from the remote service."""
        try:
            response = httpx.get(f"{self.base_url}/jobs/{job_id}")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            LOGGER.error("Failed to fetch remote summary job status: %s", exc)
            raise RuntimeError(f"Remote summary service error: {exc}") from exc

    def get_job_artifact(self, job_id: str) -> list[dict[str, Any]]:
        """Get the completed job artifact (JSON lines represented as a list of dicts)."""
        try:
            response = httpx.get(f"{self.base_url}/jobs/{job_id}/artifact")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            LOGGER.error("Failed to fetch remote summary job artifact: %s", exc)
            raise RuntimeError(f"Remote summary service error: {exc}") from exc

    def cancel_job(self, job_id: str) -> dict[str, Any]:
        """Cancel a remote summary job."""
        try:
            response = httpx.post(f"{self.base_url}/jobs/{job_id}/cancel")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            LOGGER.error("Failed to cancel remote summary job: %s", exc)
            raise RuntimeError(f"Remote summary service error: {exc}") from exc

    def pause_job(self, job_id: str) -> dict[str, Any]:
        """Pause a remote summary job."""
        try:
            response = httpx.post(f"{self.base_url}/jobs/{job_id}/pause")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            LOGGER.error("Failed to pause remote summary job: %s", exc)
            raise RuntimeError(f"Remote summary service error: {exc}") from exc

    def resume_job(self, job_id: str) -> dict[str, Any]:
        """Resume a remote summary job."""
        try:
            response = httpx.post(f"{self.base_url}/jobs/{job_id}/resume")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            LOGGER.error("Failed to resume remote summary job: %s", exc)
            raise RuntimeError(f"Remote summary service error: {exc}") from exc
