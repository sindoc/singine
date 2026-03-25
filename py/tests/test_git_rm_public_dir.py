import json
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

from singine.command import main


class GitRmPublicDirCommandTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def _mock_run(self, cmd, cwd=None, capture_output=True, text=True, check=True, timeout=60):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        if cmd[:3] == ["git", "rev-parse", "--show-toplevel"]:
            proc.stdout = "/tmp/singine\n"
        elif cmd[:4] == ["git", "remote", "get-url", "origin"]:
            proc.stdout = "git@github.com:sindoc/singine.git\n"
        elif cmd[:4] == ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads"]:
            proc.stdout = "main\nrelease/2026Q3\nfeature/nope\n"
        elif cmd[:3] == ["git", "show-ref", "--verify"]:
            proc.returncode = 0
        elif cmd[:5] == ["git", "rev-list", "-n", "1", "main"]:
            proc.stdout = "abc123\n"
        elif cmd[:5] == ["git", "rev-list", "-n", "1", "release/2026Q3"]:
            proc.stdout = "def456\n"
        elif cmd[:5] == ["git", "rev-list", "-n", "1", "feature/nope"]:
            proc.stdout = ""
        else:
            raise AssertionError(f"unexpected command: {cmd}")
        if check and proc.returncode != 0:
            raise RuntimeError("unexpected non-zero mock process")
        return proc

    def test_git_rm_public_dir_plan_json(self):
        with patch("singine.command.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
             patch("singine.command.subprocess.run", side_effect=self._mock_run):
            code, stdout, stderr = self._run(
                "git", "rm-public-dir", "github/singine", "prod/Q3",
                "--branch", "main",
                "--branch", "release/2026Q3",
                "--json",
            )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["public_dir_filter"], "prod/Q3/")
        self.assertEqual(payload["branches"], ["main", "release/2026Q3"])
        self.assertTrue(payload["repo_matches_current_repo"])
        self.assertEqual(
            payload["commands"]["push"][0],
            "git push --force-with-lease origin refs/heads/main:refs/heads/main",
        )
        self.assertIn("--path prod/Q3/", payload["commands"]["rewrite"][0])

    def test_git_rm_public_dir_requires_relative_path(self):
        code, stdout, stderr = self._run(
            "git", "rm-public-dir", "github/singine", "/prod/Q3",
            "--branch", "main",
        )
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("must be relative", stderr)

    def test_git_rm_public_dir_requires_branches(self):
        code, stdout, stderr = self._run(
            "git", "rm-public-dir", "github/singine", "prod/Q3",
        )
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("unless you pass -all", stderr)

    def test_git_rm_public_dir_all_discovers_matching_branches(self):
        with patch("singine.command.shutil.which", side_effect=lambda name: f"/usr/bin/{name}"), \
             patch("singine.command.subprocess.run", side_effect=self._mock_run):
            code, stdout, stderr = self._run(
                "git", "rm-public-dir", "github/singine", "prod/Q3",
                "-all",
                "--json",
            )
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        self.assertEqual(payload["branches"], ["main", "release/2026Q3"])
        self.assertEqual(payload["all_branch_scan"]["matched"], ["main", "release/2026Q3"])
        self.assertIn("local heads", payload["warnings"][0])


if __name__ == "__main__":
    unittest.main()
