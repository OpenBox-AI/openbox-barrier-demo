"""Local-only FastAPI service for the client-intelligence control room."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi import Path as ApiPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .profiles import PROFILES
from .repository import SUPPORTED_SUFFIXES
from .run_manager import PROJECT_ROOT, RunConflictError, WorkflowRunManager


def _document_library() -> Path:
    configured = Path(os.environ.get("DOCUMENT_LIBRARY_DIR", "./documents")).expanduser()
    if not configured.is_absolute():
        configured = PROJECT_ROOT / configured
    resolved = configured.resolve()
    if not resolved.is_dir():
        raise RuntimeError(f"Document library is not a directory: {resolved}")
    return resolved


def _documents_payload() -> dict[str, Any]:
    root = _document_library()
    documents = []
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        relative = file_path.relative_to(root)
        documents.append(
            {
                "document_id": relative.as_posix(),
                "name": file_path.name,
                "title": file_path.stem.replace("_", " ").replace("-", " "),
                "path_parts": list(relative.parts),
                "format": file_path.suffix.lower().removeprefix("."),
            }
        )
    return {"root_name": root.name, "display_path": f"./{root.name}", "documents": documents}


def _filed_documents_root() -> Path:
    configured = Path(os.environ.get("FILED_DOCUMENTS_DIR", "./filed_documents")).expanduser()
    if not configured.is_absolute():
        configured = PROJECT_ROOT / configured
    return configured.resolve()


def _filed_documents_payload() -> dict[str, Any]:
    root = _filed_documents_root()
    documents = []
    if root.is_dir():
        for file_path in sorted(root.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            relative = file_path.relative_to(root)
            documents.append(
                {
                    "destination_document_id": relative.as_posix(),
                    "name": file_path.name,
                    "path_parts": list(relative.parts),
                    "format": file_path.suffix.lower().removeprefix("."),
                }
            )
    return {
        "root_name": root.name,
        "display_path": f"./{root.name}",
        "documents": documents,
    }


def create_app(run_manager: WorkflowRunManager | None = None) -> FastAPI:
    manager = run_manager or WorkflowRunManager()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await manager.shutdown()

    application = FastAPI(
        title="OpenBox Barrier Demo API",
        version="0.2.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    application.state.run_manager = manager
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": "local"}

    @application.get("/api/documents")
    async def documents() -> dict[str, Any]:
        return _documents_payload()

    @application.get("/api/filed-documents")
    async def filed_documents() -> dict[str, Any]:
        return _filed_documents_payload()

    @application.get("/api/agents")
    async def agents() -> dict[str, Any]:
        payload = []
        for slug in ("amy", "barry", "colin"):
            profile = PROFILES[slug]
            latest = manager.latest_for(slug)
            payload.append(
                {
                    "slug": profile.slug,
                    "display_name": profile.display_name,
                    "role": profile.role,
                    "assignment": profile.assignment,
                    "leads": [
                        {
                            "label": lead.label,
                            "query": lead.query,
                            "purpose": lead.purpose,
                            "kind": lead.kind,
                        }
                        for lead in profile.leads
                    ],
                    "filing_targets": [
                        {
                            "label": target.label,
                            "client_name": target.client_name,
                            "destination_folder_id": f"{target.matter_id}/{target.client_id}",
                        }
                        for target in profile.filing_targets
                    ],
                    "latest_run": latest.snapshot() if latest else None,
                }
            )
        return {"agents": payload}

    @application.post("/api/agents/{agent_slug}/runs", status_code=status.HTTP_202_ACCEPTED)
    async def start_run(
        agent_slug: Annotated[str, ApiPath(pattern="^(amy|barry|colin)$")],
    ) -> dict[str, Any]:
        try:
            record = await manager.start(agent_slug)
        except RunConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": str(exc), "run": exc.run.snapshot()},
            ) from exc
        return record.snapshot()

    @application.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        record = manager.get(run_id)
        if not record:
            raise HTTPException(status_code=404, detail="Run not found")
        return record.snapshot()

    @application.get("/api/runs/{run_id}/events")
    async def run_events(
        request: Request,
        run_id: str,
        after: Annotated[int, Query(ge=0)] = 0,
    ) -> StreamingResponse:
        record = manager.get(run_id)
        if not record:
            raise HTTPException(status_code=404, detail="Run not found")

        last_event_id = request.headers.get("last-event-id", "")
        if last_event_id.isdigit():
            after = max(after, int(last_event_id))

        async def stream() -> AsyncIterator[str]:
            subscribed_record, history, queue = manager.subscribe(run_id, after)
            try:
                for event in history:
                    yield _sse(event)
                if subscribed_record.is_terminal:
                    return

                while True:
                    if await request.is_disconnected():
                        return
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    yield _sse(event)
                    if subscribed_record.is_terminal:
                        return
            finally:
                manager.unsubscribe(subscribed_record, queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return application


def _sse(event: dict[str, Any]) -> str:
    return f"id: {event['sequence']}\ndata: {json.dumps(event, ensure_ascii=True)}\n\n"


load_dotenv(PROJECT_ROOT / ".env")
app = create_app()


def run() -> None:
    """Run the API on loopback only."""

    port = int(os.environ.get("DEMO_API_PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
