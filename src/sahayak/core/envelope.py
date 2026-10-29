"""Standard MCP tool response envelope with safety guards.

Every tool response uses ``ok()`` or ``fail()`` to produce a uniform shape
matching PRD §9.3.  Guards enforce ``SPOKEN_SUMMARY_MAX_CHARS`` and
``MAX_RESPONSE_BYTES`` so oversized responses never reach Alexa+.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sahayak.core.config import get_settings
from sahayak.core.errors import SahayakError
from sahayak.core.request_id import get_request_id

# Characters forbidden in spoken output (markdown, emojis, URLs, symbols).
_SPOKEN_BAD_PATTERN = re.compile(
    r"[*_~`#\[\](){}<>|\\]"  # markdown
    r"|https?://"  # URLs
    r"|[\U0001F600-\U0001FAFF]",  # common emoji ranges
    re.UNICODE,
)


def _clean_spoken(text: str) -> str:
    """Strip markdown, URLs, and symbols from spoken text."""
    return _SPOKEN_BAD_PATTERN.sub("", text).strip()


def _truncate_spoken(text: str, max_chars: int) -> str:
    """Truncate spoken summary to the configured character limit."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "\u2026"


def _enforce_size(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    """Truncate ``data`` values if the serialized envelope exceeds the cap."""
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode()) <= max_bytes:
        return payload
    # Drop data to fit; keep the rest of the envelope intact.
    payload["data"] = {"_truncated": True}
    payload["meta"]["truncated"] = True
    return payload


def ok(
    spoken_summary: str,
    data: dict[str, Any] | None = None,
    *,
    next_actions: list[str] | None = None,
    module: str = "",
    version: str = "0.0.0",
    ui: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a successful tool response envelope.

    Args:
        spoken_summary: Short, voice-friendly description of the result.
        data: Tool-specific structured payload.
        next_actions: Suggested follow-up actions for the user.
        module: Owning module name for the meta block.
        version: Module version string.
        ui: Optional Alexa+ UI metadata (resourceUri, invoking, invoked).

    Returns:
        A dictionary matching the PRD §9.3 envelope shape.

    Raises:
        ValueError: If ``spoken_summary`` contains forbidden characters after
            cleaning.
    """
    settings = get_settings()
    cleaned = _clean_spoken(spoken_summary)
    spoken = _truncate_spoken(cleaned, settings.spoken_summary_max_chars)

    meta: dict[str, Any] = {
        "request_id": get_request_id() or "",
        "module": module,
        "version": version,
    }
    if ui:
        meta["ui"] = ui

    payload: dict[str, Any] = {
        "ok": True,
        "spoken_summary": spoken,
        "data": data or {},
        "next_actions": next_actions or [],
        "meta": meta,
    }
    return _enforce_size(payload, settings.max_response_bytes)


def fail(
    error: SahayakError,
    *,
    module: str = "",
    version: str = "0.0.0",
    ui: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build an error tool response envelope from a ``SahayakError``.

    Args:
        error: The domain or service error to surface.
        module: Owning module name for the meta block.
        version: Module version string.
        ui: Optional Alexa+ UI metadata.

    Returns:
        A dictionary with ``ok=False`` and the stable error code.
    """
    settings = get_settings()
    spoken = _truncate_spoken(
        _clean_spoken(error.spoken),
        settings.spoken_summary_max_chars,
    )

    meta: dict[str, Any] = {
        "request_id": get_request_id() or "",
        "module": module,
        "version": version,
    }
    if ui:
        meta["ui"] = ui

    payload: dict[str, Any] = {
        "ok": False,
        "error_code": error.code,
        "spoken_summary": spoken,
        "data": {},
        "next_actions": [],
        "meta": meta,
    }
    return _enforce_size(payload, settings.max_response_bytes)


def lint_spoken(text: str) -> list[str]:
    """Return a list of problems found in a spoken summary string.

    Use in tests to assert that spoken text is voice-safe.
    """
    problems: list[str] = []
    if _SPOKEN_BAD_PATTERN.search(text):
        problems.append("contains markdown, URLs, or symbols")
    if len(text) > get_settings().spoken_summary_max_chars:
        problems.append("exceeds SPOKEN_SUMMARY_MAX_CHARS")
    return problems
