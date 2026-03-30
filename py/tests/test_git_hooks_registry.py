import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class GitHooksRegistryTest(unittest.TestCase):
    def run_cmd(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{REPO_ROOT}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(REPO_ROOT)
        return subprocess.run(
            ["python3", "-m", "singine.command", *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_git_repos_list_json(self):
        proc = self.run_cmd("git", "repos", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        ids = {item["id"] for item in payload["repos"]}
        self.assertIn("datatech-wiki-kg", ids)
        self.assertIn("singine", ids)

    def test_git_hooks_graph_mermaid(self):
        proc = self.run_cmd("git", "hooks", "graph")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("graph TD", proc.stdout)
        self.assertIn("datatech-wiki-kg", proc.stdout)

    def test_git_hooks_install_writes_scripts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp) / "repo"
            hooks_dir = repo_root / ".git" / "hooks"
            hooks_dir.mkdir(parents=True)
            registry_path = Path(tmp) / "git-repos.json"
            payload = {
                "version": 1,
                "repos": [
                    {
                        "id": "tmp-repo",
                        "path": str(repo_root),
                        "archetype": "test",
                        "hooks": {
                            "pre-commit": {"commands": []},
                            "post-commit": {"commands": []},
                            "post-merge": {"commands": []},
                        },
                    }
                ],
            }
            registry_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{REPO_ROOT}:{env['PYTHONPATH']}" if env.get("PYTHONPATH") else str(REPO_ROOT)
            env["SINGINE_GIT_REPO_REGISTRY"] = str(registry_path)
            proc = subprocess.run(
                ["python3", "-m", "singine.command", "git", "hooks", "install", "tmp-repo", "--json"],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            for name in ["pre-commit", "post-commit", "post-merge"]:
                text = (hooks_dir / name).read_text(encoding="utf-8")
                self.assertIn("python3 -m singine.command git hooks run", text)
