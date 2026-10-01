"""Normal document tools used by every client-intelligence workflow."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass

from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import ToolRuntime
from openbox_langgraph import (
    ApprovalExpiredError,
    ApprovalRejectedError,
    ApprovalTimeoutError,
    GovernanceBlockedError,
    GovernanceHaltError,
)

from .repository import DocumentRepository

GovernanceFailureSink = Callable[[str, BaseException], None]
_GOVERNANCE_ERRORS = (
    GovernanceBlockedError,
    GovernanceHaltError,
    ApprovalRejectedError,
    ApprovalExpiredError,
    ApprovalTimeoutError,
)


@dataclass(frozen=True)
class DocumentTools:
    search_documents: BaseTool
    read_document: BaseTool
    write_briefing: BaseTool
    upload_document: BaseTool


def build_document_tools(
    repository: DocumentRepository,
    *,
    agent_slug: str,
    max_document_chars: int = 20_000,
    governance_failure_sink: GovernanceFailureSink | None = None,
) -> DocumentTools:
    """Build tools over a configured repository without adding access logic."""

    @tool("search_documents")
    def search_documents(query: str, limit: int = 3) -> str:
        """Search document metadata for a business research query."""

        return json.dumps({"results": repository.search(query, limit)}, sort_keys=True)

    @tool("read_document")
    def read_document(document_id: str, runtime: ToolRuntime) -> str:
        """Read one document selected from search results."""

        try:
            content = repository.read(document_id)
        except _GOVERNANCE_ERRORS as exc:
            tool_call_id = runtime.tool_call_id
            if governance_failure_sink is not None and isinstance(tool_call_id, str):
                try:
                    governance_failure_sink(tool_call_id, exc)
                except Exception:
                    # Display enrichment cannot affect enforcement.
                    pass
            raise
        truncated = len(content) > max_document_chars
        return json.dumps(
            {
                "document_id": document_id,
                "content": content[:max_document_chars],
                "truncated": truncated,
            },
            sort_keys=True,
        )

    @tool("write_briefing")
    def write_briefing(agent_slug: str, content: str) -> str:
        """Write a completed client-intelligence briefing for one agent."""

        destination = repository.write_report(agent_slug, content)
        return json.dumps({"report_path": str(destination)}, sort_keys=True)

    @tool("upload_document")
    def upload_document(destination_document_id: str, runtime: ToolRuntime) -> str:
        """File this agent's staged report at one matter/client destination."""

        try:
            destination = repository.file_report(agent_slug, destination_document_id)
        except _GOVERNANCE_ERRORS as exc:
            tool_call_id = runtime.tool_call_id
            if governance_failure_sink is not None and isinstance(tool_call_id, str):
                try:
                    governance_failure_sink(tool_call_id, exc)
                except Exception:
                    # Display enrichment cannot affect enforcement.
                    pass
            raise
        return json.dumps(
            {
                "destination_document_id": destination_document_id,
                "committed_path": str(destination),
            },
            sort_keys=True,
        )

    return DocumentTools(
        search_documents=search_documents,
        read_document=read_document,
        write_briefing=write_briefing,
        upload_document=upload_document,
    )
