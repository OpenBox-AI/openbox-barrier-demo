from __future__ import annotations

import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from dotenv import dotenv_values

from openbox_langgraph_client_intelligence.config import AgentSettings
from openbox_langgraph_client_intelligence.profiles import get_profile


class AgentSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.environment = {
            "OPENBOX_API_URL": "https://core.example.test",
            "OPENAI_API_KEY": "sk-test",
            "DOCUMENT_LIBRARY_DIR": str(self.root),
            "REPORT_OUTPUT_DIR": str(self.root / "output"),
            "FILED_DOCUMENTS_DIR": str(self.root / "filed_documents"),
        }
        for slug in ("amy", "barry", "colin"):
            self.environment[f"{slug.upper()}_OPENBOX_API_KEY"] = f"{slug}-test-api-key"
            self.environment[f"{slug.upper()}_OPENBOX_AGENT_NAME"] = f"{slug}-agent"

    def test_each_profile_resolves_only_its_prefixed_credentials(self) -> None:
        for slug in ("amy", "barry", "colin"):
            self.environment[f"{slug.upper()}_OPENBOX_AGENT_DID"] = f"did:aip:{slug}-test"
            self.environment[f"{slug.upper()}_OPENBOX_AGENT_PRIVATE_KEY"] = f"{slug}-private-key"

        with patch.dict(os.environ, self.environment, clear=True):
            for slug in ("amy", "barry", "colin"):
                with self.subTest(slug=slug):
                    settings = AgentSettings.from_environment(get_profile(slug))
                    self.assertEqual(settings.profile_slug, slug)
                    self.assertEqual(settings.openbox_api_key, f"{slug}-test-api-key")
                    self.assertEqual(settings.openbox_agent_name, f"{slug}-agent")
                    self.assertEqual(settings.openbox_agent_did, f"did:aip:{slug}-test")
                    self.assertEqual(settings.openbox_agent_private_key, f"{slug}-private-key")
                    self.assertIsNone(settings.openbox_workload_private_key)
                    self.assertEqual(
                        settings.filed_documents_dir, (self.root / "filed_documents").resolve()
                    )

    def test_workload_keys_load_from_dotenv_without_legacy_did_credentials(self) -> None:
        for slug in ("amy", "barry", "colin"):
            parsed = dotenv_values(
                stream=StringIO(
                    f'{slug.upper()}_OPENBOX_WORKLOAD_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----'
                    f'\\n{slug}-key-contents\\n-----END PRIVATE KEY-----"\n'
                )
            )
            self.environment.update(
                {key: value for key, value in parsed.items() if value is not None}
            )

        with patch.dict(os.environ, self.environment, clear=True):
            for slug in ("amy", "barry", "colin"):
                with self.subTest(slug=slug):
                    settings = AgentSettings.from_environment(get_profile(slug))
                    self.assertEqual(
                        settings.openbox_workload_private_key,
                        "-----BEGIN PRIVATE KEY-----\n"
                        f"{slug}-key-contents\n"
                        "-----END PRIVATE KEY-----",
                    )
                    self.assertIsNone(settings.openbox_agent_did)
                    self.assertIsNone(settings.openbox_agent_private_key)
                    self.assertNotIn(f"{slug}-key-contents", repr(settings))
                    self.assertNotIn(f"{slug}-test-api-key", repr(settings))

    def test_blank_signing_fields_are_optional_and_do_not_read_global_keys(self) -> None:
        self.environment.update(
            {
                "AMY_OPENBOX_WORKLOAD_PRIVATE_KEY": "  ",
                "AMY_OPENBOX_AGENT_DID": "",
                "AMY_OPENBOX_AGENT_PRIVATE_KEY": "",
                "BARRY_OPENBOX_WORKLOAD_PRIVATE_KEY": "another-agent-key",
                "OPENBOX_WORKLOAD_PRIVATE_KEY": "global-workload-key",
                "OPENBOX_LANGGRAPH_WORKLOAD_PRIVATE_KEY": "framework-workload-key",
                "OPENBOX_AGENT_DID": "global-did",
                "OPENBOX_AGENT_PRIVATE_KEY": "global-legacy-key",
            }
        )
        with patch.dict(os.environ, self.environment, clear=True):
            settings = AgentSettings.from_environment(get_profile("amy"))
        self.assertIsNone(settings.openbox_workload_private_key)
        self.assertIsNone(settings.openbox_agent_did)
        self.assertIsNone(settings.openbox_agent_private_key)

    def test_partial_legacy_credentials_are_rejected_without_echoing_secrets(self) -> None:
        for suffix in ("AGENT_DID", "AGENT_PRIVATE_KEY"):
            with self.subTest(suffix=suffix):
                environment = {
                    **self.environment,
                    f"AMY_OPENBOX_{suffix}": "private-test-value",
                }
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaisesRegex(ValueError, "Set both AMY") as raised:
                        AgentSettings.from_environment(get_profile("amy"))
                self.assertNotIn("private-test-value", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
