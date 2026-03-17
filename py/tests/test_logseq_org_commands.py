import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class LogseqOrgCommandsTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_graph_discovery_and_org_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            graph = root / "demo-graph"
            pages = graph / "pages"
            journals = graph / "journals"
            pages.mkdir(parents=True)
            journals.mkdir(parents=True)

            (pages / "Sample Page.md").write_text(
                "title:: Sample Page\n"
                "author:: skh\n"
                "# Heading\n"
                "- TODO inspect export path\n",
                encoding="utf-8",
            )
            (journals / "2026_03_17.md").write_text(
                "- DONE journal entry\n",
                encoding="utf-8",
            )

            code, stdout, stderr = self._run("logseq", "graphs", "--root", str(root), "--json")
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(len(payload["graphs"]), 1)
            self.assertEqual(payload["graphs"][0]["name"], "demo-graph")

            output = root / "out.org"
            code, stdout, stderr = self._run(
                "logseq",
                "export-org",
                "--graph",
                "demo-graph",
                "--root",
                str(root),
                "--output",
                str(output),
                "--json",
            )
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["output_path"], str(output))
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("** Sample Page", rendered)
            self.assertIn(":AUTHOR: skh", rendered)
            self.assertIn("** Heading", rendered)
            self.assertIn("- TODO inspect export path", rendered)
            self.assertIn("** 2026-03-17", rendered)


if __name__ == "__main__":
    unittest.main()
