"""Small security hygiene helpers for logs and diagnostics."""

from __future__ import annotations

import re
from collections.abc import Mapping

SECRET_KEY_RE = re.compile(r"(api[_-]?key|token|secret|password|credential)", re.IGNORECASE)
SECRET_VALUE_PREFIXES = ("sk-", "sk_live_", "sk_test_")
REDACTED = "[redacted]"


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
