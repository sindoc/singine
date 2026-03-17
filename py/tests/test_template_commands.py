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


if __name__ == "__main__":
    unittest.main()
