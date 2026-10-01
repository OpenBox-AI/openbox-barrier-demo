"""Safe, newline-delimited workflow events for the local operator UI."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from typing import Any

EVENT_PREFIX = "__CLIENT_INTELLIGENCE_EVENT__"
_MAX_MESSAGE_LENGTH = 800
_SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PRIVATE")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_BEARER_TOKEN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_NAMED_SECRET = re.compile(
    r"(?i)\b(api[_ -]?key|private[_ -]?key|access[_ -]?token|secret|password)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_SENSITIVE_PAYLOAD_KEYS = frozenset(
    {
        "accesstoken",
        "agentdid",
        "apikey",
        "authorization",
        "password",
        "privatekey",
        "providerresponse",
        "provideruserid",
        "refreshtoken",
        "rawgovernancepayload",
        "rawresponse",
        "rawwallsresponse",
        "secret",
        "userid",
        "wallsresponse",
        "wallsuserid",
    }
)


def sanitize_operator_message(value: object) -> str:
    """Make an exception or policy reason safe to show in a local browser."""

    text = _CONTROL_CHARACTERS.sub("", str(value)).replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    text = _BEARER_TOKEN.sub("Bearer [redacted]", text)
    text = _NAMED_SECRET.sub(lambda match: f"{match.group(1)}=[redacted]", text)

    for name, secret in os.environ.items():
        if not secret or len(secret) < 8:
            continue
        if any(marker in name.upper() for marker in _SENSITIVE_ENV_MARKERS):
            text = text.replace(secret, "[redacted]")

    if not text:
        return "OpenBox did not provide a displayable reason."
    if len(text) > _MAX_MESSAGE_LENGTH:
        return text[: _MAX_MESSAGE_LENGTH - 1].rstrip() + "…"
    return text


def sanitize_event_data(value: Any, *, key: str = "data") -> Any:
    """Recursively sanitize the display-oriented fields in an event payload."""

    if isinstance(value, dict):
        return {
            str(child_key): (
                "[redacted]"
                if _is_sensitive_payload_key(str(child_key))
                else sanitize_event_data(child, key=str(child_key))
            )
            for child_key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_event_data(child, key=key) for child in value]
    if isinstance(value, str) and key in {"reason", "safe_reason", "message", "error"}:
        return sanitize_operator_message(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return sanitize_operator_message(value)


def _is_sensitive_payload_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.lower())
    return normalized in _SENSITIVE_PAYLOAD_KEYS


class JsonEventWriter:
    """Write prefixed JSON events while retaining no document contents or credentials."""

    def __init__(self, agent_slug: str) -> None:
        self.agent_slug = agent_slug

    def emit(self, event_type: str, data: dict[str, Any] | None = None, **fields: Any) -> None:
        payload = dict(data or {})
        payload.update(fields)
        event = {
            "type": event_type,
            "agent_slug": self.agent_slug,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": sanitize_event_data(payload),
        }
        print(f"{EVENT_PREFIX}{json.dumps(event, ensure_ascii=True, sort_keys=True)}", flush=True)
