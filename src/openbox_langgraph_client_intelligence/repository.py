"""Contained, provider-neutral document discovery and reading."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from xml.etree import ElementTree

SUPPORTED_SUFFIXES = frozenset({".md", ".txt", ".docx"})
_WORD_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_SAFE_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_FILING_DESTINATION_PATTERN = re.compile(
    r"^(?P<matter_id>[0-9]+)/(?P<client_id>[0-9]+)/(?P<filename>[^/]+)$"
)


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(value.lower()))


class DocumentRepository:
    """Search and read documents contained by one configured library root."""

    def __init__(self, library_root: Path, output_root: Path, filed_documents_root: Path) -> None:
        self.library_root = library_root.expanduser().resolve()
        self.output_root = output_root.expanduser().resolve()
        self.filed_documents_root = filed_documents_root.expanduser().resolve()
        if not self.library_root.is_dir():
            raise ValueError(f"Document library is not a directory: {self.library_root}")
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.filed_documents_root.mkdir(parents=True, exist_ok=True)

    def search(self, query: str, limit: int = 3) -> list[dict[str, object]]:
        """Rank document metadata without opening document bodies."""

        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        bounded_limit = max(1, min(int(limit), 5))
        matches: list[dict[str, object]] = []

        for path in self.library_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            relative = path.relative_to(self.library_root).as_posix()
            metadata_tokens = _tokens(f"{relative} {path.stem.replace('_', ' ')}")
            score = len(query_tokens & metadata_tokens)
            if score == 0:
                continue
            matches.append(
                {
                    "document_id": relative,
                    "title": path.stem.replace("_", " ").replace("-", " "),
                    "score": score,
                }
            )

        matches.sort(key=lambda item: (-int(item["score"]), str(item["document_id"])))
        return matches[:bounded_limit]

    def read(self, document_id: str) -> str:
        """Read a supported document after resolving it inside the library root."""

        path = self._resolve_document(document_id)
        if path.suffix.lower() == ".docx":
            return self._read_docx(path)
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def write_report(self, agent_slug: str, content: str) -> Path:
        """Write one report to a fixed, validated agent-specific destination."""

        destination = self.report_path(agent_slug)
        with open(destination, "w", encoding="utf-8") as handle:
            handle.write(content.rstrip() + "\n")
        return destination

    def report_path(self, agent_slug: str) -> Path:
        """Return the one staging-report path bound to an agent."""

        if not _SAFE_SLUG_PATTERN.fullmatch(agent_slug):
            raise ValueError("Invalid agent slug")
        destination = (self.output_root / f"{agent_slug}-briefing.md").resolve()
        if not destination.is_relative_to(self.output_root):
            raise ValueError("Report destination escapes the output directory")
        return destination

    def file_report(self, agent_slug: str, destination_document_id: str) -> Path:
        """Copy an agent's staged report into one path-contained filing destination."""

        source = self.report_path(agent_slug)
        if not source.is_file():
            raise FileNotFoundError("The staged report is unavailable")
        if "\\" in destination_document_id:
            raise ValueError("Filing destination must use forward-slash path segments")

        match = _FILING_DESTINATION_PATTERN.fullmatch(destination_document_id)
        if match is None:
            raise ValueError("Filing destination must be matter/client/filename")
        filename = match.group("filename")
        if filename in {".", ".."}:
            raise ValueError("Filing destination contains a dot segment")
        if filename != source.name:
            raise ValueError("Filing destination filename must match the staged report")

        destination = (
            self.filed_documents_root
            / match.group("matter_id")
            / match.group("client_id")
            / filename
        ).resolve()
        if not destination.is_relative_to(self.filed_documents_root):
            raise ValueError("Filing destination escapes the filed-documents directory")

        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        return destination

    def _resolve_document(self, document_id: str) -> Path:
        raw = Path(document_id)
        if raw.is_absolute():
            raise ValueError("Document IDs must be relative paths")
        candidate = (self.library_root / raw).resolve()
        if not candidate.is_relative_to(self.library_root):
            raise ValueError("Document path escapes the document library")
        if candidate.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported document type: {candidate.suffix}")
        if not candidate.is_file():
            raise FileNotFoundError(f"Document not found: {document_id}")
        return candidate

    @staticmethod
    def _read_docx(path: Path) -> str:
        with zipfile.ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(document_xml)
        paragraphs: list[str] = []
        for paragraph in root.iter(f"{{{_WORD_NAMESPACE}}}p"):
            text = "".join(
                node.text or "" for node in paragraph.iter(f"{{{_WORD_NAMESPACE}}}t")
            ).strip()
            if text:
                paragraphs.append(text)
        return "\n".join(paragraphs)
