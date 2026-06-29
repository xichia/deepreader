from abc import ABC, abstractmethod

from app.records.schema import InputRecord, SummaryArtifactLine

class BaseProvider(ABC):
    def __init__(self, model_name: str, template_version: str):
        self.model_name = model_name
        self.template_version = template_version

    @abstractmethod
    async def summarize_batch(self, document_id: str, records: list[InputRecord], summary_style: str) -> list[SummaryArtifactLine]:
        pass
