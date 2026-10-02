from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, ToolMessage
from openbox_core.errors import GovernanceAPIError
from openbox_langgraph import (
    ApprovalExpiredError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    GovernanceBlockedError,
    GovernanceHaltError,
)

from openbox_langgraph_client_intelligence.governance_reasons import (
    OpenBoxEvaluationRecorder,
)
from openbox_langgraph_client_intelligence.profiles import get_profile
from openbox_langgraph_client_intelligence.repository import DocumentRepository
from openbox_langgraph_client_intelligence.tools import build_document_tools
from openbox_langgraph_client_intelligence.workflow import build_research_graph, initial_state


class StubModel:
    def __init__(self) -> None:
        self.last_messages = []

    async def ainvoke(self, messages, config=None):
        self.last_messages = messages
        return AIMessage(content="# Briefing\n\nSynthesized only from returned evidence.")


class SelectivelyUnavailableRepository(DocumentRepository):
    def read(self, document_id: str) -> str:
        if "Coca" in document_id:
            raise PermissionError("source unavailable")
        return super().read(document_id)


class SelectivelyGovernedRepository(DocumentRepository):
    def read(self, document_id: str) -> str:
        if "Coca" in document_id:
            raise GovernanceBlockedError("Cross-client read denied by client-isolation policy")
        return super().read(document_id)


class ScriptedFilingRepository(DocumentRepository):
    def __init__(self, *args, filing_failures: dict[int, BaseException] | None = None) -> None:
        super().__init__(*args)
        self.filing_failures = filing_failures or {}
        self.filing_attempts: list[str] = []

    def file_report(self, agent_slug: str, destination_document_id: str) -> Path:
        self.filing_attempts.append(destination_document_id)
        attempt_number = len(self.filing_attempts)
        failure = self.filing_failures.get(attempt_number)
        if failure is not None:
            raise failure
        return super().file_report(agent_slug, destination_document_id)


def _populate_library(library: Path) -> None:
    documents = {
        "Coca_Cola_MA.md": "Coca-Cola transaction evidence",
        "Pepsi_MA.md": "Pepsi transaction evidence",
        "Bank_of_America_CEO.md": "Bank of America leadership evidence",
        "Citi_Bank_Reorganization.md": "Citi reorganization evidence",
    }
    for name, content in documents.items():
        (library / name).write_text(content, encoding="utf-8")


class MaskGovernanceErrorCallback(BaseCallbackHandler):
    raise_error = True

    def __init__(self) -> None:
        self.seen_errors: list[BaseException] = []

    def on_tool_error(self, error, **kwargs) -> None:
        self.seen_errors.append(error)
        raise GovernanceAPIError("Governance API error: HTTP 400") from error


class StopToolCallback(BaseCallbackHandler):
    raise_error = True
    run_inline = True

    def __init__(self, tool_name: str, error: Exception) -> None:
        self.tool_name = tool_name
        self.error = error

    def on_tool_start(self, serialized, input_str, **kwargs) -> None:
        if serialized.get("name") == self.tool_name:
            raise self.error


class WorkflowTests(unittest.TestCase):
    def test_governance_control_errors_escape_every_tool_node(self) -> None:
        stages = {
            "search_documents": "search_started",
            "read_document": "read_started",
            "write_briefing": "write_started",
            "upload_document": "upload_started",
        }
        for tool_name, last_event in stages.items():
            failures = (
                GovernanceBlockedError("require_approval", "Approval pending", "activity-1"),
                GovernanceBlockedError("halt", "Hook halted", "activity-1"),
                GovernanceHaltError("Workflow halted"),
                ApprovalRejectedError("Approval rejected"),
                ApprovalExpiredError("Approval expired"),
                ApprovalTimeoutError(1000),
            )
            for failure in failures:
                with self.subTest(tool=tool_name, error=repr(failure)):
                    with tempfile.TemporaryDirectory() as temp_dir:
                        root = Path(temp_dir)
                        library = root / "library"
                        library.mkdir()
                        _populate_library(library)
                        repository = DocumentRepository(library, root / "output", root / "filed")
                        profile = get_profile("amy")
                        events: list[str] = []
                        graph = build_research_graph(
                            profile,
                            build_document_tools(repository, agent_slug="amy"),
                            StubModel(),
                            event_sink=lambda event_type, data, target=events: target.append(
                                event_type
                            ),
                        )

                        with self.assertRaises(type(failure)) as raised:
                            asyncio.run(
                                graph.ainvoke(
                                    initial_state(profile),
                                    config={"callbacks": [StopToolCallback(tool_name, failure)]},
                                )
                            )

                        self.assertIs(raised.exception, failure)
                        self.assertEqual(events[-1], last_event)
                        self.assertEqual(list((root / "filed").rglob("*.md")), [])

    def test_wrapped_approval_error_still_escapes_the_read_node(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            library.mkdir()
            _populate_library(library)
            repository = DocumentRepository(library, root / "output", root / "filed")
            profile = get_profile("amy")
            model = StubModel()
            graph = build_research_graph(
                profile, build_document_tools(repository, agent_slug="amy"), model
            )
            failure = GovernanceBlockedError("require_approval", "Approval pending", "activity-1")

            with patch.object(repository, "read", side_effect=failure):
                with self.assertRaises(GovernanceBlockedError) as raised:
                    asyncio.run(
                        graph.ainvoke(
                            initial_state(profile),
                            config={"callbacks": [MaskGovernanceErrorCallback()]},
                        )
                    )

            self.assertIs(raised.exception, failure)
            self.assertEqual(model.last_messages, [])

    def test_related_source_failure_does_not_leak_content_or_stop_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            library.mkdir()
            (library / "Coca_Cola_MA.md").write_text(
                "NEVER_INCLUDE_RESTRICTED_COCA_COLA_CONTENT", encoding="utf-8"
            )
            (library / "Pepsi_MA.md").write_text("Authorized Pepsi evidence", encoding="utf-8")
            (library / "Citi_Bank_Reorganization.md").write_text(
                "Authorized Citi evidence", encoding="utf-8"
            )

            repository = SelectivelyUnavailableRepository(
                library,
                output,
                root / "filed_documents",
            )
            tools = build_document_tools(repository, agent_slug="barry")
            model = StubModel()
            profile = get_profile("barry")
            graph = build_research_graph(profile, tools, model)

            result = asyncio.run(graph.ainvoke(initial_state(profile)))

            evidence_ids = {item["document_id"] for item in result["evidence"]}
            self.assertIn("Pepsi_MA.md", evidence_ids)
            self.assertIn("Citi_Bank_Reorganization.md", evidence_ids)
            self.assertNotIn("Coca_Cola_MA.md", evidence_ids)
            self.assertEqual(len(result["unavailable"]), 1)

            synthesis_input = " ".join(str(message.content) for message in model.last_messages)
            self.assertNotIn("NEVER_INCLUDE_RESTRICTED_COCA_COLA_CONTENT", synthesis_input)
            self.assertIn("Source Availability", synthesis_input)
            self.assertTrue(result["final_report"].startswith("# Briefing"))
            self.assertEqual(
                result["report_path"],
                str((output / "barry-briefing.md").resolve()),
            )

    def test_openbox_reason_is_emitted_for_ui_but_excluded_from_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            library.mkdir()
            (library / "Coca_Cola_MA.md").write_text("Coca-Cola evidence", encoding="utf-8")
            (library / "Pepsi_MA.md").write_text("Pepsi evidence", encoding="utf-8")
            (library / "Citi_Bank_Reorganization.md").write_text("Citi evidence", encoding="utf-8")

            repository = SelectivelyGovernedRepository(
                library,
                output,
                root / "filed_documents",
            )
            model = StubModel()
            profile = get_profile("barry")
            events: list[tuple[str, dict]] = []
            graph = build_research_graph(
                profile,
                build_document_tools(repository, agent_slug="barry"),
                model,
                event_sink=lambda event_type, data: events.append((event_type, data)),
            )

            result = asyncio.run(graph.ainvoke(initial_state(profile)))

            blocked = [data for event_type, data in events if event_type == "read_blocked"]
            self.assertEqual(len(blocked), 1)
            self.assertIn("client-isolation policy", blocked[0]["reason"])
            self.assertIn("Coca", blocked[0]["document_id"])
            synthesis_input = " ".join(str(message.content) for message in model.last_messages)
            self.assertNotIn("client-isolation policy", synthesis_input)
            self.assertEqual(len(result["unavailable"]), 1)

    def test_stashed_openbox_reason_replaces_masking_api_error_for_ui_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            output = root / "output"
            library.mkdir()
            (library / "Coca_Cola_MA.md").write_text("Coca-Cola evidence", encoding="utf-8")
            (library / "Pepsi_MA.md").write_text("Pepsi evidence", encoding="utf-8")
            (library / "Citi_Bank_Reorganization.md").write_text("Citi evidence", encoding="utf-8")

            events: list[tuple[str, dict]] = []
            profile = get_profile("barry")
            recorder = OpenBoxEvaluationRecorder()
            repository = SelectivelyGovernedRepository(
                library,
                output,
                root / "filed_documents",
            )
            masking_callback = MaskGovernanceErrorCallback()
            graph = build_research_graph(
                profile,
                build_document_tools(
                    repository,
                    agent_slug="barry",
                    governance_failure_sink=recorder.record_exception,
                ),
                StubModel(),
                event_sink=lambda event_type, data: events.append((event_type, data)),
                governance_reason_lookup=recorder.reason_for,
            )

            result = asyncio.run(
                graph.ainvoke(
                    initial_state(profile),
                    config={"callbacks": [masking_callback]},
                )
            )

            blocked = [data for event_type, data in events if event_type == "read_blocked"]
            self.assertEqual(len(blocked), 1)
            self.assertEqual(
                blocked[0]["reason"],
                "Cross-client read denied by client-isolation policy",
            )
            self.assertNotIn("HTTP 400", blocked[0]["reason"])
            self.assertEqual(
                recorder.reason_for("read-barry-1"),
                "Cross-client read denied by client-isolation policy",
            )
            self.assertEqual(len(masking_callback.seen_errors), 1)
            masked_messages = [
                message
                for message in result["messages"]
                if isinstance(message, ToolMessage) and message.tool_call_id == "read-barry-1"
            ]
            self.assertEqual(len(masked_messages), 1)
            self.assertIn("HTTP 400", str(masked_messages[0].content))
            self.assertEqual(len(result["unavailable"]), 1)

    def test_amy_and_barry_sweep_all_clients_and_commit_only_scripted_allows(self) -> None:
        for agent_slug in ("amy", "barry"):
            with self.subTest(agent_slug=agent_slug), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                library = root / "library"
                output = root / "output"
                filed = root / "filed_documents"
                library.mkdir()
                _populate_library(library)
                repository = ScriptedFilingRepository(
                    library,
                    output,
                    filed,
                    filing_failures={
                        2: GovernanceBlockedError("Access denied by barriers"),
                        4: GovernanceBlockedError("Access denied by barriers"),
                    },
                )
                profile = get_profile(agent_slug)
                events: list[tuple[str, dict]] = []

                def evaluation_for(
                    tool_call_id: str,
                    expected_agent_slug: str = agent_slug,
                ) -> dict | None:
                    blocked = tool_call_id in {
                        f"upload-{expected_agent_slug}-1",
                        f"upload-{expected_agent_slug}-3",
                    }
                    return {
                        "verdict": "block" if blocked else "allow",
                        "reason": (
                            "Openbox - Filing on wrong client directory"
                            if blocked
                            else "Upload permitted"
                        ),
                        "policy_id": "policy-version-1",
                        "risk_score": 0.4 if blocked else 0.0,
                        "metadata": {"policy_evaluated": True},
                        "future_field": {"preserved": True},
                    }

                graph = build_research_graph(
                    profile,
                    build_document_tools(repository, agent_slug=agent_slug),
                    StubModel(),
                    event_sink=lambda event_type, data, target=events: target.append(
                        (event_type, data)
                    ),
                    governance_evaluation_lookup=evaluation_for,
                )

                result = asyncio.run(
                    graph.ainvoke(initial_state(profile), config={"recursion_limit": 50})
                )

                expected_attempts = [
                    f"{target.matter_id}/{target.client_id}/{agent_slug}-briefing.md"
                    for target in profile.filing_targets
                ]
                self.assertEqual(repository.filing_attempts, expected_attempts)
                self.assertEqual(
                    [item["status"] for item in result["filing_results"]],
                    ["committed", "blocked", "committed", "blocked"],
                )
                self.assertEqual(result["filing_outcome"], "completed_with_restrictions")
                self.assertEqual(
                    [item["evaluation_response"]["verdict"] for item in result["filing_results"]],
                    ["allow", "block", "allow", "block"],
                )
                self.assertTrue(
                    all(
                        item["evaluation_response"]["future_field"] == {"preserved": True}
                        for item in result["filing_results"]
                    )
                )

                staged_path = output / f"{agent_slug}-briefing.md"
                for index, destination in enumerate(expected_attempts):
                    filed_path = filed / destination
                    if index in {1, 3}:
                        self.assertFalse(
                            filed_path.exists(),
                            "a blocked tool body must not write",
                        )
                    else:
                        self.assertTrue(filed_path.is_file())
                        self.assertEqual(filed_path.read_bytes(), staged_path.read_bytes())
                self.assertEqual(
                    [event_type for event_type, _ in events if event_type.startswith("upload_")],
                    [
                        "upload_started",
                        "upload_completed",
                        "upload_started",
                        "upload_blocked",
                        "upload_started",
                        "upload_completed",
                        "upload_started",
                        "upload_blocked",
                    ],
                )

    def test_all_uploads_block_but_the_complete_sweep_finishes(self) -> None:
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
                    1: GovernanceBlockedError("Access denied by barriers"),
                    2: GovernanceBlockedError("Access denied by barriers"),
                    3: GovernanceBlockedError("Access denied by barriers"),
                    4: GovernanceBlockedError("Access denied by barriers"),
                },
            )
            profile = get_profile("amy")
            evaluation = {
                "verdict": "block",
                "reason": "Policy rejected this filing destination",
                "policy_id": "policy-version-2",
                "metadata": {"policy_evaluated": False},
            }
            graph = build_research_graph(
                profile,
                build_document_tools(repository, agent_slug="amy"),
                StubModel(),
                governance_evaluation_lookup=lambda tool_call_id: (
                    evaluation if tool_call_id.startswith("upload-amy-") else None
                ),
            )

            result = asyncio.run(
                graph.ainvoke(initial_state(profile), config={"recursion_limit": 50})
            )

            self.assertEqual(result["filing_outcome"], "completed_with_restrictions")
            self.assertEqual(
                [item["status"] for item in result["filing_results"]],
                ["blocked", "blocked", "blocked", "blocked"],
            )
            self.assertEqual(
                [item["evaluation_response"] for item in result["filing_results"]],
                [evaluation, evaluation, evaluation, evaluation],
            )
            self.assertEqual(list((root / "filed_documents").rglob("*.md")), [])

    def test_halt_and_operational_failure_keep_sdk_terminal_behavior(self) -> None:
        cases = (
            (
                "api failure",
                GovernanceAPIError("Governance API error: HTTP 503"),
                GovernanceAPIError,
            ),
            (
                "halt",
                GovernanceHaltError("Session halted by governance"),
                GovernanceHaltError,
            ),
        )
        for name, failure, expected_error in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                library = root / "library"
                library.mkdir()
                _populate_library(library)
                repository = ScriptedFilingRepository(
                    library,
                    root / "output",
                    root / "filed_documents",
                    filing_failures={1: failure},
                )
                profile = get_profile("amy")
                events: list[tuple[str, dict]] = []
                graph = build_research_graph(
                    profile,
                    build_document_tools(repository, agent_slug="amy"),
                    StubModel(),
                    event_sink=lambda event_type, data, target=events: target.append(
                        (event_type, data)
                    ),
                )

                with self.assertRaises(expected_error):
                    asyncio.run(graph.ainvoke(initial_state(profile)))

                self.assertEqual(len(repository.filing_attempts), 1)
                self.assertEqual(list((root / "filed_documents").rglob("*.md")), [])

    def test_colin_has_no_filing_phase(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            library.mkdir()
            _populate_library(library)
            repository = ScriptedFilingRepository(
                library,
                root / "output",
                root / "filed_documents",
            )
            profile = get_profile("colin")
            events: list[tuple[str, dict]] = []
            graph = build_research_graph(
                profile,
                build_document_tools(repository, agent_slug="colin"),
                StubModel(),
                event_sink=lambda event_type, data: events.append((event_type, data)),
            )

            result = asyncio.run(graph.ainvoke(initial_state(profile)))

            self.assertEqual(repository.filing_attempts, [])
            self.assertEqual(result["filing_results"], [])
            self.assertFalse(any(event_type.startswith("upload_") for event_type, _ in events))


if __name__ == "__main__":
    unittest.main()
