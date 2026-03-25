import json
import os
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main
from singine.template import _npm_package_name


class TemplateCommandsTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_npm_scope_preserves_hyphen(self):
        self.assertEqual(_npm_package_name("Silkpage UI", "my-team"), "@my-team/silkpage-ui")

    def test_template_create_honors_explicit_current_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            old_cwd = Path.cwd()
            try:
                os.chdir(workdir)
                code, stdout, stderr = self._run(
                    "template",
                    "create",
                    "npm",
                    "Silkpage UI",
                    "--dir",
                    ".",
                    "--scope",
                    "my-team",
                    "--json",
                )
            finally:
                os.chdir(old_cwd)
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["target_dir"], ".")
            self.assertTrue((workdir / "package.json").exists())
            pkg = json.loads((workdir / "package.json").read_text(encoding="utf-8"))
            self.assertEqual(pkg["name"], "@my-team/silkpage-ui")

    def test_template_library_lists_archetypes(self):
        code, stdout, stderr = self._run("template", "list", "--family", "archetype", "--json")
        self.assertEqual(code, 0, stderr)
        payload = json.loads(stdout)
        names = [item["name"] for item in payload["items"]]
        self.assertIn("personal-os-essay", names)
        self.assertIn("platform-blueprint", names)

    def test_template_materialize_personal_os_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "personal-os"
            code, stdout, stderr = self._run(
                "template",
                "materialize",
                "personal-os-essay",
                "--output-dir",
                str(output_dir),
                "--json",
            )
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue((output_dir / "essay.md").exists())
            self.assertTrue((output_dir / "interfaces" / "grammar.ixml").exists())
            self.assertEqual(str(output_dir / "essay.md"), payload["artifacts"]["markdown"])

    def test_archetype_alias_materializes_platform_blueprint(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "blueprint"
            code, stdout, stderr = self._run(
                "archetype",
                "materialize",
                "platform-blueprint",
                "--output-dir",
                str(output_dir),
                "--json",
            )
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue((output_dir / "platform-blueprint.json").exists())
            self.assertEqual(str(output_dir / "platform-blueprint.md"), payload["artifacts"]["markdown"])

    def test_gen_command_capture_and_list_materialize_assets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root_dir = Path(tmpdir) / "command-library"
            out_dir = root_dir / "site"
            code, stdout, stderr = self._run(
                "gen",
                "command",
                "capture",
                "--raw",
                "cd $HOME/ws && singine gen command list --output-dir ~/tmp/cmds",
                "--shell",
                "bash",
                "--pwd",
                "/Users/skh/ws/today",
                "--exit-code",
                "0",
                "--root-dir",
                str(root_dir),
                "--json",
            )
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue((root_dir / "commands.jsonl").exists())
            self.assertEqual(payload["event"]["variables"], ["$HOME", "~"])

            code, stdout, stderr = self._run(
                "gen",
                "command",
                "list",
                "--root-dir",
                str(root_dir),
                "--output-dir",
                str(out_dir),
                "--json",
            )
            self.assertEqual(code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue((out_dir / "command-library.json").exists())
            self.assertTrue((out_dir / "command-library.md").exists())
            self.assertTrue((out_dir / "command-library.html").exists())
            self.assertEqual(payload["assets"][0]["abstract_command"], "cd $HOME/ws && singine gen command list --output-dir ~/tmp/cmds")


if __name__ == "__main__":
    unittest.main()
