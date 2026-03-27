import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class DotfilesCommandsTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dotfiles_inspect_and_capture(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            repo = root / "dotfiles"
            home.mkdir()
            repo.mkdir()

            (home / ".bashrc").write_text("export TEST=1\n", encoding="utf-8")
            (home / ".vimrc").write_text("set number\n", encoding="utf-8")
            (home / ".claude").mkdir()
            (home / ".claude" / "settings.json").write_text('{"theme":"dark"}\n', encoding="utf-8")

            code, out, err = self._run(
                "dotfiles",
                "inspect",
                "--home-dir",
                str(home),
                "--dotfiles-repo",
                str(repo),
                "--json",
            )
            self.assertEqual(0, code, err)
            payload = json.loads(out)
            items = {item["name"]: item for item in payload["items"]}
            self.assertTrue(items["bashrc"]["home_exists"])
            self.assertFalse(items["bashrc"]["repo_exists"])

            capture_code, capture_out, capture_err = self._run(
                "dotfiles",
                "capture",
                "bashrc",
                "--home-dir",
                str(home),
                "--dotfiles-repo",
                str(repo),
                "--json",
            )
            self.assertEqual(0, capture_code, capture_err)
            capture_payload = json.loads(capture_out)
            self.assertTrue((repo / "dot" / ".bashrc").exists())
            self.assertEqual(str(repo / "dot" / ".bashrc"), capture_payload["target"])

            manifest_code, manifest_out, manifest_err = self._run(
                "dotfiles",
                "capture",
                "claude-home",
                "--home-dir",
                str(home),
                "--dotfiles-repo",
                str(repo),
                "--json",
            )
            self.assertEqual(0, manifest_code, manifest_err)
            manifest_payload = json.loads(manifest_out)
            self.assertTrue((repo / "state" / "claude-home" / "manifest.json").exists())
            self.assertEqual(str(repo / "state" / "claude-home" / "manifest.json"), manifest_payload["target"])

    def test_dotfiles_dashboard_writes_html(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            home = root / "home"
            repo = root / "dotfiles"
            output = root / "site"
            home.mkdir()
            repo.mkdir()
            (home / ".bash_profile").write_text("export HELLO=world\n", encoding="utf-8")

            code, out, err = self._run(
                "dotfiles",
                "dashboard",
                "--home-dir",
                str(home),
                "--dotfiles-repo",
                str(repo),
                "--output-dir",
                str(output),
                "--json",
            )
            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertTrue((output / "index.html").exists())
            self.assertTrue((output / "dotfiles.json").exists())
            self.assertTrue((root / "index.html").exists())
            self.assertEqual(str(output / "index.html"), payload["artifacts"]["html"])
            self.assertIn("/site/", (root / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
