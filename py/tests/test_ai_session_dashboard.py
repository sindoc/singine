import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class AiSessionDashboardTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dashboard_combines_json_and_edn_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            json_root = root / "json-ai"
            repo_ai = root / "repo-ai"
            output_dir = root / "site"

            json_session = json_root / "sessions" / "claude-session"
            json_session.mkdir(parents=True)
            (json_session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": "claude-session",
                        "provider": "claude",
                        "model": "claude-sonnet-4-6",
                        "started_at": "2026-03-20T10:00:00Z",
                        "ended_at": "2026-03-20T10:30:00Z",
                        "status": "closed",
                        "metadata": {"topic": "Manpage and docs work"},
                    }
                ),
                encoding="utf-8",
            )
            (json_session / "interactions.json").write_text(
                json.dumps(
                    [
                        {"role": "user", "created_at": "2026-03-20T10:01:00Z", "content": "Update the docs."},
                        {"role": "assistant", "created_at": "2026-03-20T10:02:00Z", "content": "I updated the docs."},
                    ]
                ),
                encoding="utf-8",
            )
            (json_session / "mandates.json").write_text("[]", encoding="utf-8")

            edn_session = repo_ai / "sessions" / "codex-session"
            edn_session.mkdir(parents=True)
            (edn_session / "manifest.edn").write_text(
                """{:session/id "codex-session"
 :session/provider :CODEX
 :session/model "gpt-5-codex"
 :session/started-at "2026-03-19T09:00:00Z"
 :session/ended-at "2026-03-19T09:40:00Z"
 :session/status :CLOSED
 :session/topic "Edge commands and shell work"
 :session/command-count 2}""",
                encoding="utf-8",
            )
            (edn_session / "commands.edn").write_text(
                """{:commands/log
 [{:cmd/id "cmd-001" :cmd/tool "Bash" :cmd/seq 1
   :cmd/resource "shell:git status"
   :cmd/purpose "Check repo status"}
  {:cmd/id "cmd-002" :cmd/tool "Read" :cmd/seq 2
   :cmd/resource "filesystem:/tmp/demo.txt"
   :cmd/purpose "Inspect a file"}]}""",
                encoding="utf-8",
            )

            code, out, err = self._run(
                "ai",
                "session",
                "dashboard",
                "--root-dir",
                str(json_root),
                "--repo-ai-dir",
                str(repo_ai),
                "--output-dir",
                str(output_dir),
                "--json",
            )
            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertTrue((output_dir / "index.html").exists())
            self.assertTrue((output_dir / "sessions.json").exists())
            self.assertTrue((root / "index.html").exists())
            self.assertEqual(2, payload["dashboard"]["summary"]["session_count"])
            providers = payload["dashboard"]["summary"]["provider_counts"]
            self.assertEqual(1, providers["claude"])
            self.assertEqual(1, providers["codex"])

            html = (output_dir / "index.html").read_text(encoding="utf-8")
            self.assertIn("Manpage and docs work", html)
            self.assertIn("shell:git status", html)
            site_index = (root / "index.html").read_text(encoding="utf-8")
            self.assertIn("/site/", site_index)


if __name__ == "__main__":
    unittest.main()
