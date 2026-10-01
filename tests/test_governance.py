from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from openbox_langgraph_client_intelligence.config import AgentSettings
from openbox_langgraph_client_intelligence.governance import build_governed_agent
from openbox_langgraph_client_intelligence.profiles import get_profile


class GovernedAgentTests(unittest.TestCase):
    def test_worker_passes_only_its_agent_credentials_and_clears_sdk_fallbacks(self) -> None:
        for mode in ("workload", "legacy", "api-key-only"):
            for slug in ("amy", "barry", "colin"):
                with self.subTest(mode=mode, slug=slug):
                    workload_key = f"{slug}-workload-key" if mode == "workload" else None
                    did = f"did:aip:{slug}" if mode == "legacy" else None
                    legacy_key = f"{slug}-legacy-key" if mode == "legacy" else None
                    settings = AgentSettings(
                        profile_slug=slug,
                        openbox_url="https://core.example.test",
                        openbox_api_key=f"{slug}-api-key",
                        openbox_agent_name=f"{slug}-agent",
                        openbox_agent_did=did,
                        openbox_agent_private_key=legacy_key,
                        openbox_validate=True,
                        openai_model="test-model",
                        document_library_dir=Path("documents"),
                        report_output_dir=Path("output"),
                        filed_documents_dir=Path("filed_documents"),
                        openbox_workload_private_key=workload_key,
                    )
                    inherited = {
                        "OPENBOX_AGENT_DID": "another-agent-did",
                        "OPENBOX_AGENT_PRIVATE_KEY": "another-agent-legacy-key",
                        "OPENBOX_WORKLOAD_PRIVATE_KEY": "another-agent-workload-key",
                        "OPENBOX_LANGGRAPH_WORKLOAD_PRIVATE_KEY": "another-framework-key",
                        "OPENAI_API_KEY": "preserved-model-key",
                    }

                    def handler_factory(inherited_names=tuple(inherited), **kwargs):
                        # Omitted SDK arguments read these shared variables. They
                        # must already be gone when the real factory is called.
                        for name in inherited_names:
                            if name != "OPENAI_API_KEY":
                                self.assertNotIn(name, os.environ)
                        self.assertEqual(os.environ["OPENAI_API_KEY"], "preserved-model-key")
                        return kwargs

                    with patch.dict(os.environ, inherited, clear=True):
                        with patch(
                            "openbox_langgraph_client_intelligence.governance.create_openbox_graph_handler",
                            side_effect=handler_factory,
                        ):
                            arguments = build_governed_agent(
                                object(),
                                get_profile(slug),
                                settings,
                                session_id="session-1",
                                multi_agent_session_id="demo-1",
                            )
                    self.assertEqual(arguments["api_key"], settings.openbox_api_key)
                    self.assertEqual(arguments["agent_did"], did)
                    self.assertEqual(arguments["agent_private_key"], legacy_key)
                    self.assertEqual(arguments["agent_name"], settings.openbox_agent_name)
                    self.assertEqual(arguments["on_api_error"], "fail_closed")
                    if workload_key is None:
                        self.assertNotIn("workload_private_key", arguments)
                    else:
                        self.assertEqual(arguments["workload_private_key"], workload_key)
                    self.assertNotIn(f"{slug}-api-key", repr(settings))
                    self.assertNotIn(f"{slug}-legacy-key", repr(settings))


if __name__ == "__main__":
    unittest.main()
