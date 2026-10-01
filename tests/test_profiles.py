from __future__ import annotations

import unittest

from openbox_langgraph_client_intelligence.profiles import PROFILES, get_profile


class AgentProfileTests(unittest.TestCase):
    def test_profiles_define_the_intended_related_client_research(self) -> None:
        amy_queries = " ".join(lead.query for lead in PROFILES["amy"].leads)
        barry_queries = " ".join(lead.query for lead in PROFILES["barry"].leads)
        colin_queries = " ".join(lead.query for lead in PROFILES["colin"].leads)

        self.assertIn("Coca Cola", amy_queries)
        self.assertIn("Pepsi", amy_queries)
        self.assertIn("Bank of America", amy_queries)

        self.assertIn("Pepsi", barry_queries)
        self.assertIn("Coca Cola", barry_queries)
        self.assertIn("Citi", barry_queries)

        self.assertIn("Coca Cola", colin_queries)
        self.assertIn("Pepsi", colin_queries)
        self.assertIn("Citi", colin_queries)
        self.assertIn("Bank of America", colin_queries)

    def test_amy_and_barry_have_the_correct_primary_client_and_cross_client_lead(self) -> None:
        amy = PROFILES["amy"]
        barry = PROFILES["barry"]

        self.assertIn("Coca-Cola", amy.role)
        self.assertEqual(amy.leads[0].label, "primary-coca-cola")
        self.assertEqual(amy.leads[1].label, "related-pepsi")
        self.assertEqual(amy.leads[2].label, "related-bank-of-america")

        self.assertIn("Pepsi", barry.role)
        self.assertEqual(barry.leads[0].label, "primary-pepsi")
        self.assertEqual(barry.leads[1].label, "related-coca-cola")
        self.assertEqual(barry.leads[2].label, "related-citi")

    def test_profiles_contain_business_intent_not_access_rules(self) -> None:
        for profile in PROFILES.values():
            self.assertFalse(hasattr(profile, "allowed_documents"))
            self.assertFalse(hasattr(profile, "denied_documents"))
            self.assertGreater(len(profile.leads), 1)

    def test_amy_and_barry_sweep_every_seeded_client_without_access_rules(self) -> None:
        amy = PROFILES["amy"]
        barry = PROFILES["barry"]
        expected_targets = [
            ("0001", "10001", "Coca-Cola"),
            ("0001", "20001", "PepsiCo"),
            ("0001", "30001", "Bank of America"),
            ("0001", "30002", "Citi Bank"),
        ]

        self.assertEqual(
            [
                (target.matter_id, target.client_id, target.client_name)
                for target in amy.filing_targets
            ],
            expected_targets,
        )
        self.assertEqual(
            [
                (target.matter_id, target.client_id, target.client_name)
                for target in barry.filing_targets
            ],
            expected_targets,
        )
        for profile in (amy, barry):
            for target in profile.filing_targets:
                self.assertFalse(hasattr(target, "expected_status"))
        self.assertEqual(PROFILES["colin"].filing_targets, ())

    def test_unknown_profile_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown agent"):
            get_profile("unknown")


if __name__ == "__main__":
    unittest.main()
