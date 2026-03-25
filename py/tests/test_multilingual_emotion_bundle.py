import json
import tempfile
import unittest
from pathlib import Path

from singine.multilingual_emotion import (
    BASE_MESSAGE_LATIN,
    bundle,
    message_graph,
    scenario_fixture,
    training_examples,
)


class MultilingualEmotionBundleTest(unittest.TestCase):
    def test_graph_preserves_multilingual_and_causality_dimensions(self):
        graph = message_graph()

        self.assertEqual(graph["textFaLatn"], BASE_MESSAGE_LATIN)
        self.assertEqual(graph["geometry"]["cycleSpace"], "S1")
        self.assertIn("Docker", graph["edgeRuntime"]["containerization"])
        self.assertTrue(graph["causalityGuard"]["preserve_event_order"])
        self.assertIn("urn:singine:emotion:care", graph["emotion"])

    def test_bundle_contains_farsi_english_french_examples(self):
        payload = bundle()

        self.assertEqual(payload["dataset"]["languages"], ["fa-Latn", "fa", "en", "fr"])
        self.assertGreaterEqual(len(payload["dataset"]["examples"]), 6)

        first = payload["dataset"]["examples"][0]
        self.assertIn("Bonjour", first["french_translation"])
        self.assertIn("Hello", first["english_translation"])
        self.assertIn("سلام", first["source_text_persian"])
        self.assertTrue(first["causality_guard"]["do_not_infer_harm_from_checking"])

    def test_scenario_fixture_is_json_serializable_for_singine_assets(self):
        fixture = scenario_fixture()

        self.assertEqual(fixture["scenario"]["id"], "TC-ME-001")
        self.assertIn("Hive", fixture["scenario"]["systems"])

        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "fixture.json"
            out_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2), encoding="utf-8")
            reloaded = json.loads(out_path.read_text(encoding="utf-8"))

        self.assertEqual(reloaded["graph"]["textFr"], fixture["graph"]["textFr"])

    def test_training_examples_keep_parallel_language_path(self):
        examples = training_examples()

        self.assertTrue(all(example.language_path == ["fa-Latn", "fa", "en", "fr"] for example in examples))
        self.assertTrue(any("regret_light" in example.emotions for example in examples))


if __name__ == "__main__":
    unittest.main()
