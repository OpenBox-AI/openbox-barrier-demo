from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from openbox_langgraph_client_intelligence.run_manager import RunRecord, WorkflowRunManager
from openbox_langgraph_client_intelligence.web_api import create_app


class FakeRunManager(WorkflowRunManager):
    async def _execute(self, record: RunRecord) -> None:
        timestamp = datetime.now(UTC).isoformat()
        self._append_event(
            record,
            {
                "type": "workflow_started",
                "timestamp": timestamp,
                "data": {"lead_count": 1},
            },
        )
        attempts = (
            ("Coca-Cola", "10001", "blocked"),
            ("PepsiCo", "20001", "committed"),
            ("Bank of America", "30001", "blocked"),
            ("Citi Bank", "30002", "committed"),
        )
        for attempt_number, (client_name, client_id, result_status) in enumerate(attempts, start=1):
            destination = f"0001/{client_id}/barry-briefing.md"
            started_data = {
                "target_label": "Client folder",
                "client_name": client_name,
                "destination_document_id": destination,
                "attempt_number": attempt_number,
                "attempt_count": len(attempts),
            }
            if attempt_number == 1:
                started_data.update(
                    {
                        "userId": "must-not-escape@example.test",
                        "raw_governance_payload": {"secret": "must-not-escape"},
                    }
                )
            self._append_event(
                record,
                {
                    "type": "upload_started",
                    "timestamp": timestamp,
                    "data": started_data,
                },
            )
            result_data = {
                **started_data,
                "status": result_status,
                "evaluation_response": {
                    "verdict": "block" if result_status == "blocked" else "allow",
                    "reason": (
                        "Access denied by OpenBox"
                        if result_status == "blocked"
                        else "Upload permitted"
                    ),
                    "policy_id": f"policy-version-{attempt_number}",
                    "metadata": {
                        "policy_evaluated": True,
                        "userId": "must-not-escape@example.test",
                    },
                    "future_field": {"preserved": True},
                },
            }
            if result_status == "blocked":
                result_data["reason"] = "Access denied by OpenBox"
                event_type = "upload_blocked"
            else:
                result_data["committed_path"] = f"/safe/filed_documents/{destination}"
                event_type = "upload_completed"
            self._append_event(
                record,
                {
                    "type": event_type,
                    "timestamp": timestamp,
                    "data": result_data,
                },
            )
        self._append_event(
            record,
            {
                "type": "read_blocked",
                "timestamp": timestamp,
                "data": {
                    "document_id": "0001/20001/Pepsi_Co_MA.docx",
                    "reason": "Denied by cross-client policy",
                    "lead_number": 1,
                    "lead_count": 1,
                },
            },
        )
        self._append_event(
            record,
            {
                "type": "workflow_completed",
                "timestamp": timestamp,
                "data": {
                    "final_status": "completed_with_restrictions",
                    "report": "Safe report",
                    "unavailable_count": 1,
                    "filing_results": list(record.filing_results),
                },
            },
        )


class WebApiTests(unittest.TestCase):
    def test_overview_endpoints_expose_documents_and_agents_without_secrets(self) -> None:
        with TestClient(create_app()) as client:
            health = client.get("/api/health")
            documents = client.get("/api/documents")
            agents = client.get("/api/agents")

        self.assertEqual(health.json(), {"status": "ok", "mode": "local"})
        self.assertEqual(documents.status_code, 200)
        self.assertEqual(len(documents.json()["documents"]), 4)
        self.assertEqual(
            [agent["slug"] for agent in agents.json()["agents"]],
            ["amy", "barry", "colin"],
        )
        response_text = agents.text.lower()
        self.assertNotIn("api_key", response_text)
        self.assertNotIn("private_key", response_text)
        agent_payload = agents.json()["agents"]
        self.assertEqual(len(agent_payload[0]["filing_targets"]), 4)
        self.assertEqual(len(agent_payload[1]["filing_targets"]), 4)
        self.assertEqual(agent_payload[2]["filing_targets"], [])

    def test_start_and_sse_expose_a_block_reason_and_final_status(self) -> None:
        manager = FakeRunManager()
        with TestClient(create_app(manager)) as client:
            preflight = client.options(
                "/api/agents/barry/runs",
                headers={
                    "Origin": "https://any-browser-origin.example",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "x-client-intelligence-ui",
                },
            )
            started = client.post("/api/agents/barry/runs")
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(preflight.headers["access-control-allow-origin"], "*")
            self.assertEqual(started.status_code, 202)
            run_id = started.json()["run_id"]

            with client.stream("GET", f"/api/runs/{run_id}/events") as response:
                event_stream = "".join(response.iter_text())
            snapshot = client.get(f"/api/runs/{run_id}").json()

        self.assertIn("read_blocked", event_stream)
        self.assertIn("upload_blocked", event_stream)
        self.assertIn("upload_completed", event_stream)
        self.assertIn("Denied by cross-client policy", event_stream)
        self.assertNotIn("must-not-escape", event_stream)
        self.assertEqual(snapshot["status"], "completed_with_restrictions")
        self.assertEqual(snapshot["report"], "Safe report")
        self.assertEqual(
            [result["status"] for result in snapshot["filing_results"]],
            ["blocked", "committed", "blocked", "committed"],
        )
        first_evaluation = snapshot["filing_results"][0]["evaluation_response"]
        self.assertEqual(snapshot["filing_results"][0]["safe_reason"], "Access denied by OpenBox")
        self.assertEqual(first_evaluation["verdict"], "block")
        self.assertEqual(first_evaluation["policy_id"], "policy-version-1")
        self.assertEqual(first_evaluation["future_field"], {"preserved": True})
        self.assertTrue(first_evaluation["metadata"]["policy_evaluated"])
        self.assertEqual(first_evaluation["metadata"]["userId"], "[redacted]")

    def test_filed_documents_endpoint_lists_only_committed_tree(self) -> None:
        with TemporaryDirectory() as temp_dir:
            filed_root = Path(temp_dir) / "filed_documents"
            committed = filed_root / "0001/10001/amy-briefing.md"
            committed.parent.mkdir(parents=True)
            committed.write_text("Committed report\n", encoding="utf-8")

            with patch.dict("os.environ", {"FILED_DOCUMENTS_DIR": str(filed_root)}):
                with TestClient(create_app()) as client:
                    response = client.get("/api/filed-documents")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["documents"],
            [
                {
                    "destination_document_id": "0001/10001/amy-briefing.md",
                    "name": "amy-briefing.md",
                    "path_parts": ["0001", "10001", "amy-briefing.md"],
                    "format": "md",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
