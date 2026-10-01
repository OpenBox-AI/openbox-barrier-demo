"""Environment-backed runtime configuration with per-agent credential isolation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .profiles import AgentProfile


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str) -> str | None:
    return os.environ.get(name, "").strip() or None


def _boolean(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class AgentSettings:
    """Resolved settings for exactly one independently authenticated agent."""

    profile_slug: str
    openbox_url: str
    openbox_api_key: str = field(repr=False)
    openbox_agent_name: str
    openbox_agent_did: str | None
    openbox_agent_private_key: str | None = field(repr=False)
    openbox_validate: bool
    openai_model: str
    document_library_dir: Path
    report_output_dir: Path
    filed_documents_dir: Path
    openbox_workload_private_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_environment(cls, profile: AgentProfile) -> AgentSettings:
        prefix = profile.slug.upper()
        _required("OPENAI_API_KEY")
        agent_did = _optional(f"{prefix}_OPENBOX_AGENT_DID")
        agent_private_key = _optional(f"{prefix}_OPENBOX_AGENT_PRIVATE_KEY")
        if bool(agent_did) != bool(agent_private_key):
            raise ValueError(
                f"Set both {prefix}_OPENBOX_AGENT_DID and {prefix}_OPENBOX_AGENT_PRIVATE_KEY "
                "for legacy signing, or leave both unset for workload or API-key-only auth"
            )
        library = Path(_required("DOCUMENT_LIBRARY_DIR")).expanduser().resolve()
        if not library.is_dir():
            raise ValueError(f"DOCUMENT_LIBRARY_DIR is not a directory: {library}")

        output = Path(os.environ.get("REPORT_OUTPUT_DIR", "./output")).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)
        filed_documents = (
            Path(os.environ.get("FILED_DOCUMENTS_DIR", "./filed_documents")).expanduser().resolve()
        )
        filed_documents.mkdir(parents=True, exist_ok=True)

        return cls(
            profile_slug=profile.slug,
            openbox_url=_required("OPENBOX_API_URL").rstrip("/"),
            openbox_api_key=_required(f"{prefix}_OPENBOX_API_KEY"),
            openbox_agent_name=_required(f"{prefix}_OPENBOX_AGENT_NAME"),
            openbox_agent_did=agent_did,
            openbox_agent_private_key=agent_private_key,
            openbox_validate=_boolean("OPENBOX_VALIDATE", True),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            document_library_dir=library,
            report_output_dir=output,
            filed_documents_dir=filed_documents,
            openbox_workload_private_key=_optional(f"{prefix}_OPENBOX_WORKLOAD_PRIVATE_KEY"),
        )
