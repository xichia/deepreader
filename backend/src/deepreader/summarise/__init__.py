"""Summary generation pipeline for DeepReader."""

from deepreader.summarise.local import LocalExtractiveSummariser
from deepreader.summarise.service import SummaryJobRunner

__all__ = ["LocalExtractiveSummariser", "SummaryJobRunner"]
