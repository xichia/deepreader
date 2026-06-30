import asyncio
from datetime import datetime, timezone
from app.providers.base import BaseProvider
from app.records.schema import InputRecord, SummaryArtifactLine
from app.config import settings

class MockProvider(BaseProvider):
    async def summarize_batch(self, document_id: str, records: list[InputRecord], summary_style: str) -> list[SummaryArtifactLine]:
        if settings.summary_mock_provider_delay_ms > 0:
            await asyncio.sleep(settings.summary_mock_provider_delay_ms / 1000.0)
        results = []
        for r in records:
            # Deterministic one-sentence summary
            words = r.text.split()
            # If the text is empty or marker, just handle it
            if not words or r.metadata.status == "empty_or_skipped":
                summary_text = "[Empty or unreadable page]"
                status = "skipped"
            else:
                summary_text = " ".join(words[:10]) + " (mock summary)."
                status = "completed"

            line = SummaryArtifactLine(
                document_id=document_id,
                record_id=r.record_id,
                stable_id=r.stable_id,
                source_hash=r.source_hash,
                summary_text=summary_text,
                summary_style=summary_style,
                provider="mock",
                model=self.model_name,
                template_version=self.template_version,
                status=status,
                created_at=datetime.now(timezone.utc).isoformat(),
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            )
            results.append(line)
        return results
