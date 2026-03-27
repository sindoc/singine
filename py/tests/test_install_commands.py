import json
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class InstallCommandsTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_install_workstation_bootstraps_git_filter_repo(self):
        with patch("singine.command.install_launcher", return_value=Path("/tmp/.local/bin/singine")), \
             patch("singine.command.install_manpages"), \
             patch("singine.command.ensure_shell_paths", return_value={"bash": "/tmp/.bashrc"}), \
             patch("singine.command.install_git_filter_repo_tool", return_value=0) as mock_tool:
            code, stdout, stderr = self._run("install", "--mode", "workstation", "--json")
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["mode"], "workstation")
        self.assertEqual(payload["tools"], [{"tool": "git-filter-repo", "ok": True}])
        mock_tool.assert_called_once_with(json_output=False)

    def test_install_workstation_fails_if_git_filter_repo_install_fails(self):
        with patch("singine.command.install_launcher", return_value=Path("/tmp/.local/bin/singine")), \
             patch("singine.command.install_manpages"), \
             patch("singine.command.ensure_shell_paths", return_value={"bash": "/tmp/.bashrc"}), \
             patch("singine.command.install_git_filter_repo_tool", return_value=1):
            code, stdout, stderr = self._run("install", "--mode", "workstation", "--json")
        self.assertEqual(code, 1, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["tools"], [{"tool": "git-filter-repo", "ok": False}])

    def test_install_git_filter_repo_subject_dispatches(self):
        with patch("singine.command.install_git_filter_repo_tool", return_value=0) as mock_tool:
            code, stdout, stderr = self._run("install", "git-filter-repo")
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stdout, "")
        mock_tool.assert_called_once_with(json_output=False)


if __name__ == "__main__":
    unittest.main()
