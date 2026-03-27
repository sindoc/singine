import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class PersonalOsBundleTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_personal_os_bundle_writes_expected_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "personal-os"
            code, out, err = self._run(
                "essay",
                "personal-os",
                "--output-dir",
                str(output_dir),
                "--json",
            )
            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertTrue((output_dir / "essay.md").exists())
            self.assertTrue((output_dir / "essay.html").exists())
            self.assertTrue((output_dir / "visual.svg").exists())
            self.assertTrue((output_dir / "essay.tex").exists())
            self.assertTrue((output_dir / "workflow" / "request.xml").exists())
            self.assertTrue((output_dir / "workflow" / "response.xml").exists())
            self.assertTrue((output_dir / "rules" / "personal_os_rules.sinlisp").exists())
            self.assertTrue((output_dir / "interfaces" / "adapter.bal").exists())
            self.assertTrue((output_dir / "interfaces" / "bridge.h").exists())
            self.assertTrue((output_dir / "interfaces" / "bridge.rs").exists())
            self.assertTrue((output_dir / "interfaces" / "bridge.pico").exists())
            self.assertTrue((output_dir / "interfaces" / "grammar.ixml").exists())
            self.assertTrue((output_dir / "manifest.json").exists())

            references = {item["label"]: item["path"] for item in payload["manifest"]["references"]}
            self.assertIn("sindoc42 onepager", references)
            self.assertIn("lutino Collibra metamodel root", references)
            self.assertIn("publish request xml", references)
            self.assertIn("publish response xml", references)

    def test_model_catalog_exposes_personal_os_essay(self):
        code, out, err = self._run("model", "inspect", "personal-os-essay")
        self.assertEqual(0, code, err)
        payload = json.loads(out)
        self.assertEqual("personal-os-essay", payload["name"])


if __name__ == "__main__":
    unittest.main()
