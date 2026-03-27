import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class ControlCenterTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_control_center_writes_site_and_registers_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            dotfiles_repo = root / "dotfiles"
            ai_root = root / "ai-root"
            repo_ai = root / "repo-ai"
            output = root / "sindoc.local" / "control"
            home.mkdir()
            dotfiles_repo.mkdir()
            (home / ".bashrc").write_text("export TEST=1\n", encoding="utf-8")
            json_session = ai_root / "sessions" / "claude-demo"
            json_session.mkdir(parents=True)
            (json_session / "manifest.json").write_text(
                json.dumps(
                    {
                        "session_id": "claude-demo",
                        "provider": "claude",
                        "model": "claude-sonnet-4-6",
                        "started_at": "2026-03-22T08:00:00Z",
                        "ended_at": "2026-03-22T09:00:00Z",
                        "status": "closed",
                        "metadata": {},
                    }
                ),
                encoding="utf-8",
            )
            (json_session / "interactions.json").write_text("[]", encoding="utf-8")
            (json_session / "mandates.json").write_text("[]", encoding="utf-8")
            edn_session = repo_ai / "sessions" / "codex-demo"
            edn_session.mkdir(parents=True)
            (edn_session / "manifest.edn").write_text(
                """{:session/id "codex-demo"
 :session/provider :CODEX
 :session/model "gpt-5-codex"
 :session/started-at "2026-03-21T08:00:00Z"
 :session/ended-at "2026-03-21T09:00:00Z"
 :session/status :CLOSED
 :session/topic "edge work"
 :session/command-count 1}""",
                encoding="utf-8",
            )
            (edn_session / "commands.edn").write_text(
                """{:commands/log
 [{:cmd/id "cmd-001" :cmd/tool "Bash" :cmd/seq 1
   :cmd/resource "shell:docker ps"
   :cmd/purpose "Check edge containers"}]}""",
                encoding="utf-8",
            )

            with patch("singine.control_center._edge_containers", return_value=[{"name": "edge-edge-site-1", "image": "sindoc-collibra-edge-site:local", "status": "Up"}]):
                code, out, err = self._run(
                    "intranet",
                    "control-center",
                    "--home-dir",
                    str(home),
                    "--dotfiles-repo",
                    str(dotfiles_repo),
                    "--ai-root-dir",
                    str(ai_root),
                    "--repo-ai-dir",
                    str(repo_ai),
                    "--output-dir",
                    str(output),
                    "--json",
                )
            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertTrue((output / "index.html").exists())
            self.assertTrue((output / "control.json").exists())
            self.assertTrue((root / "sindoc.local" / "index.html").exists())
            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("edge-edge-site-1", html)
            self.assertIn("/dotfiles/", html)
            self.assertIn("/sessions/", html)
            site_index = (root / "sindoc.local" / "index.html").read_text(encoding="utf-8")
            self.assertIn("/control/", site_index)
            self.assertEqual(str(output / "index.html"), payload["artifacts"]["html"])


if __name__ == "__main__":
    unittest.main()
