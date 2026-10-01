"""Launch one or all isolated client-intelligence agents."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from .profiles import PROFILES
from .worker import run_agent


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--all", action="store_true", help="Run all three agents")
    selection.add_argument("--agent", choices=sorted(PROFILES), help="Run one agent")
    parser.add_argument(
        "--multi-agent-session-id",
        help="OpenBox correlation ID; generated automatically when omitted",
    )
    return parser


async def _run_all(multi_agent_session_id: str) -> int:
    processes = [
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "openbox_langgraph_client_intelligence.worker",
            "--agent",
            slug,
            "--multi-agent-session-id",
            multi_agent_session_id,
        )
        for slug in sorted(PROFILES)
    ]
    codes = await asyncio.gather(*(process.wait() for process in processes))
    return max(codes, default=0)


async def _main() -> int:
    args = _parser().parse_args()
    multi_agent_session_id = args.multi_agent_session_id or f"client-intel-{uuid.uuid4()}"
    if args.agent:
        return await run_agent(args.agent, multi_agent_session_id)
    return await _run_all(multi_agent_session_id)


def run() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    run()
