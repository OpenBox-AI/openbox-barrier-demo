from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from openbox_langgraph_client_intelligence.events import (
    EVENT_PREFIX,
    JsonEventWriter,
    sanitize_event_data,
    sanitize_operator_message,
)


class OperatorEventTests(unittest.TestCase):
    def test_sensitive_values_are_redacted_from_reasons(self) -> None:
        secret = "obx_super_secret_value"
        with patch.dict(os.environ, {"BARRY_OPENBOX_API_KEY": secret}):
            sanitized = sanitize_operator_message(
                f"Denied; api_key={secret}; Bearer another-sensitive-token"
            )

        self.assertNotIn(secret, sanitized)
        self.assertNotIn("another-sensitive-token", sanitized)
        self.assertIn("[redacted]", sanitized)

    def test_json_writer_uses_a_parseable_prefix_and_safe_reason(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            JsonEventWriter("amy").emit(
                "workflow_blocked",
                {"reason": "Blocked\nby policy", "document_id": "0001/20001/file.docx"},
            )

        line = output.getvalue().strip()
        self.assertTrue(line.startswith(EVENT_PREFIX))
        event = json.loads(line.removeprefix(EVENT_PREFIX))
        self.assertEqual(event["agent_slug"], "amy")
        self.assertEqual(event["data"]["reason"], "Blocked by policy")
        self.assertEqual(event["data"]["document_id"], "0001/20001/file.docx")

    def test_filing_safe_reason_is_sanitized(self) -> None:
        secret = "private-filing-token"
        with patch.dict(os.environ, {"PROVIDER_API_TOKEN": secret}):
            data = sanitize_event_data({"safe_reason": f"Denied with token={secret}"})

        self.assertNotIn(secret, data["safe_reason"])
        self.assertIn("[redacted]", data["safe_reason"])

    def test_evaluation_response_preserves_fields_but_redacts_identity_and_credentials(
        self,
    ) -> None:
        data = sanitize_event_data(
            {
                "evaluation_response": {
                    "verdict": "block",
                    "policy_id": "policy-version-1",
                    "metadata": {
                        "policy_evaluated": True,
                        "userId": "test-user@example.test",
                        "access_token": "secret-token",
                        "provider_response": {"private": "must-not-escape"},
                        "provider_user_id": "private-provider-user",
                        "raw_walls_response": {"private": "must-not-escape"},
                        "wallsResponse": {"private": "must-not-escape"},
                        "wallsUserId": "private-provider-user",
                    },
                    "future_field": {"preserved": True},
                }
            }
        )

        response = data["evaluation_response"]
        self.assertEqual(response["verdict"], "block")
        self.assertEqual(response["policy_id"], "policy-version-1")
        self.assertEqual(response["future_field"], {"preserved": True})
        self.assertTrue(response["metadata"]["policy_evaluated"])
        self.assertEqual(response["metadata"]["userId"], "[redacted]")
        self.assertEqual(response["metadata"]["access_token"], "[redacted]")
        for key in (
            "provider_response",
            "provider_user_id",
            "raw_walls_response",
            "wallsResponse",
            "wallsUserId",
        ):
            with self.subTest(key=key):
                self.assertEqual(response["metadata"][key], "[redacted]")


if __name__ == "__main__":
    unittest.main()
