import json
import unittest
from pathlib import Path

from singine.command import main


class WikipediaDocsSurfaceTest(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("/Users/skh/ws/git/github/sindoc/singine")
        self.actions = [
            "status",
            "refresh",
            "kernel-sync",
            "visualize",
            "test-case",
            "install-hooks",
            "preview-mail",
            "send-mail",
        ]

    def test_documentation_surfaces_match_action_inventory(self):
        markdown = (self.repo_root / "docs" / "wikipedia-contrib.md").read_text(encoding="utf-8")
        manpage = (self.repo_root / "man" / "singine-wikipedia.1").read_text(encoding="utf-8")
        sinlisp = (self.repo_root / "runtime" / "sinlisp" / "wikipedia_contrib.sinlisp").read_text(encoding="utf-8")
        javadoc = (self.repo_root / "core" / "java" / "singine" / "wikipedia" / "WikipediaContribCommand.java").read_text(encoding="utf-8")
        openapi = json.loads((self.repo_root / "schema" / "singine-wikipedia-api.json").read_text(encoding="utf-8"))

        request_enum = openapi["components"]["schemas"]["WikipediaContribRequest"]["properties"]["action"]["enum"]
        response_enum = openapi["components"]["schemas"]["WikipediaContribResponse"]["properties"]["action"]["enum"]

        self.assertEqual(request_enum, self.actions)
        self.assertEqual(response_enum, self.actions)

        for action in self.actions:
            self.assertIn(action, markdown)
            self.assertIn(action, manpage)
            self.assertIn(f"\"{action}\"", sinlisp)

        self.assertIn("ACTION_VISUALIZE = \"visualize\"", javadoc)
        self.assertIn("ACTION_TEST_CASE = \"test-case\"", javadoc)

    def test_status_command_still_reports_json(self):
        from io import StringIO
        from unittest.mock import patch

        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(["wikipedia", "contrib", "collibra", "--json"])
        self.assertEqual(code, 0, stderr.getvalue())
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["topic"], "collibra")


if __name__ == "__main__":
    unittest.main()
