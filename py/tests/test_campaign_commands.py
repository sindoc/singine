import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class CampaignCommandsTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dataset_plan_includes_trusted_realm_and_writes_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "campaign.json"
            code, out, err = self._run(
                "campaign",
                "dataset-plan",
                "--title",
                "Molecular Imaging Governance",
                "--brief",
                "Launch a governed dataset collection for Collibra, AI/LLM/MLOps, health, functional medicine, functional programming, and molecular biology.",
                "--contract",
                "msa-001",
                "--contact",
                "lead-steward",
                "--trusted-realm",
                "research.example",
                "--vocabulary-term",
                "evidence lineage",
                "--output",
                str(output_path),
                "--json",
            )
            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertEqual(str(output_path), payload["output_path"])
            self.assertIn("molecularimaging.be", payload["scope"]["trusted_realms"])
            self.assertIn("research.example", payload["scope"]["trusted_realms"])
            self.assertEqual(3, len(payload["standards_phases"]))
            self.assertGreaterEqual(len(payload["datasets"]), 6)
            self.assertTrue(output_path.exists())

            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["campaign_id"], written["campaign_id"])

    def test_model_catalog_exposes_dataset_campaign(self):
        code, out, err = self._run("model", "inspect", "dataset-campaign")
        self.assertEqual(0, code, err)
        payload = json.loads(out)
        self.assertEqual("dataset-campaign", payload["name"])
        self.assertEqual("reference-data", payload["family"])


if __name__ == "__main__":
    unittest.main()
