from pathlib import Path

from deepreader.api.main import DEFAULT_CORS_ORIGINS, get_cors_origins
from deepreader.security import REDACTED, redact_mapping, redact_secret


def test_redact_secret_masks_common_api_key_shapes() -> None:
    assert redact_secret("sk-test_abcdefghijklmnopqrstuvwxyz") == REDACTED
    assert redact_secret("a" * 32) == REDACTED
    assert redact_secret("plain-local-setting") == "plain-local-setting"


def test_redact_mapping_masks_sensitive_keys_and_values() -> None:
    redacted = redact_mapping(
        {
            "api_key": "local-test-key",
            "database_url": "sqlite:///./data/deepreader.sqlite3",
            "misc": "sk-test_abcdefghijklmnopqrstuvwxyz",
        }
    )

    assert redacted["api_key"] == REDACTED
    assert redacted["database_url"] == "sqlite:///./data/deepreader.sqlite3"
    assert redacted["misc"] == REDACTED


def test_cors_defaults_are_local_only() -> None:
    assert get_cors_origins() == list(DEFAULT_CORS_ORIGINS)
    assert all(origin.startswith(("http://127.0.0.1:", "http://localhost:")) for origin in DEFAULT_CORS_ORIGINS)


def test_env_example_contains_no_obvious_secrets() -> None:
    env_example = Path(__file__).resolve().parents[2] / ".env.example"
    contents = env_example.read_text(encoding="utf-8")

    assert "sk-" not in contents
    assert "password=" not in contents.lower()
    assert "token=" not in contents.lower()
