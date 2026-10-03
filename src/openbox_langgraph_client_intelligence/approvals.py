"""Surface OpenBox approval waits to the local operator UI without changing enforcement."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from openbox_langgraph import GovernanceBlockedError

ApprovalEventSink = Callable[[str, dict[str, Any]], None]

# The step context an approval event carries, copied from the step that triggered it.
_CONTEXT_KEYS = frozenset(
    {
        "lead",
        "purpose",
        "lead_number",
        "lead_count",
        "document_id",
        "title",
        "target_label",
        "client_name",
        "destination_document_id",
        "attempt_number",
        "attempt_count",
    }
)
_CONTEXT_EVENTS = frozenset({"read_started", "upload_started", "write_started"})


def awaits_approval(error: BaseException) -> bool:
    """True when the SDK raised this to pause for a human approval decision."""

    current: BaseException | None = error
    for _ in range(8):
        if current is None:
            return False
        if (
            isinstance(current, GovernanceBlockedError)
            and getattr(current, "verdict", None) == "require_approval"
        ):
            return True
        current = current.__cause__ or current.__context__
    return False


class ApprovalTracker:
    """Turn the SDK's approval wait into approval_requested / approval_granted events."""

    def __init__(self, emit: ApprovalEventSink) -> None:
        self._emit = emit
        self._context: dict[str, Any] = {}
        self._reason: str | None = None

    def observe(self, event_type: str, data: dict[str, Any]) -> None:
        """Remember which step is running, so an approval can name it."""

        if event_type in _CONTEXT_EVENTS:
            self._context = {key: value for key, value in data.items() if key in _CONTEXT_KEYS}
            self._reason = None

    def record_request(self, error: BaseException) -> None:
        if awaits_approval(error):
            reason = str(error).strip()
            self._reason = reason or None

    def record_reason(self, reason: object) -> None:
        text = str(reason or "").strip()
        if text:
            self._reason = text

    def wait_started(self, activity_type: str) -> None:
        self._emit(
            "approval_requested",
            {
                **self._context,
                "activity_type": activity_type,
                "reason": self._reason or "OpenBox requires approval for this step",
            },
        )

    def wait_finished(self, activity_type: str) -> None:
        self._emit("approval_granted", {**self._context, "activity_type": activity_type})


def observe_approval_waits(tracker: ApprovalTracker) -> bool:
    """Wrap the SDK's approval pollers so each wait's start and approval are reported.

    The SDK waits in two places: the graph-level poller, and (from 1.2.0) in place at the
    governed tool call. The polls themselves, their interval, and what happens on rejection
    or expiry are the SDK's; the wrappers only report around them and never swallow an
    outcome.
    """

    observed_graph = _observe_graph_poll(tracker)
    observed_activity = _observe_activity_waits(tracker)
    return observed_graph or observed_activity


def _observe_graph_poll(tracker: ApprovalTracker) -> bool:
    try:
        from openbox_langgraph import langgraph_handler
    except ImportError:
        return False
    original = getattr(langgraph_handler, "poll_until_decision", None)
    if not callable(original) or getattr(original, "_barrier_demo_observed", False):
        return False

    async def observed_poll(client: Any, params: Any, config: Any) -> None:
        activity_type = str(getattr(params, "activity_type", "") or "activity")
        _safely(tracker.wait_started, activity_type)
        await original(client, params, config)
        _safely(tracker.wait_finished, activity_type)

    observed_poll._barrier_demo_observed = True  # type: ignore[attr-defined]
    langgraph_handler.poll_until_decision = observed_poll
    return True


def _observe_activity_waits(tracker: ApprovalTracker) -> bool:
    try:
        from openbox_langgraph.activity_approval import ActivityApprovalWaiter
    except ImportError:
        return False
    original_wait = getattr(ActivityApprovalWaiter, "wait", None)
    original_wait_sync = getattr(ActivityApprovalWaiter, "wait_sync", None)
    if not callable(original_wait) or getattr(original_wait, "_barrier_demo_observed", False):
        return False

    # The sync and async tool callbacks can both wait on the same evaluation; the second
    # call reuses the first decision, so report each evaluation only once.
    reported: set[tuple[str, int]] = set()

    def first_wait(result: Any, ctx: Any) -> str | None:
        key = (str(getattr(ctx, "activity_id", "")), id(result))
        if key in reported:
            return None
        reported.add(key)
        activity_type = str(getattr(ctx, "activity_type", "") or "activity")
        _safely(lambda _: tracker.record_reason(getattr(result, "reason", None)), activity_type)
        _safely(tracker.wait_started, activity_type)
        return activity_type

    async def observed_wait(self: Any, result: Any, ctx: Any) -> None:
        activity_type = first_wait(result, ctx)
        await original_wait(self, result, ctx)
        if activity_type:
            _safely(tracker.wait_finished, activity_type)

    def observed_wait_sync(self: Any, result: Any, ctx: Any) -> None:
        activity_type = first_wait(result, ctx)
        original_wait_sync(self, result, ctx)
        if activity_type:
            _safely(tracker.wait_finished, activity_type)

    observed_wait._barrier_demo_observed = True  # type: ignore[attr-defined]
    observed_wait.__wrapped__ = original_wait  # type: ignore[attr-defined]
    observed_wait_sync.__wrapped__ = original_wait_sync  # type: ignore[attr-defined]
    ActivityApprovalWaiter.wait = observed_wait  # type: ignore[method-assign]
    if callable(original_wait_sync):
        ActivityApprovalWaiter.wait_sync = observed_wait_sync  # type: ignore[method-assign]
    return True


def _safely(callback: Callable[[str], None], activity_type: str) -> None:
    try:
        callback(activity_type)
    except Exception:
        # Display enrichment cannot affect enforcement.
        return
