from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openbox_langgraph_client_intelligence.repository import DocumentRepository


class BundledDocumentTests(unittest.TestCase):
    def test_bundled_library_contains_and_resolves_the_four_demo_documents(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        library = project_root / "documents"
        expected = {
            "0001/10001/Coca_Cola_MA.docx",
            "0001/20001/Pepsi_Co_MA.docx",
            "0001/30001/Bank_of_America_CEO.docx",
            "0001/30002/Citi_Bank_Reorg.docx",
        }
        actual = {
            path.relative_to(library).as_posix() for path in library.rglob("*") if path.is_file()
        }
        self.assertEqual(actual, expected)

        with tempfile.TemporaryDirectory() as output_dir:
            generated_root = Path(output_dir)
            repository = DocumentRepository(
                library,
                generated_root / "output",
                generated_root / "filed_documents",
            )
            expectations = {
                "Coca Cola M&A transaction": "0001/10001/Coca_Cola_MA.docx",
                "Pepsi M&A transaction": "0001/20001/Pepsi_Co_MA.docx",
                "Bank of America CEO leadership transition": (
                    "0001/30001/Bank_of_America_CEO.docx"
                ),
                "Citi Bank reorganization precedent": "0001/30002/Citi_Bank_Reorg.docx",
            }
            for query, expected_document in expectations.items():
                with self.subTest(query=query):
                    results = repository.search(query, limit=1)
                    self.assertEqual(results[0]["document_id"], expected_document)
                    self.assertTrue(repository.read(expected_document).strip())


if __name__ == "__main__":
    unittest.main()
