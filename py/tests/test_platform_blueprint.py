import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class PlatformBlueprintTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_platform_blueprint_writes_scaffold(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "platform"
            code, out, err = self._run(
                "platform",
                "blueprint",
                "--output-dir",
                str(output_dir),
                "--json",
            )
            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertTrue((output_dir / "platform-blueprint.json").exists())
            self.assertTrue((output_dir / "platform-blueprint.md").exists())
            self.assertTrue((output_dir / "deploy" / "openshift-template.yaml").exists())
            self.assertTrue((output_dir / "webapp" / "package.json").exists())
            self.assertTrue((output_dir / "python-api" / "service.py").exists())
            self.assertTrue((output_dir / "spring-adapter" / "src" / "main" / "java" / "io" / "sindoc" / "singine" / "platform" / "MetadataProtocolAdapter.java").exists())

            attrs = payload["blueprint"]["collibra_alignment"]["plain_text_attributes"]
            names = [item["name"] for item in attrs]
            self.assertIn("Script Body", names)
            self.assertIn("Source Code", names)
            self.assertIn("Authorised Commands", names)

    def test_model_catalog_exposes_platform_blueprint(self):
        code, out, err = self._run("model", "inspect", "platform-blueprint")
        self.assertEqual(0, code, err)
        payload = json.loads(out)
        self.assertEqual("platform-blueprint", payload["name"])


if __name__ == "__main__":
    unittest.main()
