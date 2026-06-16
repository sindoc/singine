"""
singine-mcp-photo — MCP server for personal photo classification.

Combines Gemma 3 4B vision (via Ollama, local inference) with DeepFace
face recognition to produce a classification envelope for each photo:
  - recognized faces (identity + confidence)
  - scene analysis (occasion, setting, sentiment, description)
  - archival decision (keep / archive-separate / archive-secondary / review)

Transport: stdio — register with:
  claude mcp add singine-photo --transport stdio -- \\
      python3 /path/to/io.lutino.mcp/mcp-photo/src/server.py

Prerequisites:
  ollama pull gemma3:4b       # ~3 GB, runs fully offline
  pip install deepface ollama Pillow tf-keras
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="singine-photo",
    version="0.1.0",
    description=(
        "Photo classification: enroll faces, recognize people in photos, "
        "analyze scenes with Gemma 3, and produce archival decisions."
    ),
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ENROLL_DB_DIR = Path(os.environ.get(
    "SINGINE_FACE_DB",
    Path.home() / ".singine" / "faces",
))


def _face_db_path() -> str:
    """Return the DeepFace DB directory, creating it if absent."""
    _ENROLL_DB_DIR.mkdir(parents=True, exist_ok=True)
    return str(_ENROLL_DB_DIR)


def _recognize(image_path: str) -> list[dict[str, Any]]:
    """Run DeepFace recognition against the enrolled face database."""
    from deepface import DeepFace  # late import — heavy

    db = _face_db_path()
    try:
        results = DeepFace.find(
            img_path=image_path,
            db_path=db,
            model_name="ArcFace",
            detector_backend="retinaface",
            enforce_detection=False,
            silent=True,
        )
    except Exception as exc:
        return [{"name": "error", "confidence": 0.0, "error": str(exc)}]

    faces: list[dict[str, Any]] = []
    for df in results:
        if df.empty:
            continue
        for _, row in df.iterrows():
            # DeepFace stores reference images as <db>/<name>/<file>.jpg
            identity_path = Path(str(row.get("identity", "")))
            name = identity_path.parent.name if identity_path.parent != _ENROLL_DB_DIR else "unknown"
            distance = float(row.get("distance", 1.0))
            threshold = float(row.get("threshold", 0.4))
            confidence = max(0.0, 1.0 - (distance / max(threshold, 1e-6)))
            faces.append({
                "name": name,
                "confidence": round(confidence, 3),
                "source_x": int(row.get("source_x", 0)),
                "source_y": int(row.get("source_y", 0)),
                "source_w": int(row.get("source_w", 0)),
                "source_h": int(row.get("source_h", 0)),
            })

    return faces if faces else [{"name": "no_face_detected", "confidence": 1.0}]


def _analyze_with_gemma3(image_path: str) -> dict[str, Any]:
    """Send the photo to Gemma 3 4B via Ollama and parse structured output."""
    import ollama  # late import

    prompt = (
        "Analyze this photo and respond ONLY with a JSON object (no markdown). "
        "Fields:\n"
        '  "occasion": one of birthday|holiday|gathering|travel|daily_life|scenery|ceremony|other\n'
        '  "setting": one of indoor|outdoor|mixed\n'
        '  "sentiment": one of celebratory|joyful|neutral|solemn|candid\n'
        '  "description": one plain sentence describing the main subject and context\n'
        '  "people_count": integer — number of people visible\n'
        '  "has_children": true or false\n'
        "Do not include any other text."
    )

    try:
        with open(image_path, "rb") as fh:
            image_bytes = fh.read()

        response = ollama.chat(
            model="gemma3:4b",
            messages=[{
                "role": "user",
                "content": prompt,
                "images": [image_bytes],
            }],
        )
        raw = response["message"]["content"].strip()
        # Strip accidental markdown fences
        if raw.startswith("```"):
            raw = "\n".join(
                line for line in raw.splitlines()
                if not line.startswith("```")
            )
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "occasion": "other",
            "setting": "unknown",
            "sentiment": "neutral",
            "description": "Unable to parse Gemma 3 response.",
            "people_count": 0,
            "has_children": False,
        }
    except Exception as exc:
        return {
            "occasion": "error",
            "setting": "error",
            "sentiment": "neutral",
            "description": f"Gemma 3 error: {exc}",
            "people_count": 0,
            "has_children": False,
        }


def _decide(faces: list[dict], scene: dict) -> dict[str, str]:
    """Apply deterministic archival rules given faces + scene."""
    names = {f["name"] for f in faces}

    if "ex_wife" in names or "ex_spouse" in names:
        if names - {"ex_wife", "ex_spouse", "self", "no_face_detected"}:
            # Mixed: ex-spouse + family/friends — separate archive
            return {
                "category": "ExSpousePresent",
                "action": "ArchiveSeparate",
                "reason": "ex_spouse present alongside family/friends",
            }
        return {
            "category": "ExSpousePresent",
            "action": "ArchiveSeparate",
            "reason": "ex_spouse present",
        }

    if names == {"no_face_detected"} or not names:
        return {
            "category": "SceneryOnly",
            "action": "ArchiveSecondary",
            "reason": "no people detected",
        }

    if "unknown" in names and len(names) == 1:
        return {
            "category": "UnclassifiedPhoto",
            "action": "FlagForReview",
            "reason": "only unknown faces — manual review needed",
        }

    known_family_or_friends = names - {"self", "unknown", "no_face_detected",
                                        "ex_wife", "ex_spouse"}
    if known_family_or_friends:
        return {
            "category": "FamilyPhoto",
            "action": "KeepPrimary",
            "reason": f"family/friends present: {', '.join(sorted(known_family_or_friends))}",
        }

    # Self only or low-confidence unknowns
    low_confidence = all(f["confidence"] < 0.55 for f in faces)
    if low_confidence:
        return {
            "category": "UnclassifiedPhoto",
            "action": "FlagForReview",
            "reason": "low-confidence recognition across all faces",
        }

    return {
        "category": "FamilyPhoto",
        "action": "KeepPrimary",
        "reason": "self or recognized people present",
    }


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def enroll_person(name: str, reference_photo_paths: list[str]) -> dict:
    """Register a person's identity by copying reference photos into the face DB.

    Args:
        name: Identifier used in decisions, e.g. "daughter", "ex_wife", "self".
              Use "ex_wife" or "ex_spouse" to trigger the separate-archive rule.
        reference_photo_paths: Absolute paths to 3-10 clear, front-facing photos.

    Returns ok=True when enrollment is complete.
    """
    import shutil

    person_dir = _ENROLL_DB_DIR / name
    person_dir.mkdir(parents=True, exist_ok=True)

    copied = []
    errors = []
    for src in reference_photo_paths:
        p = Path(src)
        if not p.exists():
            errors.append(f"not found: {src}")
            continue
        dest = person_dir / p.name
        shutil.copy2(p, dest)
        copied.append(str(dest))

    return {
        "ok": len(errors) == 0,
        "name": name,
        "enrolled": len(copied),
        "copied": copied,
        "errors": errors,
        "db_dir": str(person_dir),
    }


@mcp.tool()
def list_enrolled() -> dict:
    """List all enrolled identities and their reference photo counts."""
    db = _ENROLL_DB_DIR
    if not db.exists():
        return {"ok": True, "people": []}

    people = []
    for person_dir in sorted(db.iterdir()):
        if person_dir.is_dir():
            photos = [
                f.name for f in person_dir.iterdir()
                if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".heic", ".webp"}
            ]
            people.append({"name": person_dir.name, "reference_count": len(photos)})

    return {"ok": True, "people": people, "db_dir": str(db)}


@mcp.tool()
def recognize_faces(image_path: str) -> dict:
    """Recognize faces in a photo against the enrolled identity database.

    Args:
        image_path: Absolute path to a JPEG, PNG, HEIC, or WebP file.

    Returns a list of {name, confidence, bbox} objects, one per detected face.
    """
    if not Path(image_path).exists():
        return {"ok": False, "error": f"file not found: {image_path}"}

    faces = _recognize(image_path)
    return {"ok": True, "image": image_path, "faces": faces}


@mcp.tool()
def analyze_scene(image_path: str) -> dict:
    """Analyze the scene and context of a photo using Gemma 3 4B (local Ollama).

    Args:
        image_path: Absolute path to the photo.

    Returns occasion, setting, sentiment, description, people_count, has_children.
    Requires: ollama running locally with gemma3:4b pulled.
    """
    if not Path(image_path).exists():
        return {"ok": False, "error": f"file not found: {image_path}"}

    scene = _analyze_with_gemma3(image_path)
    return {"ok": True, "image": image_path, "scene": scene}


@mcp.tool()
def classify_photo(image_path: str) -> dict:
    """Classify a photo: recognize faces + analyze scene + produce archival decision.

    This is the main tool — it runs recognize_faces and analyze_scene together
    and applies the archival decision rules.

    Decision rules (in priority order):
      1. ex_wife / ex_spouse present → ArchiveSeparate
      2. No faces detected           → ArchiveSecondary (scenery)
      3. Only unknown, low-confidence faces → FlagForReview
      4. Known family/friends present → KeepPrimary
      5. Default                      → FlagForReview

    Args:
        image_path: Absolute path to the photo to classify.

    Returns:
        {ok, image, faces, scene, decision: {category, action, reason}}
    """
    if not Path(image_path).exists():
        return {"ok": False, "error": f"file not found: {image_path}"}

    faces = _recognize(image_path)
    scene = _analyze_with_gemma3(image_path)
    decision = _decide(faces, scene)

    return {
        "ok": True,
        "image": image_path,
        "faces": faces,
        "scene": scene,
        "decision": decision,
    }


@mcp.tool()
def batch_classify(image_paths: list[str]) -> dict:
    """Classify multiple photos in sequence.

    Args:
        image_paths: List of absolute paths to classify.

    Returns a list of classification results, one per image.
    Errors for individual images are captured per-result, not raised globally.
    """
    results = []
    for path in image_paths:
        try:
            result = classify_photo(path)
        except Exception as exc:
            result = {"ok": False, "image": path, "error": str(exc)}
        results.append(result)

    summary = {
        "KeepPrimary": 0,
        "ArchiveSeparate": 0,
        "ArchiveSecondary": 0,
        "FlagForReview": 0,
        "error": 0,
    }
    for r in results:
        if r.get("ok"):
            action = r.get("decision", {}).get("action", "FlagForReview")
            summary[action] = summary.get(action, 0) + 1
        else:
            summary["error"] += 1

    return {"ok": True, "total": len(image_paths), "summary": summary, "results": results}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
