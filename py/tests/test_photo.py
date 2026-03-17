import types
import tempfile
import unittest
from pathlib import Path

from singine.photo import (
    build_asset_query,
    build_count_query,
    create_photo_test_case,
    export_city_review,
    resolve_source,
    sanitize_filename,
)


class PhotoTest(unittest.TestCase):
    def test_sanitize_filename_normalizes_to_safe_asciiish_token(self):
        self.assertEqual(sanitize_filename("IMG 1234.HEIC"), "img_1234")
        self.assertEqual(sanitize_filename("   ???.jpg"), "photo")

    def test_queries_include_requested_city_fragments(self):
        asset_query = build_asset_query(["beirut", "shiraz"])
        count_query = build_count_query(["beirut", "shiraz"])

        self.assertIn("%beirut%", asset_query)
        self.assertIn("%shiraz%", asset_query)
        self.assertIn("COUNT(*) AS photo_count", count_query)

    def test_resolve_source_prefers_original_then_derivative(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            original = root / "originals" / "A" / "IMG.heic"
            derivative = root / "resources" / "derivatives" / "A" / "UUID_1_102_o.jpeg"
            derivative.parent.mkdir(parents=True)
            original.parent.mkdir(parents=True)

            derivative.write_text("preview", encoding="utf-8")
            self.assertEqual(resolve_source(root, "UUID", "A", "IMG.heic"), derivative)

            original.write_text("original", encoding="utf-8")
            self.assertEqual(resolve_source(root, "UUID", "A", "IMG.heic"), original)

    def test_create_test_case_builds_fixture_with_activity_metadata(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = create_photo_test_case(Path(tmpdir) / "case")

            self.assertTrue((Path(payload["library_root"]) / "database" / "Photos.sqlite").exists())
            self.assertTrue(Path(payload["activity_path"]).exists())
            self.assertIn("activity-photo-export-review-01", Path(payload["activity_path"]).read_text(encoding="utf-8"))

    def test_export_city_review_uses_fixture_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            case = create_photo_test_case(Path(tmpdir) / "case")
            out_root = Path(case["output_root"])

            import singine.photo as photo_module

            original_run = photo_module.subprocess.run

            def fake_run(cmd, capture_output, text, check):  # noqa: ANN001
                destination = Path(cmd[-1])
                source = Path(cmd[1])
                destination.write_bytes(source.read_bytes())
                return types.SimpleNamespace(returncode=0, stdout="", stderr="")

            photo_module.subprocess.run = fake_run
            try:
                payload = export_city_review(
                    library_root=Path(case["library_root"]),
                    db_path=Path(case["db_path"]),
                    out_root=out_root,
                    cities=["beirut", "shiraz"],
                    max_kb=500,
                    max_dim=2560,
                    limit=0,
                )
            finally:
                photo_module.subprocess.run = original_run

            manifest = Path(payload["manifest"])
            self.assertEqual(payload["exported"], 2)
            self.assertTrue(manifest.exists())
            self.assertIn("beirut", manifest.read_text(encoding="utf-8"))
            self.assertIn("shiraz", manifest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
