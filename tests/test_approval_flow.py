from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from langchain_core.messages import AIMessage
from openbox_core.client import EvaluationClient
from openbox_core.contracts.results import ApprovalResult, EvaluationResult, Verdict
from openbox_langgraph import ApprovalExpiredError, ApprovalRejectedError

from openbox_langgraph_client_intelligence.config import AgentSettings
from openbox_langgraph_client_intelligence.governance import build_governed_agent
from openbox_langgraph_client_intelligence.profiles import get_profile
from openbox_langgraph_client_intelligence.repository import DocumentRepository
from openbox_langgraph_client_intelligence.tools import build_document_tools
from openbox_langgraph_client_intelligence.workflow import build_research_graph, initial_state


class ApprovalFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_read_and_upload_wait_for_sdk_approval(self) -> None:
        for tool_name in ("read_document", "upload_document"):
            with self.subTest(tool=tool_name):
                await self._check_approval_flow(tool_name)

    async def test_rejected_or_expired_approval_does_not_continue_the_graph(self) -> None:
        for tool_name in ("read_document", "upload_document"):
            for failure in (ApprovalRejectedError("Rejected"), ApprovalExpiredError("Expired")):
                with self.subTest(tool=tool_name, error=type(failure).__name__):
                    await self._check_approval_flow(tool_name, failure)

    async def _check_approval_flow(self, tool_name: str, failure: Exception | None = None) -> None:
        loop = asyncio.get_running_loop()
        waiting: asyncio.Queue[int] = asyncio.Queue()
        decisions: set[int] = set()
        polled: set[str] = set()
        pending_activity_ids: list[str] = []
        events: list[str] = []

        def evaluate(client, payload):
            pending = (
                payload.get("event_type") == "ActivityStarted"
                and payload.get("activity_type") == tool_name
                and not payload.get("hook_trigger")
            )
            if pending:
                pending_activity_ids.append(payload["activity_id"])
            return EvaluationResult(
                verdict=Verdict.REQUIRE_APPROVAL if pending else Verdict.ALLOW,
                reason="Approval pending" if pending else "Allowed",
            )

        async def aevaluate(client, payload):
            return evaluate(client, payload)

        def poll(client, workflow_id, run_id, activity_id):
            index = pending_activity_ids.index(activity_id)
            if activity_id not in polled:
                polled.add(activity_id)
                loop.call_soon_threadsafe(waiting.put_nowait, index)
            if index not in decisions:
                return ApprovalResult()
            if isinstance(failure, ApprovalExpiredError):
                return ApprovalResult(expired=True)
            if failure is not None:
                return ApprovalResult(verdict=Verdict.BLOCK, reason=str(failure))
            return ApprovalResult(verdict=Verdict.ALLOW)

        async def apoll(client, workflow_id, run_id, activity_id):
            return poll(client, workflow_id, run_id, activity_id)

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            library.mkdir()
            for name in ("Coca_Cola_MA.md", "Pepsi_MA.md", "Bank_of_America_CEO.md"):
                (library / name).write_text("Offline test evidence", encoding="utf-8")
            repository = DocumentRepository(library, root / "output", root / "filed")
            profile = get_profile("amy")
            graph = build_research_graph(
                profile,
                build_document_tools(repository, agent_slug="amy"),
                SimpleNamespace(ainvoke=AsyncMock(return_value=AIMessage(content="# Briefing"))),
                event_sink=lambda event_type, data: events.append(event_type),
            )
            settings = AgentSettings(
                profile_slug="amy",
                openbox_url="https://core.example.test",
                openbox_api_key="obx_test_offline_approval_test",
                openbox_agent_name="ApprovalTest",
                openbox_agent_did=None,
                openbox_agent_private_key=None,
                openbox_validate=False,
                openai_model="offline-model",
                document_library_dir=library,
                report_output_dir=root / "output",
                filed_documents_dir=root / "filed",
            )

            # Exercise the installed SDK's callbacks and real approval loop.
            # Only external evaluations and the human decision are simulated.
            with (
                patch.dict(os.environ, {}, clear=True),
                patch.object(EvaluationClient, "evaluate", evaluate),
                patch.object(EvaluationClient, "aevaluate", aevaluate),
                patch.object(EvaluationClient, "poll_approval", poll),
                patch.object(EvaluationClient, "apoll_approval", apoll),
                patch.object(
                    httpx.Client, "send", side_effect=AssertionError("Unexpected network")
                ),
                patch.object(
                    httpx.AsyncClient, "send", side_effect=AssertionError("Unexpected network")
                ),
            ):
                governed = build_governed_agent(
                    graph, profile, settings, session_id="test", multi_agent_session_id="test"
                )
                governed._config.hitl.poll_interval_ms = 5
                task = asyncio.create_task(
                    governed.ainvoke(
                        initial_state(profile),
                        config={"configurable": {"thread_id": "test"}, "recursion_limit": 50},
                    )
                )
                try:
                    count = (
                        len(profile.leads)
                        if tool_name == "read_document"
                        else len(profile.filing_targets)
                    )
                    for index in range(count if failure is None else 1):
                        self.assertEqual(await asyncio.wait_for(waiting.get(), timeout=2), index)
                        expected_last = (
                            "read_started" if tool_name == "read_document" else "upload_started"
                        )
                        self.assertEqual(events[-1], expected_last)
                        self.assertEqual(events.count(expected_last), index + 1)
                        events_while_pending = list(events)
                        await asyncio.sleep(0.02)
                        self.assertFalse(task.done())
                        self.assertEqual(events, events_while_pending)
                        expected_files = index if tool_name == "upload_document" else 0
                        self.assertEqual(len(list((root / "filed").rglob("*.md"))), expected_files)
                        decisions.add(index)

                    if failure is None:
                        result = await asyncio.wait_for(task, timeout=3)
                        self.assertEqual(len(result["evidence"]), len(profile.leads))
                        self.assertEqual(result["unavailable"], [])
                        self.assertEqual(len(pending_activity_ids), count)
                        self.assertEqual(len(polled), count)
                        self.assertEqual(events.count("search_started"), len(profile.leads))
                        self.assertEqual(events.count("read_started"), len(profile.leads))
                        self.assertEqual(events.count("write_started"), 1)
                        self.assertEqual(
                            events.count("upload_started"), len(profile.filing_targets)
                        )
                        self.assertEqual(
                            [item["status"] for item in result["filing_results"]],
                            ["committed"] * len(profile.filing_targets),
                        )
                    else:
                        with self.assertRaises(type(failure)):
                            await asyncio.wait_for(task, timeout=3)
                        self.assertEqual(events, events_while_pending)
                        self.assertEqual(list((root / "filed").rglob("*.md")), [])
                finally:
                    if not task.done():
                        task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    await governed._core_runtime.aclose()


if __name__ == "__main__":
    unittest.main()
