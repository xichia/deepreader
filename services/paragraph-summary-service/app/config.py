import os
from pydantic import BaseModel

class Settings(BaseModel):
    summary_service_provider: str = os.getenv("SUMMARY_SERVICE_PROVIDER", "mock")
    summary_service_model: str = os.getenv("SUMMARY_SERVICE_MODEL", "mock-deterministic-v1")
    summary_batch_target_tokens: int = int(os.getenv("SUMMARY_BATCH_TARGET_TOKENS", "240000"))
    summary_batch_hard_max_tokens: int = int(os.getenv("SUMMARY_BATCH_HARD_MAX_TOKENS", "250000"))
    summary_lane_count: int = int(os.getenv("SUMMARY_LANE_COUNT", "10"))
    summary_lane_rpm: int = int(os.getenv("SUMMARY_LANE_RPM", "1"))
    summary_template_version: str = os.getenv("SUMMARY_TEMPLATE_VERSION", "paragraph_one_sentence_v1")

settings = Settings()
