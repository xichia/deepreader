"""Small security hygiene helpers for logs and diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping

SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|credential)", re.IGNORECASE)
SECRET_VALUE_PREFIXES = ("sk-", "sk_live_", "sk_test_")
REDACTED = "[redacted]"
MAX_DIAGNOSTIC_CHARS = 500
SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|credential|password|secret|token|x-goog-api-key)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
GOOGLE_API_KEY_RE = re.compile(r"AIza[0-9A-Za-z_-]{16,}")


def redact_secret(value: object) -> object:
    """Return a redacted placeholder for strings that look like secrets."""

    if not isinstance(value, str):
        return value

    stripped = value.strip()
    if not stripped:
        return value

    if stripped.startswith(SECRET_VALUE_PREFIXES):
        return REDACTED

    if len(stripped) >= 24 and re.fullmatch(r"[A-Za-z0-9_\-]+", stripped):
        return REDACTED

    return value


def redact_mapping(values: Mapping[str, object]) -> dict[str, object]:
    """Redact secret-looking keys or values from a shallow mapping."""

    redacted: dict[str, object] = {}
    for key, value in values.items():
        if SECRET_KEY_RE.search(key):
            redacted[key] = REDACTED if value not in (None, "") else value
        else:
            redacted[key] = redact_secret(value)
    return redacted


def sanitize_diagnostic_text(value: object) -> str:
    """Return bounded diagnostic text with common credentials and payloads removed."""

    text = re.sub(r"\s+", " ", str(value)).strip()
    text = GOOGLE_API_KEY_RE.sub(REDACTED, text)
    text = SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}={REDACTED}", text)
    text = re.sub(
        r"(?i)\b(input records|prompt|request body|contents)\s*[:=].*$",
        lambda match: f"{match.group(1)}=[omitted]",
        text,
    )
    if len(text) > MAX_DIAGNOSTIC_CHARS:
        return f"{text[: MAX_DIAGNOSTIC_CHARS - 3]}..."
    return text
