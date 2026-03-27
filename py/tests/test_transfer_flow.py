"""Locked-down test cases for singine.transfer, executed in Flowable order.

Execution harness:  Flowable.home()
Top-level fixture:  executionObjectWithEventMappedToCollibraWf

Chain locked in order:
    Rest(
        test().genId().genCode().genId(),  # TC-F1 .. TC-F3
        genCode,                            # TC-F4
        return_,                            # TC-F5
        genCode().toIDXML(),               # TC-F6
        toXMLId(),                          # TC-F7
    )

Each step maps to one Collibra workflow event so the execution object
carries a full event trace alongside the transfer results.
"""

from __future__ import annotations

import json
import secrets
import unittest
import uuid
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Flowable harness
# ---------------------------------------------------------------------------

class FlowStep:
    """Fluent step builder — each method returns self so calls chain."""

    def __init__(self, flow: "Flowable") -> None:
        self._flow = flow
        self._ids: List[str] = []
        self._codes: List[str] = []

    # -- generators ----------------------------------------------------------

    def genId(self) -> "FlowStep":
        new_id = str(uuid.uuid4())
        self._ids.append(new_id)
        self._flow._state.setdefault("ids", []).append(new_id)
        return self

    def genCode(self) -> "FlowStep":
        code = secrets.token_hex(4).upper()
        self._codes.append(code)
        self._flow._state.setdefault("codes", []).append(code)
        return self

    # -- converters ----------------------------------------------------------

    def toIDXML(self) -> str:
        """Render the most recent (id, code) pair as an XML id element."""
        id_val = self._ids[-1] if self._ids else str(uuid.uuid4())
        code_val = self._codes[-1] if self._codes else secrets.token_hex(4).upper()
        tag = f'<id code="{code_val}">{id_val}</id>'
        self._flow._state["last_id_xml"] = tag
        return tag

    def toXMLId(self) -> str:
        """Flatten the last UUID into a legal XML NCName id attribute value."""
        id_val = self._ids[-1] if self._ids else str(uuid.uuid4())
        xml_id = "id-" + id_val.replace("-", "")
        self._flow._state["last_xml_id"] = xml_id
        return xml_id

    # -- accessors -----------------------------------------------------------

    @property
    def last_id(self) -> Optional[str]:
        return self._ids[-1] if self._ids else None

    @property
    def last_code(self) -> Optional[str]:
        return self._codes[-1] if self._codes else None


class Flowable:
    """Ordered execution harness.  Call home() to get a clean instance."""

    # Collibra workflow event sequence — locked
    _COLLIBRA_WF_EVENTS = [
        "DRAFT",
        "ID_GENERATED",
        "CODE_ASSIGNED",
        "ENRICHED",
        "CODE_CONFIRMED",
        "RETURNED",
        "XML_ID_MAPPED",
        "XML_ID_FINALISED",
        "APPROVED",
    ]

    def __init__(self) -> None:
        self._state: Dict[str, Any] = {}
        self._event_log: List[Dict[str, Any]] = []
        self._step_index = 0

    @classmethod
    def home(cls) -> "Flowable":
        instance = cls()
        instance._state["home"] = True
        instance._log_event("DRAFT", {"note": "flowable initialised at home"})
        return instance

    def test(self) -> "FlowStep":
        return FlowStep(self)

    def _log_event(self, event: str, payload: Dict[str, Any]) -> None:
        self._event_log.append({"event": event, "payload": payload})

    def advance(self, label: str, result: Any) -> None:
        idx = min(self._step_index, len(self._COLLIBRA_WF_EVENTS) - 1)
        event = self._COLLIBRA_WF_EVENTS[idx]
        self._log_event(event, {"step": label, "result": result})
        self._state[label] = result
        self._step_index += 1

    @property
    def event_log(self) -> List[Dict[str, Any]]:
        return list(self._event_log)

    @property
    def state(self) -> Dict[str, Any]:
        return dict(self._state)


# ---------------------------------------------------------------------------
# Rest execution container
# ---------------------------------------------------------------------------

class Rest:
    """REST execution container.

    Wraps a five-argument chain that mirrors the CLI:
        Rest(
            chain_step,      # FlowStep after .genId().genCode().genId()
            gencode_fn,      # callable() -> str  (a bare genCode invocation)
            return_fn,       # callable(value) -> value  (passthrough / return)
            id_xml_fn,       # callable() -> str  (genCode().toIDXML())
            xml_id_fn,       # callable() -> str  (toXMLId())
        )
    """

    def __init__(
        self,
        chain_step: FlowStep,
        gencode_fn: Any,
        return_fn: Any,
        id_xml_fn: Any,
        xml_id_fn: Any,
    ) -> None:
        self.chain_step = chain_step
        self._gencode_fn = gencode_fn
        self._return_fn = return_fn
        self._id_xml_fn = id_xml_fn
        self._xml_id_fn = xml_id_fn

    def execute(self) -> Dict[str, Any]:
        code = self._gencode_fn()
        returned = self._return_fn(code)
        id_xml = self._id_xml_fn()
        xml_id = self._xml_id_fn()
        return {
            "chain_last_id": self.chain_step.last_id,
            "chain_last_code": self.chain_step.last_code,
            "gencode": code,
            "returned": returned,
            "id_xml": id_xml,
            "xml_id": xml_id,
        }


# ---------------------------------------------------------------------------
# Transfer functions under test  (imported lazily to keep test isolation)
# ---------------------------------------------------------------------------

def _process_request(xml_source: str) -> Dict[str, Any]:
    from singine.transfer import process_request
    return process_request(xml_source)


def _generate_response_times(data: Any, times: int = 4) -> Dict[str, Any]:
    from singine.transfer import generate_response_times
    return generate_response_times(data, times=times)


def _project_fields(data: Any, fields: List[str]) -> Dict[str, Any]:
    from singine.transfer import project_fields
    return project_fields(data, fields)


def _analyze_result(data: Any) -> Dict[str, Any]:
    from singine.transfer import analyze_result
    return analyze_result(data)


def _queue_op(op: str, item: Optional[str], state: str) -> Dict[str, Any]:
    from singine.transfer import queue_op
    return queue_op(op, item, state)


def _stack_op(op: str, item: Optional[str], state: str) -> Dict[str, Any]:
    from singine.transfer import stack_op
    return stack_op(op, item, state)


# ---------------------------------------------------------------------------
# Collibra workflow execution object fixture
# ---------------------------------------------------------------------------

def _build_execution_object(flow: Flowable, rest_result: Dict[str, Any]) -> Dict[str, Any]:
    """Build executionObjectWithEventMappedToCollibraWf from flow state."""
    return {
        "flowable": {
            "home": flow.state.get("home"),
            "ids": flow.state.get("ids", []),
            "codes": flow.state.get("codes", []),
            "last_id_xml": flow.state.get("last_id_xml"),
            "last_xml_id": flow.state.get("last_xml_id"),
        },
        "rest": rest_result,
        "collibra_wf_events": flow.event_log,
    }


# ---------------------------------------------------------------------------
# Test suite — execution order is locked by method name prefix
# ---------------------------------------------------------------------------

class TransferFlowTest(unittest.TestCase):
    """Locked-down transfer flow tests.

    Execution order (enforced by unittest alphabetical sort on tc_ prefix):
      TC-F1  test chain — genId (first)
      TC-F2  test chain — genCode
      TC-F3  test chain — genId (second)
      TC-F4  Rest: bare genCode
      TC-F5  Rest: return passthrough
      TC-F6  Rest: genCode().toIDXML()
      TC-F7  Rest: toXMLId()
      TC-F8  full execution object with Collibra WF event mapping
      TC-F9  process-request round-trip (XML → envelope → id_xml)
      TC-F10 generate-response ×4 variants
      TC-F11 project fields from Rest result
      TC-F12 analyze result shape
      TC-F13 queue FIFO order preserved across transfer steps
      TC-F14 stack LIFO order preserved across transfer steps
    """

    flow: Flowable
    _chain: FlowStep
    executionObjectWithEventMappedToCollibraWf: Dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        cls.flow = Flowable.home()
        cls._chain = (
            cls.flow.test()
            .genId()       # TC-F1
            .genCode()     # TC-F2
            .genId()       # TC-F3
        )
        cls.flow.advance("chain_built", {
            "ids": list(cls.flow.state.get("ids", [])),
            "codes": list(cls.flow.state.get("codes", [])),
        })

        # Rest(...) — construct and execute the full chain container
        def _gencode() -> str:
            step = cls.flow.test().genCode()
            cls.flow.advance("rest_gencode", step.last_code)
            return step.last_code  # type: ignore[return-value]

        def _return(value: Any) -> Any:
            cls.flow.advance("rest_return", value)
            return value

        def _to_id_xml() -> str:
            step = cls.flow.test().genId().genCode()
            tag = step.toIDXML()
            cls.flow.advance("rest_id_xml", tag)
            return tag

        def _to_xml_id() -> str:
            step = cls.flow.test().genId()
            xml_id = step.toXMLId()
            cls.flow.advance("rest_xml_id", xml_id)
            return xml_id

        rest = Rest(cls._chain, _gencode, _return, _to_id_xml, _to_xml_id)
        cls._rest_result = rest.execute()

        cls.executionObjectWithEventMappedToCollibraWf = _build_execution_object(
            cls.flow, cls._rest_result
        )

    # ── TC-F1: chain — first genId ────────────────────────────────────────

    def test_tc_f01_chain_first_id_is_uuid(self) -> None:
        ids = self.flow.state.get("ids", [])
        self.assertGreaterEqual(len(ids), 1, "at least one ID must be generated")
        first_id = ids[0]
        parsed = uuid.UUID(first_id)
        self.assertEqual(str(parsed), first_id)

    # ── TC-F2: chain — genCode ────────────────────────────────────────────

    def test_tc_f02_chain_code_is_hex_string(self) -> None:
        codes = self.flow.state.get("codes", [])
        self.assertGreaterEqual(len(codes), 1)
        first_code = codes[0]
        self.assertRegex(first_code, r"^[0-9A-F]{8}$",
                         "code must be 8 hex chars (upper)")

    # ── TC-F3: chain — second genId ───────────────────────────────────────

    def test_tc_f03_chain_second_id_is_distinct_uuid(self) -> None:
        ids = self.flow.state.get("ids", [])
        self.assertGreaterEqual(len(ids), 2, "chain must have produced two IDs")
        self.assertNotEqual(ids[0], ids[1], "IDs must be distinct")
        uuid.UUID(ids[1])  # must be valid UUID

    # ── TC-F4: Rest — bare genCode ────────────────────────────────────────

    def test_tc_f04_rest_gencode_present(self) -> None:
        code = self._rest_result["gencode"]
        self.assertIsNotNone(code)
        self.assertRegex(code, r"^[0-9A-F]{8}$")

    # ── TC-F5: Rest — return passthrough ──────────────────────────────────

    def test_tc_f05_rest_return_equals_gencode(self) -> None:
        self.assertEqual(
            self._rest_result["returned"],
            self._rest_result["gencode"],
            "return_ must pass the value through unchanged",
        )

    # ── TC-F6: Rest — genCode().toIDXML() ────────────────────────────────

    def test_tc_f06_rest_id_xml_is_well_formed(self) -> None:
        import xml.etree.ElementTree as ET
        tag = self._rest_result["id_xml"]
        self.assertIsNotNone(tag)
        root = ET.fromstring(tag)
        self.assertEqual(root.tag, "id")
        self.assertIn("code", root.attrib)
        self.assertRegex(root.attrib["code"], r"^[0-9A-F]{8}$")
        uuid.UUID(root.text)  # content must be a valid UUID

    # ── TC-F7: Rest — toXMLId() ───────────────────────────────────────────

    def test_tc_f07_rest_xml_id_is_ncname(self) -> None:
        xml_id = self._rest_result["xml_id"]
        self.assertIsNotNone(xml_id)
        self.assertTrue(xml_id.startswith("id-"),
                        f"xml_id must start with 'id-', got {xml_id!r}")
        # NCName: no hyphens after the prefix, just hex
        hex_part = xml_id[3:]
        self.assertRegex(hex_part, r"^[0-9a-f]{32}$",
                         "hex part must be 32 lowercase hex chars (UUID without hyphens)")

    # ── TC-F8: execution object — Collibra WF event trace ─────────────────

    def test_tc_f08_execution_object_has_wf_events(self) -> None:
        obj = self.executionObjectWithEventMappedToCollibraWf
        events = obj["collibra_wf_events"]
        event_names = [e["event"] for e in events]

        self.assertIn("DRAFT", event_names)
        self.assertIn("ID_GENERATED", event_names)
        self.assertIn("CODE_ASSIGNED", event_names)
        # DRAFT must be first
        self.assertEqual(event_names[0], "DRAFT")

    def test_tc_f08b_execution_object_rest_fields_present(self) -> None:
        obj = self.executionObjectWithEventMappedToCollibraWf
        for key in ("chain_last_id", "chain_last_code", "gencode",
                    "returned", "id_xml", "xml_id"):
            self.assertIn(key, obj["rest"])

    # ── TC-F9: process-request XML → envelope ────────────────────────────

    def test_tc_f09_process_request_round_trip(self) -> None:
        xml_id = self._rest_result["xml_id"]
        code = self._rest_result["gencode"]
        xml_source = (
            f'<singine-request id="{xml_id}" code="{code}">'
            f'<operation>transfer</operation>'
            f'<payload>test</payload>'
            f'</singine-request>'
        )
        result = _process_request(xml_source)
        self.assertTrue(result["ok"])
        self.assertTrue(result["well_formed"])
        self.assertEqual(result["root_tag"], "singine-request")
        self.assertEqual(result["attributes"]["id"], xml_id)
        self.assertEqual(result["attributes"]["code"], code)
        self.assertGreater(result["element_count"], 1)
        self.flow.advance("process_request_ok", result["root_tag"])

    # ── TC-F10: generate-response ×4 variants ────────────────────────────

    def test_tc_f10_generate_response_times_four(self) -> None:
        data = {
            "id": self._rest_result["chain_last_id"],
            "code": self._rest_result["gencode"],
            "xml_id": self._rest_result["xml_id"],
        }
        result = _generate_response_times(data, times=4)
        self.assertTrue(result["ok"])
        self.assertEqual(result["times"], 4)
        self.assertEqual(len(result["variants"]), 4)
        formats = [v["format"] for v in result["variants"]]
        self.assertEqual(formats, ["json", "xml", "summary", "table"])
        # json variant must carry the id
        json_variant = result["variants"][0]["content"]
        self.assertIn("id", json_variant)
        # xml variant must be parseable
        import xml.etree.ElementTree as ET
        ET.fromstring(result["variants"][1]["content"])
        self.flow.advance("generate_response_ok", formats)

    # ── TC-F11: project fields from Rest result ───────────────────────────

    def test_tc_f11_project_fields_from_rest_result(self) -> None:
        data = {
            "chain_last_id": self._rest_result["chain_last_id"],
            "chain_last_code": self._rest_result["chain_last_code"],
            "gencode": self._rest_result["gencode"],
            "returned": self._rest_result["returned"],
            "id_xml": self._rest_result["id_xml"],
            "xml_id": self._rest_result["xml_id"],
        }
        result = _project_fields(data, ["chain_last_id", "xml_id"])
        self.assertTrue(result["ok"])
        self.assertEqual(set(result["result"].keys()), {"chain_last_id", "xml_id"})
        self.assertEqual(result["result"]["xml_id"], self._rest_result["xml_id"])
        self.flow.advance("project_ok", list(result["result"].keys()))

    # ── TC-F12: analyze result shape ──────────────────────────────────────

    def test_tc_f12_analyze_result_shape(self) -> None:
        result = _analyze_result(self._rest_result)
        self.assertTrue(result["ok"])
        self.assertEqual(result["type"], "dict")
        self.assertGreater(result["depth"], 0)
        self.assertGreater(result["leaf_count"], 0)
        self.assertIsNotNone(result["keys"])
        self.assertIn("xml_id", result["keys"])
        self.flow.advance("analyze_ok", result["type"])

    # ── TC-F13: queue FIFO order across transfer steps ────────────────────

    def test_tc_f13_queue_fifo_order(self) -> None:
        import tempfile, os
        state = os.path.join(tempfile.gettempdir(), "singine-flow-test-queue.json")
        ids = self.flow.state.get("ids", [])
        for item in ids:
            r = _queue_op("push", item, state)
            self.assertTrue(r["ok"])
        first_pop = _queue_op("pop", None, state)
        self.assertTrue(first_pop["ok"])
        self.assertEqual(first_pop["item"], ids[0],
                         "FIFO: first pushed item must be first popped")
        # drain
        _queue_op("clear", None, state)
        self.flow.advance("queue_fifo_ok", ids[0])

    # ── TC-F14: stack LIFO order across transfer steps ────────────────────

    def test_tc_f14_stack_lifo_order(self) -> None:
        import tempfile, os
        state = os.path.join(tempfile.gettempdir(), "singine-flow-test-stack.json")
        ids = self.flow.state.get("ids", [])
        for item in ids:
            r = _stack_op("push", item, state)
            self.assertTrue(r["ok"])
        first_pop = _stack_op("pop", None, state)
        self.assertTrue(first_pop["ok"])
        self.assertEqual(first_pop["item"], ids[-1],
                         "LIFO: last pushed item must be first popped")
        # drain
        _stack_op("clear", None, state)
        self.flow.advance("stack_lifo_ok", ids[-1])


if __name__ == "__main__":
    unittest.main()
