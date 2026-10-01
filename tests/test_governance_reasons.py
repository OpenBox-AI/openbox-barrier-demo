from __future__ import annotations

import unittest

from openbox_core.contracts.results import EvaluationResult, Verdict
from openbox_langchain import ActivityBridge

from openbox_langgraph_client_intelligence.governance_reasons import (
    OpenBoxEvaluationRecorder,
    observe_openbox_start_results,
)


class _GovernedHandler:
    def __init__(self, bridge: ActivityBridge | None) -> None:
        self._activity_bridge = bridge


class OpenBoxEvaluationRecorderTests(unittest.TestCase):
    def test_raw_block_response_is_observed_without_replacing_stashed_result(self) -> None:
        bridge = ActivityBridge()
        bridge.prepare_tool(
            "workflow-1",
            "activity-1",
            tool_call_id="read-barry-1",
        )
        recorder = OpenBoxEvaluationRecorder()
        attached = observe_openbox_start_results(_GovernedHandler(bridge), recorder)
        raw_response = {
            "verdict": "block",
            "reason": "Cross-client access denied by OpenBox",
            "policy_id": "policy-version-1",
            "risk_score": 0.7,
            "metadata": {"policy_evaluated": True},
            "future_field": {"preserved": True},
        }
        result = EvaluationResult(
            verdict=Verdict.BLOCK,
            reason="Cross-client access denied by OpenBox",
            metadata={"policy_evaluated": True},
            raw=raw_response,
        )

        bridge.stash_start_result("workflow-1", "activity-1", result)

        self.assertTrue(attached)
        self.assertEqual(
            recorder.reason_for("read-barry-1"),
            "Cross-client access denied by OpenBox",
        )
        self.assertEqual(recorder.evaluation_for("read-barry-1"), raw_response)
        self.assertIs(bridge.get("workflow-1", "activity-1").start_result, result)

    def test_allow_response_is_recorded_too(self) -> None:
        bridge = ActivityBridge()
        bridge.prepare_tool("workflow-1", "activity-1", tool_call_id="read-amy-0")
        recorder = OpenBoxEvaluationRecorder()
        observe_openbox_start_results(_GovernedHandler(bridge), recorder)
        raw_response = {
            "verdict": "allow",
            "reason": None,
            "metadata": {"policy_evaluated": True},
        }

        bridge.stash_start_result(
            "workflow-1",
            "activity-1",
            EvaluationResult(verdict=Verdict.ALLOW, raw=raw_response),
        )

        self.assertIsNone(recorder.reason_for("read-amy-0"))
        self.assertEqual(recorder.evaluation_for("read-amy-0"), raw_response)

    def test_typed_result_is_serialized_when_raw_response_is_unavailable(self) -> None:
        bridge = ActivityBridge()
        bridge.prepare_tool("workflow-1", "activity-1", tool_call_id="upload-amy-1")
        recorder = OpenBoxEvaluationRecorder()
        observe_openbox_start_results(_GovernedHandler(bridge), recorder)

        bridge.stash_start_result(
            "workflow-1",
            "activity-1",
            EvaluationResult(
                verdict=Verdict.ALLOW,
                reason="Allowed",
                policy_id="policy-version-2",
                metadata={"policy_evaluated": True},
            ),
        )

        response = recorder.evaluation_for("upload-amy-1")
        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(response["verdict"], "allow")
        self.assertEqual(response["reason"], "Allowed")
        self.assertEqual(response["policy_id"], "policy-version-2")
        self.assertEqual(response["metadata"], {"policy_evaluated": True})

    def test_missing_bridge_keeps_existing_fallback_behavior(self) -> None:
        recorder = OpenBoxEvaluationRecorder()

        self.assertFalse(observe_openbox_start_results(_GovernedHandler(None), recorder))


if __name__ == "__main__":
    unittest.main()
