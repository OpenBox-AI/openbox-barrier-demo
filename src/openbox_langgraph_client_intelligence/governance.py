"""OpenBox wrapping for one separately authenticated LangGraph agent."""

from __future__ import annotations

import os
from typing import Any

from openbox_langgraph import create_openbox_graph_handler

from .config import AgentSettings
from .profiles import AgentProfile


def build_governed_agent(
    graph: Any,
    profile: AgentProfile,
    settings: AgentSettings,
    *,
    session_id: str,
    multi_agent_session_id: str,
):
    """Wrap a compiled graph with one agent's immutable OpenBox credentials."""

    # This function runs in the agent's own worker process. The SDK falls back
    # to these shared variables for omitted credentials; use only this agent's
    # explicitly resolved settings, including when a signing mode is unset.
    for name in (
        "OPENBOX_AGENT_DID",
        "OPENBOX_AGENT_PRIVATE_KEY",
        "OPENBOX_LANGGRAPH_WORKLOAD_PRIVATE_KEY",
        "OPENBOX_WORKLOAD_PRIVATE_KEY",
    ):
        os.environ.pop(name, None)
    workload_options = {}
    if settings.openbox_workload_private_key is not None:
        workload_options["workload_private_key"] = settings.openbox_workload_private_key

    return create_openbox_graph_handler(
        graph=graph,
        api_url=settings.openbox_url,
        api_key=settings.openbox_api_key,
        validate=settings.openbox_validate,
        agent_did=settings.openbox_agent_did,
        agent_private_key=settings.openbox_agent_private_key,
        agent_name=settings.openbox_agent_name,
        session_id=session_id,
        multi_agent_session_id=multi_agent_session_id,
        task_queue="barrier-demo",
        on_api_error="fail_closed",
        use_core_instrumentation=True,
        strict_activity_context=True,
        tool_type_map={
            "search_documents": "builtin",
            "read_document": "builtin",
            "write_briefing": "builtin",
            "upload_document": "builtin",
        },
        send_chain_start_event=True,
        send_chain_end_event=True,
        send_tool_start_event=True,
        send_tool_end_event=True,
        send_llm_start_event=True,
        send_llm_end_event=True,
        **workload_options,
    )
