"""Capture OpenBox evaluation responses for the local operator UI."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from enum import Enum
from threading import Lock
from types import MethodType
from typing import Any


class OpenBoxEvaluationRecorder:
    """Store evaluate-endpoint responses and fallback errors by tool-call ID."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._reasons: dict[str, str] = {}
        self._evaluations: dict[str, dict[str, Any]] = {}

    def record(self, tool_call_id: str, reason: str) -> None:
        with self._lock:
            self._reasons[tool_call_id] = reason

    def reason_for(self, tool_call_id: str) -> str | None:
        with self._lock:
            return self._reasons.get(tool_call_id)

    def record_evaluation(self, tool_call_id: str, response: dict[str, Any]) -> None:
        with self._lock:
            self._evaluations[tool_call_id] = deepcopy(response)
            reason = response.get("reason")
            if isinstance(reason, str) and reason.strip():
                self._reasons[tool_call_id] = reason.strip()

    def evaluation_for(self, tool_call_id: str) -> dict[str, Any] | None:
        with self._lock:
            response = self._evaluations.get(tool_call_id)
            return deepcopy(response) if response is not None else None

    def record_exception(self, tool_call_id: str, error: BaseException) -> None:
        """Save an SDK error before later telemetry can replace it."""
        reason = str(error).strip()
        if reason:
            self.record(tool_call_id, reason)


def observe_openbox_start_results(governed: Any, recorder: OpenBoxEvaluationRecorder) -> bool:
    """Copy each tool-start evaluation response without changing SDK enforcement."""

    bridge = getattr(governed, "_activity_bridge", None)
    original_stash = getattr(bridge, "stash_start_result", None)
    bridge_get = getattr(bridge, "get", None)
    if bridge is None or not callable(original_stash) or not callable(bridge_get):
        return False

    def recording_stash(
        current_bridge: Any,
        workflow_id: str,
        activity_id: str,
        result: Any,
    ) -> None:
        original_stash(workflow_id, activity_id, result)
        try:
            record = current_bridge.get(workflow_id, activity_id)
            tool_call_id = getattr(record, "tool_call_id", None)
            if isinstance(tool_call_id, str):
                recorder.record_evaluation(tool_call_id, _evaluation_response(result))
        except Exception:
            # Display enrichment cannot affect enforcement.
            return

    bridge.stash_start_result = MethodType(recording_stash, bridge)
    return True


def _evaluation_response(result: Any) -> dict[str, Any]:
    """Return the exact HTTP response when available, with a typed fallback for tests."""

    raw = getattr(result, "raw", None)
    if isinstance(raw, dict) and raw:
        return deepcopy(raw)

    response: dict[str, Any] = {}
    fields = {
        "verdict": "verdict",
        "reason": "reason",
        "policy_id": "policy_id",
        "risk_score": "risk_score",
        "metadata": "metadata",
        "governance_event_id": "governance_event_id",
        "guardrails_result": "guardrails",
        "approval_id": "approval_id",
        "approval_expiration_time": "approval_expiration_time",
        "trust_tier": "trust_tier",
        "alignment_score": "alignment_score",
        "behavioral_violations": "behavioral_violations",
        "constraints": "constraints",
        "fallback_used": "fallback_used",
        "diagnostics": "diagnostics",
        "patch": "patch",
    }
    for response_key, attribute_name in fields.items():
        value = getattr(result, attribute_name, None)
        if value is not None:
            response[response_key] = _json_safe(value)
    return response


def _json_safe(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(child) for child in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
