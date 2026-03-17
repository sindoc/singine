"""Tests for singine domain command family.

Tests cover schema bootstrap, master data CRUD, event log, governed
transactions, and reference data — all over an in-memory SQLite database.
"""
import json
import sqlite3
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from singine.command import main


class DomainCommandsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db = self._tmp.name

    def tearDown(self):
        Path(self.db).unlink(missing_ok=True)

    def _run(self, *args):
        stdout = StringIO()
        stderr = StringIO()
        with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    # ── schema ───────────────────────────────────────────────────────────────

    def test_schema_init_and_tables(self):
        code, out, _ = self._run("domain", "schema", "init", "--db", self.db)
        self.assertEqual(0, code)
        code, out, _ = self._run("domain", "schema", "tables", "--db", self.db)
        self.assertEqual(0, code)
        for table in ("business_term", "business_capability", "domain_event",
                      "governed_transaction", "reference_data_entry"):
            self.assertIn(table, out)

    def test_schema_init_is_idempotent(self):
        code1, _, _ = self._run("domain", "schema", "init", "--db", self.db)
        code2, _, _ = self._run("domain", "schema", "init", "--db", self.db)
        self.assertEqual(0, code1)
        self.assertEqual(0, code2)

    # ── master data ──────────────────────────────────────────────────────────

    def _init_and_add(self, record_type, name, extra_args=None):
        self._run("domain", "schema", "init", "--db", self.db)
        args = ["domain", "master", "add",
                "--type", record_type,
                "--name", name,
                "--db", self.db]
        if extra_args:
            args.extend(extra_args)
        return self._run(*args)

    def test_master_add_business_term(self):
        code, out, _ = self._init_and_add("BusinessTerm", "Electricity Balancing")
        self.assertEqual(0, code)

    def test_master_add_business_capability(self):
        code, out, _ = self._init_and_add("BusinessCapability", "Grid Operations")
        self.assertEqual(0, code)

    def test_master_add_business_process(self):
        code, out, _ = self._init_and_add("BusinessProcess", "Balancing Process")
        self.assertEqual(0, code)

    def test_master_add_data_category(self):
        code, out, _ = self._init_and_add("DataCategory", "Energy Data")
        self.assertEqual(0, code)

    def test_master_list(self):
        self._run("domain", "schema", "init", "--db", self.db)
        self._run("domain", "master", "add", "--type", "BusinessTerm",
                  "--name", "Electricity Balancing", "--db", self.db)
        self._run("domain", "master", "add", "--type", "BusinessCapability",
                  "--name", "Grid Operations", "--db", self.db)
        code1, out1, _ = self._run("domain", "master", "list",
                                    "--type", "BusinessTerm", "--db", self.db)
        code2, out2, _ = self._run("domain", "master", "list",
                                    "--type", "BusinessCapability", "--db", self.db)
        self.assertEqual(0, code1)
        self.assertEqual(0, code2)
        self.assertIn("Electricity Balancing", out1)
        self.assertIn("Grid Operations", out2)

    def test_master_list_json(self):
        self._run("domain", "schema", "init", "--db", self.db)
        self._run("domain", "master", "add", "--type", "BusinessTerm",
                  "--name", "ELBA Term", "--db", self.db)
        code, out, _ = self._run("domain", "master", "list",
                                  "--type", "BusinessTerm", "--json", "--db", self.db)
        self.assertEqual(0, code)
        data = json.loads(out)
        self.assertIsInstance(data, list)
        names = [r["name"] for r in data]
        self.assertIn("ELBA Term", names)

    def test_master_find(self):
        self._run("domain", "schema", "init", "--db", self.db)
        self._run("domain", "master", "add", "--type", "BusinessTerm",
                  "--name", "Balancing Term", "--db", self.db)
        code, out, _ = self._run("domain", "master", "find",
                                  "--type", "BusinessTerm",
                                  "--name", "Balancing Term", "--db", self.db)
        self.assertEqual(0, code)
        self.assertIn("Balancing Term", out)

    # ── events ───────────────────────────────────────────────────────────────

    def test_event_append_and_log(self):
        self._run("domain", "schema", "init", "--db", self.db)
        code, out, _ = self._run(
            "domain", "event", "append",
            "--event-type", "AI_SESSION_STARTED",
            "--subject-id", "subject-001",
            "--db", self.db,
        )
        self.assertEqual(0, code)
        code, out, _ = self._run("domain", "event", "log", "--db", self.db)
        self.assertEqual(0, code)
        self.assertIn("AI_SESSION_STARTED", out)

    def test_event_log_json(self):
        self._run("domain", "schema", "init", "--db", self.db)
        self._run("domain", "event", "append",
                  "--event-type", "IDENTITY_LOGIN",
                  "--subject-id", "user-1",
                  "--db", self.db)
        code, out, _ = self._run("domain", "event", "log", "--json", "--db", self.db)
        self.assertEqual(0, code)
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertTrue(any(e["event_type"] == "IDENTITY_LOGIN" for e in data))

    def test_event_log_limit(self):
        self._run("domain", "schema", "init", "--db", self.db)
        for i in range(5):
            self._run("domain", "event", "append",
                      "--event-type", "IDENTITY_LOGIN",
                      "--subject-id", f"user-{i}",
                      "--db", self.db)
        code, out, _ = self._run("domain", "event", "log",
                                  "--limit", "2", "--json", "--db", self.db)
        self.assertEqual(0, code)
        data = json.loads(out)
        self.assertLessEqual(len(data), 2)

    # ── transactions ─────────────────────────────────────────────────────────

    def test_tx_create_and_list(self):
        self._run("domain", "schema", "init", "--db", self.db)
        code, out, _ = self._run(
            "domain", "tx", "create",
            "--type", "GOVERNANCE_DECISION",
            "--initiator-id", "operator-1",
            "--subject-id", "asset-elba",
            "--db", self.db,
        )
        self.assertEqual(0, code)
        code, out, _ = self._run("domain", "tx", "list", "--db", self.db)
        self.assertEqual(0, code)
        self.assertIn("GOVERNANCE_DECISION", out)

    def test_tx_create_json(self):
        self._run("domain", "schema", "init", "--db", self.db)
        code, out, _ = self._run(
            "domain", "tx", "create",
            "--type", "POLICY_EVALUATION",
            "--initiator-id", "claude",
            "--subject-id", "policy-001",
            "--json",
            "--db", self.db,
        )
        self.assertEqual(0, code)
        data = json.loads(out)
        self.assertEqual("POLICY_EVALUATION", data["type"])
        self.assertEqual("PENDING", data["status"])

    def test_tx_update_status(self):
        self._run("domain", "schema", "init", "--db", self.db)
        _, create_out, _ = self._run(
            "domain", "tx", "create",
            "--type", "MANDATE_GRANT",
            "--initiator-id", "admin",
            "--subject-id", "session-x",
            "--json",
            "--db", self.db,
        )
        tx_id = json.loads(create_out)["transaction_id"]
        code, out, _ = self._run(
            "domain", "tx", "update",
            "--tx-id", tx_id,
            "--status", "APPROVED",
            "--db", self.db,
        )
        self.assertEqual(0, code)
        code, out, _ = self._run("domain", "tx", "list", "--json", "--db", self.db)
        self.assertEqual(0, code)
        txs = json.loads(out)
        match = next((t for t in txs if t["transaction_id"] == tx_id), None)
        self.assertIsNotNone(match)
        self.assertEqual("APPROVED", match["status"])

    # ── reference data ───────────────────────────────────────────────────────

    def test_refdata_add_and_list(self):
        self._run("domain", "schema", "init", "--db", self.db)
        code, out, _ = self._run(
            "domain", "refdata", "add",
            "--code-set", "scenario-codes",
            "--code", "ELBA",
            "--label", "Electricity Balancing",
            "--db", self.db,
        )
        self.assertEqual(0, code)
        code, out, _ = self._run("domain", "refdata", "list", "--db", self.db)
        self.assertEqual(0, code)
        self.assertIn("scenario-codes", out)

    def test_refdata_list_by_code_set(self):
        self._run("domain", "schema", "init", "--db", self.db)
        self._run("domain", "refdata", "add",
                  "--code-set", "scenario-codes",
                  "--code", "ELBA",
                  "--label", "Electricity Balancing",
                  "--db", self.db)
        self._run("domain", "refdata", "add",
                  "--code-set", "iata-codes",
                  "--code", "BRU",
                  "--label", "Brussels Airport",
                  "--db", self.db)
        code, out, _ = self._run(
            "domain", "refdata", "list",
            "--code-set", "iata-codes",
            "--json",
            "--db", self.db,
        )
        self.assertEqual(0, code)
        data = json.loads(out)
        self.assertTrue(all(e["code_set"] == "iata-codes" for e in data))
        codes = [e["code"] for e in data]
        self.assertIn("BRU", codes)

    def test_refdata_add_is_upsert(self):
        self._run("domain", "schema", "init", "--db", self.db)
        self._run("domain", "refdata", "add",
                  "--code-set", "scenario-codes",
                  "--code", "GRID",
                  "--label", "Grid v1",
                  "--db", self.db)
        code, out, _ = self._run("domain", "refdata", "add",
                                  "--code-set", "scenario-codes",
                                  "--code", "GRID",
                                  "--label", "Grid v2",
                                  "--db", self.db)
        self.assertEqual(0, code)
        code, out, _ = self._run(
            "domain", "refdata", "list",
            "--code-set", "scenario-codes",
            "--json",
            "--db", self.db,
        )
        data = json.loads(out)
        grid = next(e for e in data if e["code"] == "GRID")
        self.assertEqual("Grid v2", grid["label"])


if __name__ == "__main__":
    unittest.main()
