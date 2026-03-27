import json
import sqlite3
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main
from singine.zip_neighborhood_demo import build_zip_neighborhood_demo


class ZipNeighborhoodDemoTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_notebook_builder_exposes_kafka_and_multilingual_rows(self):
        demo = build_zip_neighborhood_demo()
        self.assertIn("kafka", demo["messages"])
        self.assertEqual(3, len(demo["datasets"]))
        self.assertTrue(all(row["languages"] for row in demo["datasets"]))
        self.assertTrue(all("collibra_codes" in row for row in demo["datasets"]))

    def test_cli_writes_raw_staging_publication_and_domain_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "bundle"
            db_path = Path(tmpdir) / "domain.db"
            code, out, err = self._run(
                "demo",
                "zip-neighborhood",
                "--output-dir",
                str(output_dir),
                "--db",
                str(db_path),
                "--json",
            )
            self.assertEqual(0, code, err)
            manifest = json.loads(out)

            self.assertTrue((output_dir / "rabbitmq" / "raw" / "01-1000.json").exists())
            self.assertTrue((output_dir / "rabbitmq" / "staging" / "01-1000.json").exists())
            self.assertTrue((output_dir / "kafka" / "topic.json").exists())
            self.assertTrue((output_dir / "publication" / "demo.md").exists())
            self.assertTrue((output_dir / "publication" / "demo.xml").exists())
            self.assertTrue((output_dir / "publication" / "demo.mediawiki").exists())
            self.assertEqual(str(output_dir / "publication" / "demo.md"), manifest["artifacts"]["markdown"])

            conn = sqlite3.connect(str(db_path))
            rows = conn.execute("SELECT event_type, subject_id FROM domain_event ORDER BY occurred_at").fetchall()
            conn.close()
            self.assertEqual(2, len(rows))
            self.assertEqual("AI_SESSION_STARTED", rows[0][0])
            self.assertEqual("CATALOG_ASSET_REGISTERED", rows[1][0])


if __name__ == "__main__":
    unittest.main()
