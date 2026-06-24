"""Summary provider interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SummaryInput:
    stable_id: str
    source_text: str
    source_hash: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class GeneratedSummary:
    summary_text: str
    summariser_name: str
    summary_hash: str


class Summariser(Protocol):
    name: str

    def summarise(self, item: SummaryInput) -> GeneratedSummary:
        """Create a deterministic summary for one source record."""
