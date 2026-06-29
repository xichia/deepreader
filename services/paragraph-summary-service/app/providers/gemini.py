"""Gemini paragraph-summary provider."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from pydantic import BaseModel, ValidationError

from app.providers.base import BaseProvider
from app.records.schema import InputRecord, SummaryArtifactLine


class StructuredOutputParseError(ValueError):
    """Raised when Gemini does not return the requested JSON structure."""


class GeminiSummaryItem(BaseModel):
    record_id: str
    source_hash: str
    summary_text: str
    status: str


class GeminiSummaryPayload(BaseModel):
    summaries: list[GeminiSummaryItem]


class GeminiProvider(BaseProvider):
    def __init__(
        self,
        model_name: str,
        template_version: str,
        api_key: str,
        lane_id: str,
        *,
        client: Any | None = None,
    ) -> None:
        super().__init__(model_name, template_version)
        if not api_key:
            raise ValueError(f"Gemini credential is missing for lane {lane_id}")

        self.lane_id = lane_id
        if client is not None:
            self._client = client
            return

        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - exercised only in a broken runtime install
            raise RuntimeError("google-genai is required when the Gemini provider is enabled") from exc

        self._client = genai.Client(api_key=api_key)

    async def summarize_batch(
        self,
        document_id: str,
        records: list[InputRecord],
        summary_style: str,
    ) -> list[SummaryArtifactLine]:
        prompt = self._build_prompt(records)
        response = await self._client.aio.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config={
                "response_mime_type": "application/json",
                "response_json_schema": GeminiSummaryPayload.model_json_schema(),
            },
        )
        payload = self._parse_response(response)
        usage = self._usage_metadata(response)
        records_by_id = {record.record_id: record for record in records}
        created_at = datetime.now(timezone.utc).isoformat()

        return [
            SummaryArtifactLine(
                document_id=document_id,
                record_id=item.record_id,
                stable_id=(
                    records_by_id[item.record_id].stable_id
                    if item.record_id in records_by_id
                    else None
                ),
                source_hash=item.source_hash,
                summary_text=item.summary_text,
                summary_style=summary_style,
                provider="gemini",
                model=self.model_name,
                template_version=self.template_version,
                status=item.status,
                created_at=created_at,
                usage=usage,
            )
            for item in payload.summaries
        ]

    @staticmethod
    def _build_prompt(records: list[InputRecord]) -> str:
        input_payload = {
            "records": [
                {
                    "record_id": record.record_id,
                    "source_hash": record.source_hash,
                    "text": record.text,
                }
                for record in records
            ]
        }
        rules = """You are summarizing paragraph records for retrieval.

Return JSON only.

For every input record, return exactly one output item.

Each output item must include:
- record_id
- source_hash
- summary_text
- status

Rules:
- exactly one sentence
- no markdown
- no citations
- no bullet points
- do not add facts not present in the paragraph
- preserve technical terms
- do not omit records
- do not invent record IDs
- copy record_id and source_hash exactly
- if the paragraph is empty or unreadable, return status="skipped" and a short empty/unreadable message
"""
        return f"{rules}\nInput records:\n{json.dumps(input_payload, ensure_ascii=False)}"

    @staticmethod
    def _parse_response(response: Any) -> GeminiSummaryPayload:
        try:
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, GeminiSummaryPayload):
                return parsed
            if parsed is not None:
                return GeminiSummaryPayload.model_validate(parsed)

            response_text = getattr(response, "text", None)
            if not isinstance(response_text, str) or not response_text.strip():
                raise ValueError("Gemini response did not contain JSON text")
            return GeminiSummaryPayload.model_validate_json(response_text)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise StructuredOutputParseError(
                "Gemini structured output could not be parsed"
            ) from exc

    @staticmethod
    def _usage_metadata(response: Any) -> dict[str, int]:
        metadata = getattr(response, "usage_metadata", None)
        if metadata is None:
            return {}

        def value_for(name: str) -> Any:
            if isinstance(metadata, dict):
                return metadata.get(name)
            return getattr(metadata, name, None)

        field_map = {
            "prompt_tokens": "prompt_token_count",
            "completion_tokens": "candidates_token_count",
            "total_tokens": "total_token_count",
        }
        usage: dict[str, int] = {}
        for output_name, source_name in field_map.items():
            value = value_for(source_name)
            if isinstance(value, int):
                usage[output_name] = value
        return usage
