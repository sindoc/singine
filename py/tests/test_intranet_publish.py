import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class IntranetPublishTest(unittest.TestCase):
    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_publish_writes_deploy_bundle_and_silkpage_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            site_root = root / "target" / "sindoc.local"
            deploy_root = root / "var" / "deploy" / "sindoc.local"
            silkpage_root = root / "silkpage"
            ssl_dir = root / "ssl"

            site_root.mkdir(parents=True, exist_ok=True)
            (site_root / "index.html").write_text("<h1>home</h1>", encoding="utf-8")
            (site_root / "sessions").mkdir(parents=True, exist_ok=True)
            (site_root / "sessions" / "index.html").write_text("<h2>sessions</h2>", encoding="utf-8")
            ssl_dir.mkdir(parents=True)
            (ssl_dir / "sindoc.local.crt").write_text("crt", encoding="utf-8")
            (ssl_dir / "sindoc.local.key").write_text("key", encoding="utf-8")
            (ssl_dir / "cacert.pem").write_text("ca", encoding="utf-8")

            code, out, err = self._run(
                "intranet",
                "publish",
                "--site-root",
                str(site_root),
                "--deploy-root",
                str(deploy_root),
                "--silkpage-root",
                str(silkpage_root),
                "--ssl-dir",
                str(ssl_dir),
                "--json",
            )

            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertTrue((site_root / "deploy" / "index.html").exists())
            self.assertTrue((site_root / "deploy" / "deploy.json").exists())
            self.assertTrue((site_root / "deploy" / "firefox-policies.json").exists())
            self.assertTrue((deploy_root / "index.html").exists())
            self.assertTrue((deploy_root / "sessions" / "index.html").exists())
            self.assertTrue((silkpage_root / "dev" / "infra" / "vhosts" / "sindoc.local.conf").exists())
            self.assertTrue((silkpage_root / "dev" / "infra" / "hosts.sindoc.local.fragment").exists())
            html = (site_root / "deploy" / "index.html").read_text(encoding="utf-8")
            self.assertIn("Firefox", html)
            self.assertIn("sindoc.local", html)
            index_html = (site_root / "index.html").read_text(encoding="utf-8")
            self.assertIn("/deploy/", index_html)
            self.assertEqual(str(deploy_root), payload["sync"]["target"])
            self.assertTrue(payload["certificate"]["ready"])

    def test_publish_can_skip_sync(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            site_root = root / "target" / "sindoc.local"
            silkpage_root = root / "silkpage"
            ssl_dir = root / "ssl"
            site_root.mkdir(parents=True)
            ssl_dir.mkdir(parents=True)
            (site_root / "index.html").write_text("<h1>home</h1>", encoding="utf-8")

            code, out, err = self._run(
                "intranet",
                "publish",
                "--site-root",
                str(site_root),
                "--deploy-root",
                str(root / "deploy"),
                "--silkpage-root",
                str(silkpage_root),
                "--ssl-dir",
                str(ssl_dir),
                "--no-sync",
                "--json",
            )

            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertEqual(0, payload["sync"]["count"])
            self.assertFalse(payload["certificate"]["ready"])

    def test_cert_bootstrap_writes_expected_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ssl_dir = Path(tmpdir) / "ssl"

            def fake_run(parts, check, capture_output, text):
                if "-out" in parts:
                    out_path = Path(parts[parts.index("-out") + 1])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text("generated\n", encoding="utf-8")
                if "-CAcreateserial" in parts:
                    ca_cert = Path(parts[parts.index("-CA") + 1])
                    (ca_cert.parent / "cacert.srl").write_text("01\n", encoding="utf-8")
                return None

            with patch("singine.intranet_deploy.shutil.which", return_value="/usr/bin/openssl"), patch(
                "singine.intranet_deploy.subprocess.run",
                side_effect=fake_run,
            ):
                code, out, err = self._run(
                    "intranet",
                    "cert-bootstrap",
                    "--ssl-dir",
                    str(ssl_dir),
                    "--json",
                )

            self.assertEqual(0, code, err)
            payload = json.loads(out)
            self.assertTrue((ssl_dir / "cacert.pem").exists())
            self.assertTrue((ssl_dir / "sindoc.local.key").exists())
            self.assertTrue((ssl_dir / "sindoc.local.crt").exists())
            self.assertTrue((ssl_dir / ".cacert_path").exists())
            self.assertGreaterEqual(len(payload["commands_run"]), 4)


if __name__ == "__main__":
    unittest.main()
