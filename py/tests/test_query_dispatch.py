"""Tests for singine query multi-backend dispatcher — singine API 1.0.

Each test method documents the request (CLI invocation + arguments) and the
expected response (JSON envelope shape and field contracts) for singine 1.0.

Envelope contract (all backends):
    {
      "ok":          bool,
      "api_version": "1.0",
      "backend":     str,   # one of git/emacs/logseq/xml/sql/sparql/graphql/docker/sys
      "query":       str,
      "ts":          str,   # ISO-8601 UTC timestamp
      "result":      dict
    }

External-process backends (git, emacs, docker, logseq) are tested with
subprocess/urlopen mocks so the suite runs offline without side-effects.
In-process backends (xml, sql, sparql, graphql, sys) run against real
temp files.
"""

import json
import platform
import tempfile
import textwrap
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from singine.command import main
from singine.query_dispatch import QUERY_API_VERSION


# ── helpers ────────────────────────────────────────────────────────────────────


def _run(*args):
    """Invoke ``singine.command.main`` with captured stdout/stderr.

    Returns (exit_code, stdout_text, stderr_text).
    """
    stdout = StringIO()
    stderr = StringIO()
    with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
        code = main(list(args))
    return code, stdout.getvalue(), stderr.getvalue()


def _parse(stdout: str) -> dict:
    """Parse the first JSON object emitted to stdout."""
    return json.loads(stdout)


def _assert_envelope(test: unittest.TestCase, payload: dict, backend: str, query: str) -> None:
    """Assert that *payload* is a well-formed singine 1.0 query envelope."""
    test.assertEqual(payload.get("api_version"), QUERY_API_VERSION, "api_version must be '1.0'")
    test.assertEqual(payload.get("backend"), backend, f"backend must be '{backend}'")
    test.assertEqual(payload.get("query"), query, "query must echo the input")
    test.assertIn("ok", payload, "envelope must contain 'ok'")
    test.assertIn("ts", payload, "envelope must contain 'ts'")
    test.assertIn("result", payload, "envelope must contain 'result'")


# ── git ────────────────────────────────────────────────────────────────────────


class GitQueryTest(unittest.TestCase):
    """singine query git — git log/show/status/diff/files.

    Request:  singine query git <pattern> [--action log|show|status|diff|files]
                                          [--repo <path>] [--limit N]
    Response: JSON envelope, result.lines list, result.action, result.repo
    """

    def _mock_run(self, cmd, capture_output, text, timeout):
        proc = MagicMock()
        proc.stdout = "abc1234 Add electricity domain\ndef5678 Add Collibra link\n"
        proc.returncode = 0
        return proc

    def test_git_log_query(self):
        """Request: singine query git electricity --action log --repo /tmp
        Response: ok=true, backend=git, result.action=log, result.lines non-empty list.
        """
        with patch("singine.query_dispatch.subprocess.run", side_effect=self._mock_run):
            code, stdout, _ = _run("query", "git", "electricity", "--action", "log", "--repo", "/tmp")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "git", "electricity")
        self.assertTrue(p["ok"])
        self.assertEqual(p["result"]["action"], "log")
        self.assertIsInstance(p["result"]["lines"], list)
        self.assertGreater(p["result"]["count"], 0)

    def test_git_status_query(self):
        """Request: singine query git "" --action status --repo /tmp
        Response: ok=true, backend=git, result.action=status.
        """
        with patch("singine.query_dispatch.subprocess.run", side_effect=self._mock_run):
            code, stdout, _ = _run("query", "git", "--action", "status", "--repo", "/tmp")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "git", "")
        self.assertEqual(p["result"]["action"], "status")

    def test_git_not_found(self):
        """Request: singine query git foo (git binary absent)
        Response: ok=false, result.error contains 'not found'.
        """
        def _raise(cmd, **kw):
            raise FileNotFoundError("git")

        with patch("singine.query_dispatch.subprocess.run", side_effect=_raise):
            code, stdout, _ = _run("query", "git", "foo", "--repo", "/tmp")
        self.assertEqual(code, 1)
        p = _parse(stdout)
        self.assertFalse(p["ok"])
        self.assertIn("error", p["result"])


# ── emacs ──────────────────────────────────────────────────────────────────────


class EmacsQueryTest(unittest.TestCase):
    """singine query emacs — emacsclient --eval.

    Request:  singine query emacs <elisp-expr> [--bin emacsclient] [--socket name]
    Response: JSON envelope, result.output contains evaluated value,
              result.returncode int.
    """

    def test_emacs_eval(self):
        """Request: singine query emacs '(+ 1 1)'
        Response: ok=true, backend=emacs, result.output='2'.
        """
        proc = MagicMock()
        proc.stdout = "2\n"
        proc.returncode = 0
        with patch("singine.query_dispatch.subprocess.run", return_value=proc):
            code, stdout, _ = _run("query", "emacs", "(+ 1 1)")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "emacs", "(+ 1 1)")
        self.assertTrue(p["ok"])
        self.assertEqual(p["result"]["output"], "2")
        self.assertEqual(p["result"]["returncode"], 0)

    def test_emacs_daemon_not_running(self):
        """Request: singine query emacs '(message "hi")' (no daemon)
        Response: ok=false, result.error mentions timeout.
        """
        import subprocess as sp

        def _timeout(*a, **kw):
            raise sp.TimeoutExpired(cmd="emacsclient", timeout=10)

        with patch("singine.query_dispatch.subprocess.run", side_effect=_timeout):
            code, stdout, _ = _run("query", "emacs", '(message "hi")')
        self.assertEqual(code, 1)
        p = _parse(stdout)
        self.assertFalse(p["ok"])
        self.assertIn("timed out", p["result"]["error"])

    def test_emacs_not_found(self):
        """Request: singine query emacs '(+ 1 1)' --bin /nonexistent
        Response: ok=false, result.error contains 'not found'.
        """
        with patch("singine.query_dispatch.subprocess.run", side_effect=FileNotFoundError):
            code, stdout, _ = _run("query", "emacs", "(+ 1 1)", "--bin", "/nonexistent")
        self.assertEqual(code, 1)
        p = _parse(stdout)
        self.assertFalse(p["ok"])
        self.assertIn("not found", p["result"]["error"])


# ── logseq ─────────────────────────────────────────────────────────────────────


class LogseqQueryTest(unittest.TestCase):
    """singine query logseq — Logseq HTTP API Datalog q.

    Request:  singine query logseq <q-expr> --token <tok> [--base-url url]
    Response: JSON envelope, result.data contains Logseq query result.
    """

    def _mock_urlopen(self, request, timeout=10):
        resp = MagicMock()
        resp.read.return_value = json.dumps([["page-a"], ["page-b"]]).encode("utf-8")
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        return resp

    def test_logseq_q_query(self):
        """Request: singine query logseq '[:find ?b :where [?b :block/name]]' --token tok
        Response: ok=true, backend=logseq, result.data is a list.
        """
        expr = "[:find ?b :where [?b :block/name]]"
        with patch("singine.query_dispatch.urlopen", side_effect=self._mock_urlopen):
            code, stdout, _ = _run("query", "logseq", expr, "--token", "tok")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "logseq", expr)
        self.assertTrue(p["ok"])
        self.assertIsInstance(p["result"]["data"], list)

    def test_logseq_xml_query(self):
        """Request: singine query logseq '[:find ?b :where [?b :block/properties]]' --token tok
        Demonstrates the logseq-xml query pattern: Datalog result returned as
        structured JSON suitable for XML serialisation.
        Response: ok=true, result.q echoes the expression.
        """
        expr = "[:find ?b :where [?b :block/properties]]"
        with patch("singine.query_dispatch.urlopen", side_effect=self._mock_urlopen):
            code, stdout, _ = _run("query", "logseq", expr, "--token", "tok")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "logseq", expr)
        self.assertEqual(p["result"]["q"], expr)

    def test_logseq_sql_query_pattern(self):
        """Request: singine query logseq '[:find ?n :where [?b :block/name ?n]]' --token tok
        Demonstrates the logseq-sql query pattern: property-level Datalog as a
        stand-in for SQL-style column selection.
        Response: ok=true, backend=logseq.
        """
        expr = "[:find ?n :where [?b :block/name ?n]]"
        with patch("singine.query_dispatch.urlopen", side_effect=self._mock_urlopen):
            code, stdout, _ = _run("query", "logseq", expr, "--token", "tok")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertTrue(p["ok"])
        self.assertEqual(p["backend"], "logseq")

    def test_logseq_connection_error(self):
        """Request: singine query logseq '[:find ?b]' --token tok (server down)
        Response: ok=false, result.error present.
        """
        from urllib.error import URLError

        def _fail(*a, **kw):
            raise URLError("connection refused")

        with patch("singine.query_dispatch.urlopen", side_effect=_fail):
            code, stdout, _ = _run("query", "logseq", "[:find ?b]", "--token", "tok")
        self.assertEqual(code, 1)
        p = _parse(stdout)
        self.assertFalse(p["ok"])
        self.assertIn("error", p["result"])


# ── xml ────────────────────────────────────────────────────────────────────────


class XmlQueryTest(unittest.TestCase):
    """singine query xml — XPath over local XML files.

    Request:  singine query xml <xpath> --path <file-or-dir> [--glob pattern]
    Response: JSON envelope, result.matches list of {file, tag, attrib, text},
              result.files_scanned int, result.match_count int.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.xml_dir = Path(self._tmp.name)
        # Write two XML files
        (self.xml_dir / "domain.xml").write_text(textwrap.dedent("""\
            <?xml version="1.0"?>
            <elia-electricity-data-platform>
              <domain id="electricity-balancing">
                <name>Electricity Balancing</name>
              </domain>
            </elia-electricity-data-platform>
        """))
        (self.xml_dir / "refdata.xml").write_text(textwrap.dedent("""\
            <?xml version="1.0"?>
            <reference-data>
              <domain id="grid-operations">
                <name>Grid Operations</name>
              </domain>
            </reference-data>
        """))

    def tearDown(self):
        self._tmp.cleanup()

    def test_xml_xpath_find_domains(self):
        """Request: singine query xml './/domain' --path <dir>
        Response: ok=true, backend=xml, result.match_count=2,
                  each match has {file, tag, attrib.id, text=None (children present)}.
        """
        code, stdout, _ = _run("query", "xml", ".//domain", "--path", str(self.xml_dir))
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "xml", ".//domain")
        self.assertTrue(p["ok"])
        self.assertEqual(p["result"]["match_count"], 2)
        self.assertEqual(p["result"]["files_scanned"], 2)
        tags = {m["tag"] for m in p["result"]["matches"]}
        self.assertEqual(tags, {"domain"})

    def test_xml_xpath_by_attribute(self):
        """Request: singine query xml './/*[@id]' --path <dir>
        Response: ok=true, all matched elements have an 'id' attribute.
        """
        code, stdout, _ = _run("query", "xml", ".//*[@id]", "--path", str(self.xml_dir))
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertTrue(p["ok"])
        for m in p["result"]["matches"]:
            self.assertIn("id", m["attrib"])

    def test_xml_single_file(self):
        """Request: singine query xml './/name' --path <single-file>
        Response: ok=true, result.files_scanned=1, result.match_count=1.
        """
        single = str(self.xml_dir / "domain.xml")
        code, stdout, _ = _run("query", "xml", ".//name", "--path", single)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertEqual(p["result"]["files_scanned"], 1)
        self.assertGreater(p["result"]["match_count"], 0)

    def test_xml_no_matches(self):
        """Request: singine query xml './/nonexistent' --path <dir>
        Response: ok=true, result.match_count=0 (no error for empty result).
        """
        code, stdout, _ = _run("query", "xml", ".//nonexistent", "--path", str(self.xml_dir))
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertTrue(p["ok"])
        self.assertEqual(p["result"]["match_count"], 0)


# ── sql ────────────────────────────────────────────────────────────────────────


class SqlQueryTest(unittest.TestCase):
    """singine query sql — raw SQL against SQLite.

    Request:  singine query sql <statement> --db <path>
    Response: JSON envelope, result.rows list of dicts, result.count int.
    """

    def setUp(self):
        import sqlite3

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE domain (id TEXT, name TEXT)")
        con.execute("INSERT INTO domain VALUES ('elba', 'Electricity Balancing')")
        con.execute("INSERT INTO domain VALUES ('grid', 'Grid Operations')")
        con.commit()
        con.close()

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def test_sql_select_all(self):
        """Request: singine query sql 'SELECT * FROM domain' --db <path>
        Response: ok=true, backend=sql, result.rows=[{id,name},...], result.count=2.
        """
        code, stdout, _ = _run("query", "sql", "SELECT * FROM domain", "--db", self.db)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "sql", "SELECT * FROM domain")
        self.assertTrue(p["ok"])
        self.assertEqual(p["result"]["count"], 2)
        names = {r["name"] for r in p["result"]["rows"]}
        self.assertIn("Electricity Balancing", names)

    def test_sql_where_clause(self):
        """Request: singine query sql 'SELECT id FROM domain WHERE id=\\'elba\\'' --db <path>
        Response: ok=true, result.count=1, result.rows[0].id='elba'.
        """
        stmt = "SELECT id FROM domain WHERE id='elba'"
        code, stdout, _ = _run("query", "sql", stmt, "--db", self.db)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertEqual(p["result"]["count"], 1)
        self.assertEqual(p["result"]["rows"][0]["id"], "elba")

    def test_sql_error_response(self):
        """Request: singine query sql 'SELECT * FROM nonexistent' --db <path>
        Response: ok=false, result.error contains sqlite error message.
        """
        code, stdout, _ = _run("query", "sql", "SELECT * FROM nonexistent", "--db", self.db)
        self.assertEqual(code, 1)
        p = _parse(stdout)
        self.assertFalse(p["ok"])
        self.assertIn("error", p["result"])


# ── sparql ─────────────────────────────────────────────────────────────────────


class SparqlQueryTest(unittest.TestCase):
    """singine query sparql — SPARQL over the bridge DB.

    Request:  singine query sparql <SELECT-statement> --db <path>
    Response: JSON envelope wrapping cortex_bridge.BridgeDB.sparql() result.
    """

    def test_sparql_query(self):
        """Request: singine query sparql 'SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5' --db /tmp/x.db
        Response: ok=true, backend=sparql, result contains bridge SPARQL response.
        """
        mock_result = {"results": {"bindings": [{"s": {"value": "iri-1"}}]}}
        mock_bridge = MagicMock()
        mock_bridge.sparql.return_value = mock_result

        sparql_q = "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5"
        with patch("singine.query_dispatch.cortex_bridge") as mock_mod:
            mock_mod.BridgeDB.return_value = mock_bridge
            code, stdout, _ = _run("query", "sparql", sparql_q, "--db", "/tmp/mock.db")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "sparql", sparql_q)
        self.assertTrue(p["ok"])
        self.assertIn("results", p["result"])

    def test_sparql_bridge_error(self):
        """Request: singine query sparql <query> (bridge raises exception)
        Response: ok=false, result.error present.
        """
        mock_bridge = MagicMock()
        mock_bridge.sparql.side_effect = RuntimeError("bridge not built")

        with patch("singine.query_dispatch.cortex_bridge") as mock_mod:
            mock_mod.BridgeDB.return_value = mock_bridge
            code, stdout, _ = _run(
                "query", "sparql",
                "SELECT ?s WHERE { ?s ?p ?o }",
                "--db", "/tmp/mock.db",
            )
        self.assertEqual(code, 1)
        p = _parse(stdout)
        self.assertFalse(p["ok"])
        self.assertIn("error", p["result"])


# ── graphql ────────────────────────────────────────────────────────────────────


class GraphqlQueryTest(unittest.TestCase):
    """singine query graphql — GraphQL over the bridge DB.

    Request:  singine query graphql <query-string> --db <path>
    Response: JSON envelope wrapping cortex_bridge.BridgeDB.graphql() result.
    """

    def test_graphql_entity_query(self):
        """Request: singine query graphql '{ entity(iri: "example") { iri } }' --db /tmp/x.db
        Response: ok=true, backend=graphql, result contains data key.
        """
        mock_result = {"data": {"entity": {"iri": "example"}}}
        mock_bridge = MagicMock()
        mock_bridge.graphql.return_value = mock_result

        gql = '{ entity(iri: "example") { iri } }'
        with patch("singine.query_dispatch.cortex_bridge") as mock_mod:
            mock_mod.BridgeDB.return_value = mock_bridge
            code, stdout, _ = _run("query", "graphql", gql, "--db", "/tmp/mock.db")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "graphql", gql)
        self.assertTrue(p["ok"])
        self.assertIn("data", p["result"])

    def test_graphql_search_query(self):
        """Request: singine query graphql '{ search(text: "electricity") { iri label } }' --db /tmp/x.db
        Response: ok=true, backend=graphql, result.data present.
        """
        mock_result = {"data": {"search": [{"iri": "elba", "label": "Electricity Balancing"}]}}
        mock_bridge = MagicMock()
        mock_bridge.graphql.return_value = mock_result

        gql = '{ search(text: "electricity") { iri label } }'
        with patch("singine.query_dispatch.cortex_bridge") as mock_mod:
            mock_mod.BridgeDB.return_value = mock_bridge
            code, stdout, _ = _run("query", "graphql", gql, "--db", "/tmp/mock.db")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertTrue(p["ok"])
        self.assertEqual(p["backend"], "graphql")


# ── docker ─────────────────────────────────────────────────────────────────────


class DockerQueryTest(unittest.TestCase):
    """singine query docker — docker ps/images/inspect/logs.

    Request:  singine query docker [<name>] --action ps|images|inspect|logs
    Response: JSON envelope, result.action echoed, result.rows or result.lines.
    """

    def _mock_ps(self, cmd, capture_output, text, timeout):
        proc = MagicMock()
        proc.stdout = (
            '{"ID":"abc","Names":"singine-cdn","Status":"Up 2 hours"}\n'
            '{"ID":"def","Names":"singine-edge","Status":"Up 1 hour"}\n'
        )
        proc.returncode = 0
        return proc

    def _mock_inspect(self, cmd, capture_output, text, timeout):
        proc = MagicMock()
        proc.stdout = json.dumps([{"Id": "abc", "Name": "/singine-cdn"}])
        proc.returncode = 0
        return proc

    def test_docker_ps(self):
        """Request: singine query docker --action ps
        Response: ok=true, backend=docker, result.action=ps, result.rows list.
        """
        with patch("singine.query_dispatch.subprocess.run", side_effect=self._mock_ps):
            code, stdout, _ = _run("query", "docker", "--action", "ps")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "docker", "")
        self.assertTrue(p["ok"])
        self.assertEqual(p["result"]["action"], "ps")
        self.assertIsInstance(p["result"]["rows"], list)
        self.assertEqual(p["result"]["count"], 2)

    def test_docker_inspect(self):
        """Request: singine query docker singine-cdn --action inspect
        Response: ok=true, backend=docker, result.items list with Id field.
        """
        with patch("singine.query_dispatch.subprocess.run", side_effect=self._mock_inspect):
            code, stdout, _ = _run("query", "docker", "singine-cdn", "--action", "inspect")
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertTrue(p["ok"])
        self.assertEqual(p["result"]["action"], "inspect")
        self.assertIsInstance(p["result"]["items"], list)
        self.assertEqual(p["result"]["items"][0]["Id"], "abc")

    def test_docker_not_found(self):
        """Request: singine query docker --action ps (docker absent)
        Response: ok=false, result.error contains 'not found'.
        """
        with patch("singine.query_dispatch.subprocess.run", side_effect=FileNotFoundError):
            code, stdout, _ = _run("query", "docker", "--action", "ps")
        self.assertEqual(code, 1)
        p = _parse(stdout)
        self.assertFalse(p["ok"])
        self.assertIn("not found", p["result"]["error"])


# ── sys ────────────────────────────────────────────────────────────────────────


class SysQueryTest(unittest.TestCase):
    """singine query sys — <sys-request>/<sys-response> XML envelope.

    The sys backend generates two XML files and returns their paths in the
    JSON envelope.  No external process is required.

    Request format:
        <sys-request id="<uuid>" api-version="1.0">
          <query>...</query>
        </sys-request>

    Response format:
        <sys-response id="<uuid>" request-ref="<req-id>" api-version="1.0">
          <query-echo>...</query-echo>
          <platform><system/><node/><machine/><release/></platform>
          <python><version/><executable/></python>
          <env><var name="..."/> ...</env>
          <ts/>
        </sys-response>
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out_dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_sys_query_envelope(self):
        """Request: singine query sys 'runtime context' --output-dir <dir>
        Response: ok=true, backend=sys, result.request_id and result.response_id
                  are UUIDs, result.facts.system is non-empty.
        """
        code, stdout, _ = _run("query", "sys", "runtime context", "--output-dir", self.out_dir)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        _assert_envelope(self, p, "sys", "runtime context")
        self.assertTrue(p["ok"])
        r = p["result"]
        self.assertIn("request_id", r)
        self.assertIn("response_id", r)
        self.assertNotEqual(r["request_id"], r["response_id"])
        self.assertEqual(r["facts"]["system"], platform.system())

    def test_sys_request_xml_written(self):
        """Request: singine query sys 'platform check' --output-dir <dir>
        Response: sys.request.xml file exists and has root tag <sys-request>
                  with api-version='1.0' attribute.
        """
        code, stdout, _ = _run("query", "sys", "platform check", "--output-dir", self.out_dir)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        req_path = Path(p["result"]["request_path"])
        self.assertTrue(req_path.exists(), "sys.request.xml must be written")
        from xml.etree import ElementTree as ET
        tree = ET.parse(str(req_path))
        root = tree.getroot()
        self.assertEqual(root.tag, "sys-request")
        self.assertEqual(root.attrib.get("api-version"), "1.0")
        self.assertEqual(root.find("query").text, "platform check")

    def test_sys_response_xml_written(self):
        """Request: singine query sys 'python version' --output-dir <dir>
        Response: sys.response.xml file exists, root tag <sys-response> with
                  request-ref matching request_id, <python><version/> non-empty.
        """
        code, stdout, _ = _run("query", "sys", "python version", "--output-dir", self.out_dir)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        resp_path = Path(p["result"]["response_path"])
        req_id = p["result"]["request_id"]
        self.assertTrue(resp_path.exists(), "sys.response.xml must be written")
        from xml.etree import ElementTree as ET
        tree = ET.parse(str(resp_path))
        root = tree.getroot()
        self.assertEqual(root.tag, "sys-response")
        self.assertEqual(root.attrib.get("request-ref"), req_id)
        version_text = root.find(".//python/version").text
        self.assertTrue(version_text, "python/version must be non-empty")
        self.assertEqual(version_text, platform.python_version())

    def test_sys_env_subset_in_response(self):
        """Request: singine query sys 'env probe' --output-dir <dir>
        Response: result.facts.env_subset contains HOME and SHELL keys (values
                  may be empty string if not set in the test environment).
        """
        code, stdout, _ = _run("query", "sys", "env probe", "--output-dir", self.out_dir)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        env = p["result"]["facts"]["env_subset"]
        self.assertIn("HOME", env)
        self.assertIn("SHELL", env)


# ── API version contract ────────────────────────────────────────────────────────


class ApiVersionContractTest(unittest.TestCase):
    """Verify that the QUERY_API_VERSION constant is '1.0' across all backends.

    This test is the pinned contract for singine query API 1.0.  Any bump to the
    constant must be accompanied by a changelog entry and a version gate in
    dependent consumers.
    """

    def test_api_version_constant(self):
        """QUERY_API_VERSION must equal '1.0' for singine 1.0 compatibility."""
        self.assertEqual(QUERY_API_VERSION, "1.0")

    def test_sys_envelope_carries_version(self):
        """The sys backend must embed api_version='1.0' in every envelope."""
        with tempfile.TemporaryDirectory() as tmp:
            code, stdout, _ = _run("query", "sys", "version probe", "--output-dir", tmp)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertEqual(p["api_version"], "1.0")

    def test_sql_envelope_carries_version(self):
        """The sql backend must embed api_version='1.0' in every envelope."""
        import sqlite3

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            con = sqlite3.connect(db_path)
            con.execute("CREATE TABLE t (x INTEGER)")
            con.execute("INSERT INTO t VALUES (42)")
            con.commit()
            con.close()
            code, stdout, _ = _run("query", "sql", "SELECT x FROM t", "--db", db_path)
        finally:
            Path(db_path).unlink(missing_ok=True)
        self.assertEqual(code, 0)
        p = _parse(stdout)
        self.assertEqual(p["api_version"], "1.0")


if __name__ == "__main__":
    unittest.main()
