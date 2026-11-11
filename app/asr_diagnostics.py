"""Sanitized, opt-in details for local CPU ASR errors.

The default API/CLI errors intentionally omit underlying library messages. These
local diagnostics redact URLs and common credential forms before printing.
"""
from __future__ import annotations

import re


_URL = re.compile(r"\b(?:https?|ftp)://[^\s<>\"']+", re.IGNORECASE)
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+", re.IGNORECASE)
_TOKEN = re.compile(r"\b(?:hf_|ghp_|sk-)[A-Za-z0-9_-]{6,}\b", re.IGNORECASE)
_SECRET_KV = re.compile(
    r"\b(authorization|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*\S+",
    re.IGNORECASE,
)


def sanitize_asr_message(value: object) -> str:
    """One short printable line without signed URLs or common tokens."""
    message = " ".join(str(value).split())
    message = _URL.sub("[redacted URL]", message)
    message = _BEARER.sub("Bearer [redacted]", message)
    message = _TOKEN.sub("[redacted token]", message)
    message = _SECRET_KV.sub(lambda found: found.group(1) + "=[redacted]", message)
    return message[:300] if message else "(no exception message)"


def asr_failure_details(error: BaseException) -> dict[str, str]:
    """Identify the underlying exception; never include traceback or media data."""
    root = error
    visited: set[int] = set()
    for _ in range(8):
        visited.add(id(root))
        next_error = root.__cause__ or (
            root.__context__ if not root.__suppress_context__ else None
        )
        if next_error is None or id(next_error) in visited:
            break
        root = next_error
    return {
        "exception_type": type(root).__name__,
        "exception_message": sanitize_asr_message(root),
    }
