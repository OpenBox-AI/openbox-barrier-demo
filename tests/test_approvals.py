from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from openbox_core.contracts.context import ActivityContext
from openbox_core.contracts.results import ApprovalResult, EvaluationResult, Verdict
from openbox_langgraph import ApprovalRejectedError, GovernanceBlockedError, langgraph_handler
from openbox_langgraph.activity_approval import ActivityApprovalWaiter
from openbox_langgraph.types import HITLConfig
from test_workflow import (
    ScriptedFilingRepository,
    StubModel,
    _populate_library,
)

from openbox_langgraph_client_intelligence.approvals import (
    ApprovalTracker,
    _observe_activity_waits,
    awaits_approval,
    observe_approval_waits,
)
from openbox_langgraph_client_intelligence.profiles import get_profile
from openbox_langgraph_client_intelligence.run_manager import RunRecord, WorkflowRunManager
from openbox_langgraph_client_intelligence.tools import build_document_tools
from openbox_langgraph_client_intelligence.workflow import build_research_graph, initial_state


def _approval_request(reason: str = "Compliance must approve this read") -> GovernanceBlockedError:
    # The shape the SDK's core adapter raises for a hook-level REQUIRE_APPROVAL.
    return GovernanceBlockedError("require_approval", reason, "0001/20001/Pepsi_MA.md")


class ApprovalPendingReadRepository(ScriptedFilingRepository):
    def read(self, document_id: str) -> str:
        if "Pepsi" in document_id:
            raise _approval_request()
        return super().read(document_id)


class ApprovalPropagationTests(unittest.TestCase):
    def _graph(self, repository, profile_slug: str, events: list):
        profile = get_profile(profile_slug)
        graph = build_research_graph(
            profile,
            build_document_tools(repository, agent_slug=profile_slug),
            StubModel(),
            event_sink=lambda event_type, data: events.append((event_type, data)),
        )
        return profile, graph

    def test_read_approval_request_leaves_the_graph_for_the_sdk_to_poll(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            library.mkdir()
            _populate_library(library)
            repository = ApprovalPendingReadRepository(
                library, root / "output", root / "filed_documents"
            )
            events: list[tuple[str, dict]] = []
            profile, graph = self._graph(repository, "amy", events)

            with self.assertRaises(GovernanceBlockedError) as raised:
                asyncio.run(graph.ainvoke(initial_state(profile)))

            self.assertEqual(raised.exception.verdict, "require_approval")
            event_types = [event_type for event_type, _ in events]
            self.assertNotIn("read_blocked", event_types)
            self.assertNotIn("synthesis_started", event_types)

    def test_filing_approval_request_stops_the_sweep_instead_of_recording_a_block(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            library.mkdir()
            _populate_library(library)
            repository = ScriptedFilingRepository(
                library,
                root / "output",
                root / "filed_documents",
                filing_failures={
                    1: GovernanceBlockedError("block", "Barrier", "0001/10001"),
                    2: _approval_request("Compliance must approve this filing"),
                },
            )
            events: list[tuple[str, dict]] = []
            profile, graph = self._graph(repository, "barry", events)

            with self.assertRaises(GovernanceBlockedError) as raised:
                asyncio.run(graph.ainvoke(initial_state(profile)))

            self.assertEqual(raised.exception.verdict, "require_approval")
            self.assertEqual(len(repository.filing_attempts), 2)
            upload_events = [
                event_type for event_type, _ in events if event_type.startswith("upload_")
            ]
            # The ordinary BLOCK on attempt 1 is still recorded; attempt 2 is left pending.
            self.assertEqual(upload_events, ["upload_started", "upload_blocked", "upload_started"])

    def test_wrapped_approval_request_is_recognised(self) -> None:
        try:
            try:
                raise _approval_request()
            except GovernanceBlockedError as inner:
                raise RuntimeError("tool wrapper") from inner
        except RuntimeError as outer:
            self.assertTrue(awaits_approval(outer))
        self.assertFalse(awaits_approval(GovernanceBlockedError("block", "Barrier", "x")))


class ApprovalWaitReportingTests(unittest.TestCase):
    def _observe(self, original):
        events: list[tuple[str, dict]] = []
        tracker = ApprovalTracker(lambda event_type, data: events.append((event_type, data)))
        tracker.observe(
            "read_started",
            {"lead": "related-pepsi", "document_id": "0001/20001/Pepsi.docx", "query": "x"},
        )
        tracker.record_request(_approval_request())
        with patch.object(langgraph_handler, "poll_until_decision", original):
            self.assertTrue(observe_approval_waits(tracker))
            poll = langgraph_handler.poll_until_decision
        return events, poll

    def test_wait_is_reported_when_it_starts_and_when_it_is_approved(self) -> None:
        async def approves(client, params, config):
            return None

        events, poll = self._observe(approves)
        asyncio.run(poll(None, SimpleNamespace(activity_type="hook"), None))

        self.assertEqual(
            [event_type for event_type, _ in events], ["approval_requested", "approval_granted"]
        )
        requested = events[0][1]
        self.assertEqual(requested["document_id"], "0001/20001/Pepsi.docx")
        self.assertEqual(requested["reason"], "Compliance must approve this read")
        self.assertNotIn("query", requested)

    def test_rejection_reaches_the_caller_unchanged(self) -> None:
        async def rejects(client, params, config):
            raise ApprovalRejectedError("Rejected by compliance")

        events, poll = self._observe(rejects)
        with self.assertRaises(ApprovalRejectedError):
            asyncio.run(poll(None, SimpleNamespace(activity_type="hook"), None))

        self.assertEqual([event_type for event_type, _ in events], ["approval_requested"])


class InPlaceApprovalWaitReportingTests(unittest.TestCase):
    """SDK 1.2.0 waits at the governed tool call instead of the graph-level poller."""

    def _waiter(self, responses: list):
        class Client:
            async def apoll_approval(self, workflow_id, run_id, activity_id):
                return responses.pop(0)

        events: list[tuple[str, dict]] = []
        tracker = ApprovalTracker(lambda event_type, data: events.append((event_type, data)))
        tracker.observe("upload_started", {"client_name": "PepsiCo", "attempt_number": 2})
        # Start from the SDK's own methods, even if another test already wrapped them.
        sdk_wait = getattr(ActivityApprovalWaiter.wait, "__wrapped__", ActivityApprovalWaiter.wait)
        sdk_wait_sync = getattr(
            ActivityApprovalWaiter.wait_sync, "__wrapped__", ActivityApprovalWaiter.wait_sync
        )
        with (
            patch.object(ActivityApprovalWaiter, "wait", sdk_wait),
            patch.object(ActivityApprovalWaiter, "wait_sync", sdk_wait_sync),
        ):
            self.assertTrue(_observe_activity_waits(tracker))
            waiter = ActivityApprovalWaiter(Client(), HITLConfig(poll_interval_ms=1))
            waiter.begin_turn("wf", "run")
            ctx = ActivityContext(
                workflow_id="wf", run_id="run", activity_id="a1", activity_type="upload_document"
            )
            result = EvaluationResult(verdict=Verdict.REQUIRE_APPROVAL, reason="Filing review")
            yield waiter, result, ctx
        self.events = events

    def test_wait_is_reported_once_with_its_step_and_reason(self) -> None:
        for waiter, result, ctx in self._waiter(
            [ApprovalResult(), ApprovalResult(verdict=Verdict.ALLOW)]
        ):
            asyncio.run(waiter.wait(result, ctx))
            # The other tool callback reuses the decision; it must not be reported again.
            asyncio.run(waiter.wait(result, ctx))

        self.assertEqual(
            [event_type for event_type, _ in self.events],
            ["approval_requested", "approval_granted"],
        )
        requested = self.events[0][1]
        self.assertEqual(requested["client_name"], "PepsiCo")
        self.assertEqual(requested["reason"], "Filing review")
        self.assertEqual(requested["activity_type"], "upload_document")

    def test_rejection_reaches_the_tool_unchanged(self) -> None:
        for waiter, result, ctx in self._waiter([ApprovalResult(verdict=Verdict.BLOCK)]):
            with self.assertRaises(ApprovalRejectedError):
                asyncio.run(waiter.wait(result, ctx))

        self.assertEqual([event_type for event_type, _ in self.events], ["approval_requested"])


class ApprovalStatusTests(unittest.TestCase):
    def test_run_shows_awaiting_approval_until_it_resumes(self) -> None:
        manager = WorkflowRunManager(project_root=Path(tempfile.gettempdir()))
        record = RunRecord(
            run_id="run-1",
            agent_slug="amy",
            multi_agent_session_id="session",
            created_at="2026-10-02T00:00:00+00:00",
        )

        def append(event_type: str, data: dict) -> None:
            manager._append_event(
                record,
                {"type": event_type, "agent_slug": "amy", "timestamp": "t", "data": data},
            )

        append("workflow_started", {})
        append("approval_requested", {"document_id": "0001/20001/Pepsi.docx", "reason": "Approve"})
        self.assertEqual(record.status, "awaiting_approval")
        self.assertEqual(record.current_step, "Requires approval")
        self.assertFalse(record.is_terminal)

        append("approval_granted", {"document_id": "0001/20001/Pepsi.docx"})
        self.assertEqual(record.status, "running")
        self.assertEqual(record.events[-1]["type"], "approval_granted")


if __name__ == "__main__":
    unittest.main()
