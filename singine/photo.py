"""singine.photo - Apple Photos exports for lightweight review workflows."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


APPLE_EPOCH_OFFSET = 978307200
DEFAULT_PHOTOS_LIBRARY_ROOT = Path.home() / "Pictures" / "Photos Library.photoslibrary"
DEFAULT_DB_PATH = DEFAULT_PHOTOS_LIBRARY_ROOT / "database" / "Photos.sqlite"
DEFAULT_REVIEW_CITIES = ("beirut", "shiraz")
PHOTO_REVIEW_ACTIVITY = {
    "activity_id": "activity-photo-export-review-01",
    "activity_name": "Export City Review JPEGs from Apple Photos",
    "activity_interface": "singine photo export-review",
    "taxonomy_id": "taxonomy-singine-photo-review-export",
    "taxonomy_domain": "media-review",
    "taxonomy_category": "photo-review",
    "taxonomy_subcategory": "review-export",
    "policy_id": "policy-singine-photo-local-review-01",
    "policy_decision": "approved",
    "outcome_type": "SUCCESS",
    "artifact_types": ["jpeg", "manifest.tsv", "paths"],
}
DEMO_JPEG_BASE64 = (
    "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgICAgMCAgIDAwMDBAYEBAQEBAgGBgUGCQgKCgkICQkK"
    "DA8MCgsOCwkJDRENDg8QEBEQCgwSExIQEw8QEBD/2wBDAQMDAwQDBAgEBAgQCwkLEBAQEBAQEBAQEBAQ"
    "EBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBD/wAARCAACAAIDAREAAhEBAxEB/"
    "8QAFAABAAAAAAAAAAAAAAAAAAAABP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/xAAVAQEBAAAAAAAAAAAA"
    "AAAAAAAHCP/EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAMAwEAAhEDEQA/AEARQr//2Q=="
)


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2))


def _demo_jpeg_bytes() -> bytes:
    return base64.b64decode(DEMO_JPEG_BASE64)


def sanitize_filename(name: str) -> str:
    stem = Path(name).stem.lower()
    cleaned = [
        ch if ch.isalnum() else "_"
        for ch in stem
    ]
    value = "".join(cleaned).strip("_")
    while "__" in value:
        value = value.replace("__", "_")
    return value or "photo"


def resolve_source(library_root: Path, uuid: str, zdirectory: str, original_filename: str) -> Path | None:
    candidates = [
        library_root / "originals" / zdirectory / original_filename,
        library_root / "resources" / "derivatives" / zdirectory / f"{uuid}_1_102_o.jpeg",
        library_root / "resources" / "derivatives" / zdirectory / f"{uuid}_1_105_c.jpeg",
        library_root / "resources" / "derivatives" / zdirectory / f"{uuid}_1_101_o.jpeg",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _city_conditions(cities: Sequence[str]) -> str:
    clauses: List[str] = []
    for city in cities:
        token = city.lower().replace("'", "''")
        clauses.append(
            "("
            f"lower(ifnull(m.ZTITLE, '')) LIKE '%{token}%' OR "
            f"lower(ifnull(m.ZSUBTITLE, '')) LIKE '%{token}%'"
            ")"
        )
    return " OR ".join(clauses)


def _city_case(cities: Sequence[str]) -> str:
    branches = []
    for city in cities:
        token = city.lower().replace("'", "''")
        branches.append(
            "WHEN "
            f"lower(ifnull(m.ZTITLE, '')) LIKE '%{token}%' OR "
            f"lower(ifnull(m.ZSUBTITLE, '')) LIKE '%{token}%' "
            f"THEN '{city.lower()}'"
        )
    return "CASE " + " ".join(branches) + " END"


def build_asset_query(cities: Sequence[str]) -> str:
    city_case = _city_case(cities)
    city_conditions = _city_conditions(cities)
    return f"""
SELECT
  {city_case} AS city,
  strftime('%Y%m%d_%H%M%S', datetime(a.ZDATECREATED + {APPLE_EPOCH_OFFSET}, 'unixepoch')) AS capture_stamp,
  a.ZUUID,
  a.ZFILENAME,
  a.ZDIRECTORY
FROM ZASSET a
JOIN ZMOMENT m ON a.ZMOMENT = m.Z_PK
WHERE a.ZKIND = 0
  AND ifnull(a.ZTRASHEDSTATE, 0) = 0
  AND ({city_conditions})
ORDER BY city, a.ZDATECREATED, a.ZUUID
""".strip()


def build_count_query(cities: Sequence[str]) -> str:
    city_case = _city_case(cities)
    city_conditions = _city_conditions(cities)
    return f"""
SELECT {city_case} AS city, COUNT(*) AS photo_count
FROM ZASSET a
JOIN ZMOMENT m ON a.ZMOMENT = m.Z_PK
WHERE a.ZKIND = 0
  AND ifnull(a.ZTRASHEDSTATE, 0) = 0
  AND ({city_conditions})
GROUP BY city
ORDER BY city
""".strip()


def _require_tools() -> None:
    if shutil.which("magick") is None:
        raise RuntimeError("ImageMagick 'magick' is required on PATH.")


def _require_db(db_path: Path) -> None:
    if not db_path.exists():
        raise RuntimeError(f"Photos database not found at {db_path}")


def _write_demo_jpeg(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_demo_jpeg_bytes())


def create_photo_test_case(case_root: Path) -> Dict[str, object]:
    library_root = case_root / "fixture-library.photoslibrary"
    db_path = library_root / "database" / "Photos.sqlite"
    output_root = case_root / "review-output"
    readme_path = case_root / "README.txt"
    activity_path = case_root / "activity.json"

    if case_root.exists():
        shutil.rmtree(case_root)
    (library_root / "database").mkdir(parents=True, exist_ok=True)
    (library_root / "originals" / "B").mkdir(parents=True, exist_ok=True)
    (library_root / "resources" / "derivatives" / "S").mkdir(parents=True, exist_ok=True)

    beirut_original = library_root / "originals" / "B" / "beirut-demo-1.jpeg"
    shiraz_derivative = library_root / "resources" / "derivatives" / "S" / "SHIRAZ-DEMO-1_1_102_o.jpeg"
    _write_demo_jpeg(beirut_original)
    _write_demo_jpeg(shiraz_derivative)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE ZMOMENT (Z_PK INTEGER PRIMARY KEY, ZTITLE TEXT, ZSUBTITLE TEXT)")
        conn.execute(
            """
            CREATE TABLE ZASSET (
              ZUUID TEXT,
              ZDATECREATED REAL,
              ZFILENAME TEXT,
              ZDIRECTORY TEXT,
              ZKIND INTEGER,
              ZTRASHEDSTATE INTEGER,
              ZMOMENT INTEGER
            )
            """
        )
        conn.execute("INSERT INTO ZMOMENT (Z_PK, ZTITLE, ZSUBTITLE) VALUES (1, 'Beirut', '')")
        conn.execute("INSERT INTO ZMOMENT (Z_PK, ZTITLE, ZSUBTITLE) VALUES (2, 'Shiraz', '')")
        conn.execute(
            "INSERT INTO ZASSET (ZUUID, ZDATECREATED, ZFILENAME, ZDIRECTORY, ZKIND, ZTRASHEDSTATE, ZMOMENT) "
            "VALUES (?, ?, ?, ?, 0, 0, 1)",
            ("BEIRUT-DEMO-1", 700000000, "beirut-demo-1.jpeg", "B"),
        )
        conn.execute(
            "INSERT INTO ZASSET (ZUUID, ZDATECREATED, ZFILENAME, ZDIRECTORY, ZKIND, ZTRASHEDSTATE, ZMOMENT) "
            "VALUES (?, ?, ?, ?, 0, 0, 2)",
            ("SHIRAZ-DEMO-1", 700000100, "shiraz-demo-1.jpeg", "S"),
        )
        conn.commit()
    finally:
        conn.close()

    activity_payload = {
        "activity": PHOTO_REVIEW_ACTIVITY,
        "fixture": {
            "library_root": str(library_root),
            "db_path": str(db_path),
            "output_root": str(output_root),
            "cities": list(DEFAULT_REVIEW_CITIES),
        },
    }
    activity_path.write_text(json.dumps(activity_payload, indent=2) + "\n", encoding="utf-8")

    readme_path.write_text(
        "\n".join(
            [
                "Singine photo test case",
                "",
                "Commands:",
                f"  singine photo export-review {output_root} --library-root {library_root} --db {db_path} --max-kb 500 --max-dim 2560 --json",
                f"  column -t -s $'\\t' {output_root / 'manifest.tsv'}",
                f"  find {output_root} -name '*.jpg' | sort",
                f"  cat {activity_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "case_root": str(case_root),
        "library_root": str(library_root),
        "db_path": str(db_path),
        "output_root": str(output_root),
        "activity_path": str(activity_path),
        "readme_path": str(readme_path),
        "activity": PHOTO_REVIEW_ACTIVITY,
        "commands": [
            f"singine photo export-review {output_root} --library-root {library_root} --db {db_path} --max-kb 500 --max-dim 2560 --json",
            f"column -t -s $'\\t' {output_root / 'manifest.tsv'}",
            f"find {output_root} -name '*.jpg' | sort",
            f"cat {activity_path}",
        ],
    }


def _iter_assets(db_path: Path, cities: Sequence[str]) -> Iterable[sqlite3.Row]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield from conn.execute(build_asset_query(cities))
    finally:
        conn.close()


def count_city_photos(db_path: Path, cities: Sequence[str]) -> List[Dict[str, object]]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(build_count_query(cities)).fetchall()
    finally:
        conn.close()
    return [{"city": row["city"], "photo_count": row["photo_count"]} for row in rows]


def export_city_review(
    *,
    library_root: Path,
    db_path: Path,
    out_root: Path,
    cities: Sequence[str],
    max_kb: int,
    max_dim: int,
    limit: int = 0,
) -> Dict[str, object]:
    _require_db(db_path)
    _require_tools()

    out_root.mkdir(parents=True, exist_ok=True)
    for city in cities:
        (out_root / city.lower()).mkdir(parents=True, exist_ok=True)

    manifest = out_root / "manifest.tsv"
    path_lists = {city.lower(): out_root / f"{city.lower()}.paths" for city in cities}

    manifest.write_text(
        "city\tcapture_stamp\tuuid\toriginal_filename\tsource_path\toutput_path\tbytes\n",
        encoding="utf-8",
    )
    for path_list in path_lists.values():
        path_list.write_text("", encoding="utf-8")

    exported = 0
    missing: List[Dict[str, str]] = []

    for row in _iter_assets(db_path, cities):
        if limit > 0 and exported >= limit:
            break

        city = str(row["city"]).lower()
        capture_stamp = row["capture_stamp"] or "unknown"
        uuid = row["ZUUID"]
        original_filename = row["ZFILENAME"]
        zdirectory = row["ZDIRECTORY"]

        source = resolve_source(library_root, uuid, zdirectory, original_filename)
        if source is None:
            missing.append({"uuid": uuid, "filename": original_filename, "city": city})
            continue

        safe_name = sanitize_filename(original_filename)
        destination = out_root / city / f"{capture_stamp}_{safe_name}_{uuid}.jpg"

        cmd = [
            "magick",
            str(source),
            "-auto-orient",
            "-strip",
            "-resize",
            f"{max_dim}x{max_dim}>",
            "-sampling-factor",
            "4:2:0",
            "-interlace",
            "Plane",
            "-colorspace",
            "sRGB",
            "-define",
            f"jpeg:extent={max_kb}KB",
            str(destination),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(
                f"magick failed for {source}: {result.stderr.strip() or result.stdout.strip()}"
            )

        size_bytes = destination.stat().st_size
        with manifest.open("a", encoding="utf-8") as handle:
            handle.write(
                f"{city}\t{capture_stamp}\t{uuid}\t{original_filename}\t"
                f"{source}\t{destination}\t{size_bytes}\n"
            )
        with path_lists[city].open("a", encoding="utf-8") as handle:
            handle.write(f"{destination}\n")

        exported += 1

    return {
        "ok": True,
        "library_root": str(library_root),
        "db_path": str(db_path),
        "out_root": str(out_root),
        "cities": [city.lower() for city in cities],
        "exported": exported,
        "missing_sources": missing,
        "manifest": str(manifest),
        "path_lists": {city: str(path) for city, path in path_lists.items()},
    }


def cmd_photo_count(args: argparse.Namespace) -> int:
    cities = [city.lower() for city in (args.city or list(DEFAULT_REVIEW_CITIES))]
    try:
        payload = {
            "ok": True,
            "db_path": str(Path(args.db).expanduser()),
            "cities": cities,
            "counts": count_city_photos(Path(args.db).expanduser(), cities),
        }
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)}

    if args.json:
        _print_json(payload)
        return 0 if payload.get("ok") else 1

    if not payload.get("ok"):
        print(payload["error"], file=sys.stderr)
        return 1

    for item in payload["counts"]:
        print(f"{item['city']}: {item['photo_count']}")
    return 0


def cmd_photo_export_review(args: argparse.Namespace) -> int:
    cities = [city.lower() for city in (args.city or list(DEFAULT_REVIEW_CITIES))]
    try:
        payload = export_city_review(
            library_root=Path(args.library_root).expanduser(),
            db_path=Path(args.db).expanduser(),
            out_root=Path(args.out_root).expanduser(),
            cities=cities,
            max_kb=args.max_kb,
            max_dim=args.max_dim,
            limit=args.limit,
        )
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)}

    if args.json:
        _print_json(payload)
        return 0 if payload.get("ok") else 1

    if not payload.get("ok"):
        print(payload["error"], file=sys.stderr)
        return 1

    print(f"Exported {payload['exported']} files to {payload['out_root']}")
    print(f"Manifest: {payload['manifest']}")
    for city, path in payload["path_lists"].items():
        print(f"{city} list: {path}")
    if payload["missing_sources"]:
        print(f"Missing sources: {len(payload['missing_sources'])}", file=sys.stderr)
    return 0


def cmd_photo_test_case(args: argparse.Namespace) -> int:
    case_root = Path(args.case_root).expanduser()
    try:
        payload = create_photo_test_case(case_root)
    except Exception as exc:
        payload = {"ok": False, "error": str(exc)}

    if args.json:
        _print_json(payload)
        return 0 if payload.get("ok") else 1

    if not payload.get("ok"):
        print(payload["error"], file=sys.stderr)
        return 1

    print(f"Created test case at {payload['case_root']}")
    print(f"Fixture library: {payload['library_root']}")
    print(f"Readme: {payload['readme_path']}")
    for command in payload["commands"]:
        print(command)
    return 0
