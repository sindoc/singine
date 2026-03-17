import json
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from singine.command import main


class _MockHTTPResponse:
    def __init__(self, payload, status=200):
        self._payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class ServerSurfaceCommandsTest(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path("/Users/skh/ws/git/github/sindoc/singine")
        self.port = 18080

    def _mock_urlopen(self, request, timeout=10):
        url = request.full_url if hasattr(request, "full_url") else request
        if url.endswith("/health"):
            return _MockHTTPResponse({"status": "ok", "platform": "singine", "camel": "started"})
        if "/bridge?action=sources" in url:
            return _MockHTTPResponse({"ok": True, "sources": [{"name": "mock-source", "kind": "test"}]})
        if url.endswith("/api"):
            return _MockHTTPResponse({"name": "mock-graph", "uuid": "logseq-test"})
        raise HTTPError(url, 404, "not found", hdrs=None, fp=None)

    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr), patch("singine.server_surface.urlopen", side_effect=self._mock_urlopen):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def test_server_logseq_and_snapshot_commands(self):
        inspect_code, inspect_stdout, inspect_stderr = self._run("server", "inspect", "--host", "127.0.0.1", "--port", str(self.port), "--json")
        self.assertEqual(inspect_code, 0, inspect_stderr)
        inspect_payload = json.loads(inspect_stdout)
        self.assertEqual(inspect_payload["server"]["port"], self.port)
        self.assertIn("taxonomy_path", inspect_payload["activity_api"])
        self.assertIn("photo/PhotoReviewActivities.java", inspect_payload["activity_api"]["interfaces"])

        health_code, health_stdout, health_stderr = self._run("server", "health", "--host", "127.0.0.1", "--port", str(self.port), "--json")
        self.assertEqual(health_code, 0, health_stderr)
        health_payload = json.loads(health_stdout)
        self.assertEqual(health_payload["data"]["status"], "ok")

        bridge_code, bridge_stdout, bridge_stderr = self._run("server", "bridge", "--host", "127.0.0.1", "--port", str(self.port), "--action", "sources", "--json")
        self.assertEqual(bridge_code, 0, bridge_stderr)
        bridge_payload = json.loads(bridge_stdout)
        self.assertEqual(bridge_payload["data"]["sources"][0]["name"], "mock-source")

        logseq_code, logseq_stdout, logseq_stderr = self._run("logseq", "ping", "--base-url", f"http://127.0.0.1:{self.port}", "--token", "test-token", "--json")
        self.assertEqual(logseq_code, 0, logseq_stderr)
        logseq_payload = json.loads(logseq_stdout)
        self.assertEqual(logseq_payload["data"]["name"], "mock-graph")

        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_path = Path(tmpdir) / "snapshot.json"
            snapshot_code, snapshot_stdout, snapshot_stderr = self._run(
                "snapshot", "save",
                "--output", str(snapshot_path),
                "--host", "127.0.0.1",
                "--port", str(self.port),
                "--logseq-url", f"http://127.0.0.1:{self.port}",
                "--logseq-token", "test-token",
                "--json",
            )
            self.assertEqual(snapshot_code, 0, snapshot_stderr)
            payload = json.loads(snapshot_stdout)
            self.assertTrue(snapshot_path.exists())
            saved = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["output_path"], str(snapshot_path))
            self.assertEqual(saved["server"]["server"]["port"], self.port)
            self.assertTrue(saved["logseq"]["token_present"])


if __name__ == "__main__":
    unittest.main()
