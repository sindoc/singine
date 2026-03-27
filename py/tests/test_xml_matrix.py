import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from singine.cortex_bridge import BridgeDB
from singine.xml_matrix import execute_matrix


class XmlMatrixTest(unittest.TestCase):
    def test_execute_matrix_generates_request_response_and_heatmap(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "matrix.sqlite.db"
            out_dir = Path(tmpdir) / "xml"

            db = BridgeDB(db_path)
            try:
                db.setup()
                source_id = db.upsert_source(type("SourceSpecLike", (), {
                    "name": "claude",
                    "kind": "agent-home",
                    "root_path": Path(tmpdir),
                    "metadata": {"family": "claude"},
                })())
                entity_id = db.ensure_entity(
                    source_id=source_id,
                    entity_type="markdown",
                    iri="urn:test:markdown:1",
                    label="kernel session TODO",
                    metadata={},
                )
                db.add_statement(source_id=source_id, subject_id=entity_id, predicate="http://www.w3.org/1999/02/22-rdf-syntax-ns#type", object_value="markdown")
                db.add_statement(source_id=source_id, subject_id=entity_id, predicate="http://www.w3.org/2000/01/rdf-schema#label", object_value="kernel session TODO")
                db.add_fragment(source_id=source_id, entity_id=entity_id, seq=1, text="kernel session TODO")
                db.commit()
            finally:
                db.close()

            result = execute_matrix(db_path, Path.cwd(), out_dir)
            self.assertIsInstance(result["failures"], int)
            self.assertTrue((out_dir / "request.xml").exists())
            self.assertTrue((out_dir / "response.xml").exists())
            self.assertTrue((out_dir / "heatmap.xml").exists())

            request_root = ET.parse(out_dir / "request.xml").getroot()
            response_root = ET.parse(out_dir / "response.xml").getroot()
            heatmap_root = ET.parse(out_dir / "heatmap.xml").getroot()

            self.assertEqual(request_root.tag, "singine-request")
            self.assertEqual(response_root.tag, "singine-response")
            self.assertEqual(heatmap_root.tag, "heatmap")
            self.assertTrue(request_root.findall(".//lambda"))
            self.assertTrue(request_root.findall(".//cyclic-periods/period"))
            self.assertTrue(response_root.findall(".//result"))
            self.assertTrue(heatmap_root.findall(".//cell"))
            self.assertTrue(request_root.findall(".//scenario[@id='TC003']"))
            self.assertTrue(response_root.findall(".//result[@scenario-id='TC003']"))
            self.assertTrue(response_root.findall(".//result[@causality='preserved']"))


if __name__ == "__main__":
    unittest.main()
