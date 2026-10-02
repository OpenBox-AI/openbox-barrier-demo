"""Run one agent identity in one operating-system process."""

from __future__ import annotations

import argparse
import asyncio
import uuid

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from openbox_langgraph import (
    ApprovalExpiredError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    GovernanceBlockedError,
    GovernanceHaltError,
)
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .approvals import ApprovalTracker, observe_approval_waits
from .config import AgentSettings
from .events import JsonEventWriter
from .governance import build_governed_agent
from .governance_reasons import OpenBoxEvaluationRecorder, observe_openbox_start_results
from .profiles import PROFILES, get_profile
from .repository import DocumentRepository
from .tools import build_document_tools
from .workflow import build_research_graph, initial_state

console = Console()
_GOVERNANCE_ERRORS = (
    GovernanceBlockedError,
    GovernanceHaltError,
    ApprovalRejectedError,
    ApprovalExpiredError,
    ApprovalTimeoutError,
)


async def run_agent(
    agent_slug: str,
    multi_agent_session_id: str,
    *,
    event_writer: JsonEventWriter | None = None,
) -> int:
    """Build and run one governed workflow."""

    profile = get_profile(agent_slug)
    try:
        load_dotenv()
        settings = AgentSettings.from_environment(profile)
        run_suffix = uuid.uuid4().hex[:12]
        repository = DocumentRepository(
            settings.document_library_dir,
            settings.report_output_dir,
            settings.filed_documents_dir,
        )
        openbox_evaluations = OpenBoxEvaluationRecorder()
        approvals = ApprovalTracker(_approval_reporter(profile.display_name, event_writer))
        observe_approval_waits(approvals)

        def record_governance_failure(tool_call_id: str, error: BaseException) -> None:
            openbox_evaluations.record_exception(tool_call_id, error)
            approvals.record_request(error)

        def emit_workflow_event(event_type: str, data: dict) -> None:
            approvals.observe(event_type, data)
            if event_writer:
                event_writer.emit(event_type, data)

        tools = build_document_tools(
            repository,
            agent_slug=profile.slug,
            governance_failure_sink=record_governance_failure,
        )
        model = ChatOpenAI(
            model=settings.openai_model,
            temperature=0,
            disable_streaming=True,
        )
        graph = build_research_graph(
            profile,
            tools,
            model,
            event_sink=emit_workflow_event,
            governance_reason_lookup=openbox_evaluations.reason_for,
            governance_evaluation_lookup=openbox_evaluations.evaluation_for,
        )

        governed = build_governed_agent(
            graph,
            profile,
            settings,
            session_id=f"{profile.slug}-{run_suffix}",
            multi_agent_session_id=multi_agent_session_id,
        )
        observe_openbox_start_results(governed, openbox_evaluations)

        if event_writer:
            event_writer.emit(
                "workflow_started",
                {
                    "display_name": profile.display_name,
                    "role": profile.role,
                    "assignment": profile.assignment,
                    "lead_count": len(profile.leads),
                    "filing_target_count": len(profile.filing_targets),
                },
            )
        else:
            console.print(
                Panel(
                    profile.assignment,
                    title=f"{profile.display_name} — {profile.role}",
                    border_style="blue",
                )
            )

        result = await governed.ainvoke(
            initial_state(profile),
            config={
                "configurable": {"thread_id": f"{profile.slug}-{run_suffix}"},
                "recursion_limit": 50,
            },
        )
    except _GOVERNANCE_ERRORS as exc:
        if event_writer:
            event_writer.emit(
                "workflow_blocked",
                {
                    "reason": str(exc),
                    "decision": getattr(exc, "verdict", type(exc).__name__),
                    "policy_id": getattr(exc, "policy_id", None),
                    "risk_score": getattr(exc, "risk_score", None),
                },
            )
        else:
            console.print(
                Panel(
                    "The workflow was stopped by OpenBox. No bypass was attempted.",
                    title=f"{profile.display_name} — governed stop",
                    border_style="red",
                )
            )
            console.print(f"[dim]{type(exc).__name__}: {exc}[/]")
        return 2
    except Exception as exc:
        if event_writer:
            event_writer.emit(
                "workflow_failed",
                {"reason": str(exc), "error_type": type(exc).__name__},
            )
        else:
            console.print(
                Panel(
                    str(exc),
                    title=f"{profile.display_name} — workflow failed",
                    border_style="red",
                )
            )
        return 1

    report = str(result.get("final_report", "No report was produced."))
    report_path = result.get("report_path")
    unavailable_count = len(result.get("unavailable", []))
    filing_results = list(result.get("filing_results", []))
    filing_outcome = result.get("filing_outcome")

    terminal_data = {
        "report": report,
        "report_path": report_path,
        "evidence_count": len(result.get("evidence", [])),
        "unavailable_count": unavailable_count,
        "filing_results": filing_results,
    }
    if event_writer:
        final_status = (
            "completed_with_restrictions"
            if unavailable_count or filing_outcome == "completed_with_restrictions"
            else "completed"
        )
        event_writer.emit(
            "workflow_completed",
            {
                **terminal_data,
                "final_status": final_status,
            },
        )
    else:
        console.print(Panel(Markdown(report), title=f"{profile.display_name} briefing"))
        if report_path:
            console.print(f"[green]Saved:[/] {report_path}")
        elif report:
            console.print(
                "[yellow]The briefing was produced but its file write was unavailable.[/]"
            )
        if filing_results:
            blocked = sum(item.get("status") == "blocked" for item in filing_results)
            committed = sum(item.get("status") == "committed" for item in filing_results)
            console.print(
                f"[cyan]Filing:[/] {len(filing_results)} attempts · "
                f"{blocked} blocked · {committed} committed"
            )
    return 0


def _approval_reporter(display_name: str, event_writer: JsonEventWriter | None):
    """Send approval waits to the web UI, or print them when run from the terminal."""

    def report(event_type: str, data: dict) -> None:
        if event_writer:
            event_writer.emit(event_type, data)
        elif event_type == "approval_requested":
            console.print(f"[cyan]{display_name} requires approval in OpenBox:[/] {data['reason']}")
        else:
            console.print(f"[green]Approved.[/] {display_name}'s run continues.")

    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, choices=sorted(PROFILES))
    parser.add_argument("--multi-agent-session-id", required=True)
    parser.add_argument(
        "--json-events",
        action="store_true",
        help="Emit prefixed JSON lifecycle events for the local web API",
    )
    return parser


def run() -> None:
    args = _parser().parse_args()
    writer = JsonEventWriter(args.agent) if args.json_events else None
    raise SystemExit(
        asyncio.run(
            run_agent(
                args.agent,
                args.multi_agent_session_id,
                event_writer=writer,
            )
        )
    )


if __name__ == "__main__":
    run()
