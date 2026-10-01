from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openbox_langgraph_client_intelligence.repository import DocumentRepository
from openbox_langgraph_client_intelligence.tools import build_document_tools


class DocumentToolTests(unittest.TestCase):
    def test_upload_tool_exposes_only_the_destination_document_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            library = root / "library"
            library.mkdir()
            repository = DocumentRepository(
                library,
                root / "output",
                root / "filed_documents",
            )

            tools = build_document_tools(repository, agent_slug="amy")

        self.assertEqual(
            set(tools.upload_document.args),
            {"destination_document_id"},
        )


if __name__ == "__main__":
    unittest.main()
