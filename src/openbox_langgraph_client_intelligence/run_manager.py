"""In-memory orchestration for isolated web-triggered agent processes."""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .events import EVENT_PREFIX, sanitize_event_data, sanitize_operator_message
from .profiles import PROFILES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TERMINAL_STATUSES = frozenset({"completed", "completed_with_restrictions", "blocked", "failed"})
_ALLOWED_EVENT_TYPES = frozenset(
    {
        "workflow_started",
        "search_started",
        "search_empty",
        "search_blocked",
        "search_failed",
        "read_started",
        "read_allowed",
        "read_blocked",
        "read_failed",
        "synthesis_started",
        "synthesis_completed",
        "write_started",
        "write_completed",
        "write_blocked",
        "write_failed",
        "upload_started",
        "upload_blocked",
        "upload_completed",
        "upload_failed",
        "approval_requested",
        "approval_granted",
        "workflow_completed",
        "workflow_blocked",
        "workflow_failed",
    }
)
_FILING_EVENT_TYPES = frozenset(
    {"upload_started", "upload_blocked", "upload_completed", "upload_failed"}
)
_SAFE_FILING_KEYS = frozenset(
    {
        "target_label",
        "client_name",
        "destination_document_id",
        "attempt_number",
        "attempt_count",
        "status",
        "reason",
        "safe_reason",
        "committed_path",
        "evaluation_response",
    }
)


class RunConflictError(RuntimeError):
    """Raised when an agent already has an active web-triggered run."""

    def __init__(self, run: RunRecord) -> None:
        super().__init__(f"{run.agent_slug} already has an active workflow")
        self.run = run


@dataclass
class RunRecord:
    """Mutable state for one worker process, owned by the API event loop."""

    run_id: str
    agent_slug: str
    multi_agent_session_id: str
    created_at: str
    status: str = "starting"
    current_step: str = "Starting"
    progress: int = 2
    events: list[dict[str, Any]] = field(default_factory=list)
    report: str | None = None
    report_path: str | None = None
    filing_results: list[dict[str, Any]] = field(default_factory=list)
    final_reason: str | None = None
    process: asyncio.subprocess.Process | None = field(default=None, repr=False)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set, repr=False)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "agent_slug": self.agent_slug,
            "multi_agent_session_id": self.multi_agent_session_id,
            "created_at": self.created_at,
            "status": self.status,
            "current_step": self.current_step,
            "progress": self.progress,
            "events": list(self.events),
            "report": self.report,
            "report_path": self.report_path,
            "filing_results": list(self.filing_results),
            "final_reason": self.final_reason,
        }


class WorkflowRunManager:
    """Start workers and fan their safe event stream out to local UI clients."""

    def __init__(self, *, project_root: Path = PROJECT_ROOT) -> None:
        self.project_root = project_root.resolve()
        self.multi_agent_session_id = f"client-intel-web-{uuid.uuid4()}"
        self._runs: dict[str, RunRecord] = {}
        self._latest_by_agent: dict[str, str] = {}
        self._tasks: set[asyncio.Task[None]] = set()
        self._start_lock = asyncio.Lock()

    async def start(self, agent_slug: str) -> RunRecord:
        if agent_slug not in PROFILES:
            raise ValueError(f"Unknown agent: {agent_slug}")

        async with self._start_lock:
            latest = self.latest_for(agent_slug)
            if latest and not latest.is_terminal:
                raise RunConflictError(latest)

            run_id = uuid.uuid4().hex
            record = RunRecord(
                run_id=run_id,
                agent_slug=agent_slug,
                multi_agent_session_id=self.multi_agent_session_id,
                created_at=datetime.now(UTC).isoformat(),
            )
            self._runs[run_id] = record
            self._latest_by_agent[agent_slug] = run_id
            self._append_event(
                record,
                {
                    "type": "workflow_starting",
                    "agent_slug": agent_slug,
                    "timestamp": record.created_at,
                    "data": {"message": "Launching isolated agent process"},
                },
            )
            task = asyncio.create_task(self._execute(record), name=f"workflow-{run_id}")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            return record

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def latest_for(self, agent_slug: str) -> RunRecord | None:
        run_id = self._latest_by_agent.get(agent_slug)
        return self._runs.get(run_id) if run_id else None

    def subscribe(
        self,
        run_id: str,
        after_sequence: int,
    ) -> tuple[RunRecord, list[dict[str, Any]], asyncio.Queue[dict[str, Any]]]:
        record = self._runs[run_id]
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
        record.subscribers.add(queue)
        history = [event for event in record.events if event["sequence"] > after_sequence]
        return record, history, queue

    @staticmethod
    def unsubscribe(record: RunRecord, queue: asyncio.Queue[dict[str, Any]]) -> None:
        record.subscribers.discard(queue)

    async def shutdown(self) -> None:
        active = [record.process for record in self._runs.values() if record.process]
        for process in active:
            if process and process.returncode is None:
                process.terminate()
        if active:
            waits = (process.wait() for process in active if process)
            await asyncio.gather(*waits, return_exceptions=True)
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _execute(self, record: RunRecord) -> None:
        stderr_task: asyncio.Task[list[str]] | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "openbox_langgraph_client_intelligence.worker",
                "--agent",
                record.agent_slug,
                "--multi-agent-session-id",
                record.multi_agent_session_id,
                "--json-events",
                cwd=self.project_root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            record.process = process
            if process.stderr:
                stderr_task = asyncio.create_task(self._collect_stderr(process.stderr))
            if process.stdout:
                async for raw_line in process.stdout:
                    self._handle_worker_line(record, raw_line.decode("utf-8", errors="replace"))

            return_code = await process.wait()
            stderr_lines = await stderr_task if stderr_task else []
            if not record.is_terminal:
                detail = (
                    stderr_lines[-1] if stderr_lines else f"Worker exited with code {return_code}"
                )
                self._append_terminal_failure(record, detail, "WorkerExitError")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._append_terminal_failure(record, str(exc), type(exc).__name__)
        finally:
            record.process = None
            if stderr_task and not stderr_task.done():
                stderr_task.cancel()

    @staticmethod
    async def _collect_stderr(stream: asyncio.StreamReader) -> list[str]:
        lines: list[str] = []
        async for raw_line in stream:
            line = sanitize_operator_message(raw_line.decode("utf-8", errors="replace"))
            lines.append(line)
            if len(lines) > 12:
                lines.pop(0)
        return lines

    def _handle_worker_line(self, record: RunRecord, line: str) -> None:
        if not line.startswith(EVENT_PREFIX):
            return
        try:
            event = json.loads(line.removeprefix(EVENT_PREFIX))
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict) or event.get("type") not in _ALLOWED_EVENT_TYPES:
            return
        if event.get("agent_slug") != record.agent_slug:
            return
        self._append_event(record, event)

    def _append_terminal_failure(self, record: RunRecord, reason: str, error_type: str) -> None:
        if record.is_terminal:
            return
        self._append_event(
            record,
            {
                "type": "workflow_failed",
                "agent_slug": record.agent_slug,
                "timestamp": datetime.now(UTC).isoformat(),
                "data": {
                    "reason": sanitize_operator_message(reason),
                    "error_type": error_type,
                },
            },
        )

    def _append_event(self, record: RunRecord, event: dict[str, Any]) -> None:
        event_data = event.get("data")
        event_type = str(event.get("type", "unknown"))
        safe_data = sanitize_event_data(event_data if isinstance(event_data, dict) else {})
        if event_type in _FILING_EVENT_TYPES:
            safe_data = {key: value for key, value in safe_data.items() if key in _SAFE_FILING_KEYS}
        elif event_type in {"workflow_completed", "workflow_blocked", "workflow_failed"}:
            filing_results = safe_data.get("filing_results")
            if isinstance(filing_results, list):
                safe_data["filing_results"] = [
                    safe
                    for item in filing_results
                    if (safe := _safe_filing_result(item)) is not None
                ]
        normalized = {
            "sequence": len(record.events) + 1,
            "type": event_type,
            "agent_slug": record.agent_slug,
            "timestamp": str(event.get("timestamp") or datetime.now(UTC).isoformat()),
            "data": safe_data,
        }
        record.events.append(normalized)
        self._apply_status(record, normalized)
        for queue in tuple(record.subscribers):
            try:
                queue.put_nowait(normalized)
            except asyncio.QueueFull:
                record.subscribers.discard(queue)

    @staticmethod
    def _apply_status(record: RunRecord, event: dict[str, Any]) -> None:
        event_type = event["type"]
        data = event["data"]
        if event_type == "workflow_starting":
            record.status, record.current_step, record.progress = "starting", "Starting", 2
        elif event_type == "workflow_started":
            record.status, record.current_step, record.progress = "running", "Starting", 5
        elif event_type == "search_started":
            lead_count = max(int(data.get("lead_count", 1)), 1)
            lead_number = max(int(data.get("lead_number", 1)), 1)
            record.current_step = "Searching"
            record.progress = min(65, 8 + int(((lead_number - 1) / lead_count) * 58))
        elif event_type == "read_started":
            record.current_step = "Reading"
        elif event_type in {"read_allowed", "read_blocked", "read_failed", "search_empty"}:
            lead_count = max(int(data.get("lead_count", 1)), 1)
            lead_number = max(int(data.get("lead_number", 1)), 1)
            record.current_step = "Reading"
            record.progress = min(70, 10 + int((lead_number / lead_count) * 58))
        elif event_type == "synthesis_started":
            record.current_step, record.progress = "Synthesizing", 76
        elif event_type == "synthesis_completed":
            record.current_step, record.progress = "Synthesizing", 86
        elif event_type == "write_started":
            record.current_step, record.progress = "Writing", 91
        elif event_type in {"write_completed", "write_blocked", "write_failed"}:
            record.current_step, record.progress = "Writing", 96
        elif event_type == "upload_started":
            record.current_step = "Filing"
            record.progress = 97
        elif event_type in {"upload_completed", "upload_blocked", "upload_failed"}:
            record.current_step = "Filing"
            record.progress = 99
            filing_result = _filing_result_from_event(data)
            if filing_result is not None:
                attempt_number = filing_result.get("attempt_number")
                record.filing_results = [
                    item
                    for item in record.filing_results
                    if item.get("attempt_number") != attempt_number
                ]
                record.filing_results.append(filing_result)
                record.filing_results.sort(key=lambda item: int(item.get("attempt_number", 0)))
        elif event_type == "approval_requested":
            record.status, record.current_step = "awaiting_approval", "Requires approval"
        elif event_type == "approval_granted":
            record.status, record.current_step = "running", "Resuming"
        elif event_type == "workflow_completed":
            final_status = str(data.get("final_status", "completed"))
            record.status = (
                final_status
                if final_status in {"completed", "completed_with_restrictions"}
                else "completed"
            )
            record.current_step, record.progress = "Finished", 100
            record.report = str(data.get("report")) if data.get("report") is not None else None
            record.report_path = (
                str(data.get("report_path")) if data.get("report_path") is not None else None
            )
            _capture_terminal_filing(record, data)
        elif event_type == "workflow_blocked":
            record.status, record.current_step, record.progress = "blocked", "Blocked", 100
            record.final_reason = str(data.get("reason") or "Blocked by OpenBox")
            _capture_terminal_filing(record, data)
        elif event_type == "workflow_failed":
            record.status, record.current_step, record.progress = "failed", "Failed", 100
            record.final_reason = str(data.get("reason") or "Workflow failed")
            _capture_terminal_filing(record, data)


def _safe_filing_result(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        str(key): sanitize_event_data(child, key=str(key))
        for key, child in value.items()
        if str(key) in _SAFE_FILING_KEYS
    }


def _filing_result_from_event(data: dict[str, Any]) -> dict[str, Any] | None:
    safe = _safe_filing_result(data)
    if safe is None:
        return None
    if "reason" in safe:
        safe["safe_reason"] = safe.pop("reason")
    safe.setdefault("committed_path", None)
    return safe


def _capture_terminal_filing(record: RunRecord, data: dict[str, Any]) -> None:
    record.report = str(data.get("report")) if data.get("report") is not None else record.report
    record.report_path = (
        str(data.get("report_path")) if data.get("report_path") is not None else record.report_path
    )
    filing_results = data.get("filing_results")
    if isinstance(filing_results, list):
        record.filing_results = [
            safe for item in filing_results if (safe := _safe_filing_result(item)) is not None
        ]
