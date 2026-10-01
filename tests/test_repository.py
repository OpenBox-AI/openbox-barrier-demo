from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openbox_langgraph_client_intelligence.repository import DocumentRepository


class DocumentRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.library = self.root / "library"
        self.output = self.root / "output"
        self.filed = self.root / "filed_documents"
        self.library.mkdir()
        (self.library / "Coca_Cola_MA.md").write_text("Coca-Cola evidence", encoding="utf-8")
        (self.library / "Pepsi_MA.txt").write_text("Pepsi evidence", encoding="utf-8")
        self.repository = DocumentRepository(self.library, self.output, self.filed)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_search_uses_metadata_and_returns_relative_ids(self) -> None:
        results = self.repository.search("Coca Cola transaction", limit=3)
        self.assertEqual(results[0]["document_id"], "Coca_Cola_MA.md")
        self.assertNotIn("evidence", str(results[0]).lower())

    def test_read_and_report_stay_inside_configured_roots(self) -> None:
        self.assertEqual(self.repository.read("Pepsi_MA.txt"), "Pepsi evidence")
        destination = self.repository.write_report("amy", "Briefing")
        self.assertEqual(destination, (self.output / "amy-briefing.md").resolve())
        self.assertEqual(destination.read_text(encoding="utf-8"), "Briefing\n")

    def test_path_traversal_and_absolute_paths_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "relative"):
            self.repository.read(str((self.library / "Pepsi_MA.txt").resolve()))
        with self.assertRaisesRegex(ValueError, "escapes"):
            self.repository.read("../outside.txt")

    def test_file_report_copies_the_exact_staged_report(self) -> None:
        source = self.repository.write_report("amy", "Exact staged report")

        destination = self.repository.file_report(
            "amy",
            "0001/10001/amy-briefing.md",
        )

        self.assertEqual(
            destination,
            (self.filed / "0001/10001/amy-briefing.md").resolve(),
        )
        self.assertEqual(destination.read_bytes(), source.read_bytes())

    def test_invalid_filing_destinations_never_create_a_file(self) -> None:
        self.repository.write_report("amy", "Staged report")
        invalid_destinations = (
            "/0001/10001/amy-briefing.md",
            "../10001/amy-briefing.md",
            "0001/10001/../amy-briefing.md",
            "0001/10001/sub/amy-briefing.md",
            "matter/10001/amy-briefing.md",
            "0001/client/amy-briefing.md",
            "0001/10001/renamed.md",
            r"0001\10001\amy-briefing.md",
        )

        for destination in invalid_destinations:
            with self.subTest(destination=destination):
                with self.assertRaises(ValueError):
                    self.repository.file_report("amy", destination)

        self.assertEqual(list(self.filed.rglob("*.md")), [])


if __name__ == "__main__":
    unittest.main()
