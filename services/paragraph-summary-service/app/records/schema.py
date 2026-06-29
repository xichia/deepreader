from typing import Any, Optional
from pydantic import BaseModel

class RecordMetadata(BaseModel):
    page: Optional[int] = None
    paragraph_index: Optional[int] = None
    status: Optional[str] = None

class InputRecord(BaseModel):
    record_id: str
    stable_id: Optional[str] = None
    source_ref: Optional[str] = None
    text: str
    source_hash: str
    metadata: RecordMetadata = RecordMetadata()

class SummaryRequest(BaseModel):
    document_id: str
    records: list[InputRecord]
    summary_style: str = "one_sentence"
    priority: str = "interactive"

class SummaryArtifactLine(BaseModel):
    document_id: str
    record_id: str
    stable_id: Optional[str] = None
    source_hash: str
    summary_text: str
    summary_style: str
    provider: str
    model: str
    template_version: str
    status: str
    error_code: Optional[str] = None
    usage: dict[str, Any] = {}
    created_at: str
