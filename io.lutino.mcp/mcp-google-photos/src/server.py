"""
singine-mcp-google-photos — MCP server for Google Photos via REST API + OAuth2.

Reads the Google Photos library to list albums, search media items, download
originals, and generate a deletion manifest (Google Photos API does not support
deletion — the manifest is used manually at photos.google.com).

Transport: stdio — register with:
  claude mcp add singine-google-photos --transport stdio -- \\
      python3 /path/to/io.lutino.mcp/mcp-google-photos/src/server.py

ONE-TIME SETUP:
  1. Go to https://console.cloud.google.com
  2. Create a project → Enable "Photos Library API"
  3. Create OAuth2 credentials → Desktop application → Download JSON
  4. Save as: ~/.singine/google-photos-client-secret.json
  5. First call to any tool will open a browser for OAuth consent
  6. Token saved to: ~/.singine/google-photos-token.json

Scopes used: photoslibrary.readonly (read-only — no delete via API)
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="singine-google-photos",
    instructions=(
        "Google Photos read access: list albums, search photos, download originals. "
        "Generates deletion manifests (CSV + JSON) for manual deletion at photos.google.com. "
        "Requires one-time OAuth2 setup — see server docstring."
    ),
)

_CREDENTIALS_FILE = Path(os.environ.get(
    "SINGINE_GOOGLE_CREDENTIALS",
    Path.home() / ".singine" / "google-photos-client-secret.json",
))
_TOKEN_FILE = Path(os.environ.get(
    "SINGINE_GOOGLE_TOKEN",
    Path.home() / ".singine" / "google-photos-token.json",
))
_STAGING_DIR = Path(os.environ.get(
    "SINGINE_PHOTO_STAGING",
    Path.home() / ".singine" / "photo-staging",
))
_DELETION_MANIFEST_CSV = Path(os.environ.get(
    "SINGINE_GOOGLE_DELETION_CSV",
    Path.home() / ".singine" / "google-photos-deletion-manifest.csv",
))

_PENDING_OAUTH_URL_FILE = Path(os.environ.get(
    "SINGINE_GOOGLE_PENDING_AUTH_URL",
    Path.home() / ".singine" / "pending-oauth-url.txt",
))

_SCOPES = ["https://www.googleapis.com/auth/photoslibrary.readonly"]
_API_BASE = os.environ.get(
    "SINGINE_GOOGLE_API_BASE",
    "https://photoslibrary.googleapis.com/v1",
)

# ---------------------------------------------------------------------------
# OAuth2
# ---------------------------------------------------------------------------

def _run_oauth_flow(flow):
    """Run the OAuth2 installed-app flow, saving the auth URL before opening browser."""
    import http.server
    import socket
    import subprocess
    import urllib.parse

    # Find a free port
    with socket.socket() as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    flow.redirect_uri = f"http://localhost:{port}/"
    auth_url, _ = flow.authorization_url(access_type="offline")

    # Save URL immediately — readable via `sng photos.google url`
    try:
        _PENDING_OAUTH_URL_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PENDING_OAUTH_URL_FILE.write_text(auth_url, encoding="utf-8")
    except OSError:
        pass

    print(f"\nOpen this URL to authorise Google Photos:\n{auth_url}\n", flush=True)
    subprocess.Popen(["open", auth_url])  # macOS: open in default browser

    # Minimal HTTP server to catch the OAuth callback
    code_holder: list[str] = []

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code_holder.extend(params.get("code", []))
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Authorised. You may close this tab.</h2>")
        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("localhost", port), _Handler)
    server.handle_request()  # blocks until one request arrives
    server.server_close()

    if not code_holder:
        raise RuntimeError("OAuth2 callback received no authorisation code.")

    flow.fetch_token(code=code_holder[0])
    return flow.credentials


def _load_credentials():
    """Load or refresh OAuth2 credentials. Opens browser on first run."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None

    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not _CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {_CREDENTIALS_FILE}. "
                    "Download from Google Cloud Console → Credentials → OAuth2 → Desktop app."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDENTIALS_FILE), _SCOPES)
            creds = _run_oauth_flow(flow)
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(creds.to_json())

    return creds


def _api_get(path: str, params: dict | None = None) -> dict:
    creds = _load_credentials()
    url = f"{_API_BASE}/{path}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{url}?{query}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {creds.token}"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _api_post(path: str, body: dict) -> dict:
    creds = _load_credentials()
    url = f"{_API_BASE}/{path}"
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {creds.token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def _media_item_to_dict(item: dict) -> dict:
    meta = item.get("mediaMetadata", {})
    photo_meta = meta.get("photo", {})
    video_meta = meta.get("video", {})
    return {
        "id": item.get("id"),
        "filename": item.get("filename"),
        "mime_type": item.get("mimeType"),
        "date_created": meta.get("creationTime"),
        "width": meta.get("width"),
        "height": meta.get("height"),
        "camera_make": photo_meta.get("cameraMake") or video_meta.get("cameraMake"),
        "camera_model": photo_meta.get("cameraModel") or video_meta.get("cameraModel"),
        "focal_length": photo_meta.get("focalLength"),
        "aperture": photo_meta.get("apertureFNumber"),
        "iso": photo_meta.get("isoEquivalent"),
        "exposure_time": photo_meta.get("exposureTime"),
        "base_url": item.get("baseUrl"),
        "product_url": item.get("productUrl"),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def google_photos_auth_status() -> dict:
    """Check Google Photos authentication status.

    Returns ok=True if credentials are valid. On first run, opens a browser
    window for OAuth2 consent. Requires google-photos-client-secret.json.
    """
    try:
        creds = _load_credentials()
        return {
            "ok": True,
            "authenticated": True,
            "scopes": list(creds.scopes or _SCOPES),
            "token_path": str(_TOKEN_FILE),
            "credentials_path": str(_CREDENTIALS_FILE),
        }
    except FileNotFoundError as exc:
        return {
            "ok": False,
            "authenticated": False,
            "error": str(exc),
            "setup_steps": [
                "1. Go to https://console.cloud.google.com",
                "2. Create project → Enable 'Photos Library API'",
                "3. Create OAuth2 credentials → Desktop app → Download JSON",
                f"4. Save as: {_CREDENTIALS_FILE}",
                "5. Call this tool again to complete OAuth2 consent in browser",
            ],
        }
    except Exception as exc:
        return {"ok": False, "authenticated": False, "error": str(exc)}


@mcp.tool()
def list_albums() -> dict:
    """List all albums in Google Photos."""
    try:
        albums = []
        page_token = None

        while True:
            params: dict[str, Any] = {"pageSize": 50}
            if page_token:
                params["pageToken"] = page_token
            resp = _api_get("albums", params)
            for album in resp.get("albums", []):
                albums.append({
                    "id": album.get("id"),
                    "title": album.get("title"),
                    "photo_count": int(album.get("mediaItemsCount", 0)),
                    "cover_base_url": album.get("coverPhotoBaseUrl"),
                    "product_url": album.get("productUrl"),
                })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        albums.sort(key=lambda a: a["title"] or "")
        return {"ok": True, "albums": albums, "total": len(albums)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def search_photos(
    album_id: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
) -> dict:
    """Search Google Photos media items.

    Args:
        album_id:  Restrict to a specific album ID (from list_albums).
        date_from: Start date, ISO 8601 e.g. "2020-01-01" (optional).
        date_to:   End date, ISO 8601 e.g. "2023-12-31" (optional).
        limit:     Maximum items to return (default 100).

    Returns list of media items with id, filename, date, camera info, base_url.
    Use the id with download_photo to fetch the original file.
    """
    try:
        body: dict[str, Any] = {"pageSize": min(limit, 100)}

        if album_id:
            body["albumId"] = album_id

        filters: dict[str, Any] = {}
        if date_from or date_to:
            date_filter: dict[str, Any] = {}
            if date_from:
                df = datetime.fromisoformat(date_from)
                date_filter["startDate"] = {"year": df.year, "month": df.month, "day": df.day}
            if date_to:
                dt = datetime.fromisoformat(date_to)
                date_filter["endDate"] = {"year": dt.year, "month": dt.month, "day": dt.day}
            filters["dateFilter"] = {"dates": [date_filter]}

        if filters:
            body["filters"] = filters

        items = []
        page_token = None

        while len(items) < limit:
            if page_token:
                body["pageToken"] = page_token
            resp = _api_post("mediaItems:search", body)
            batch = resp.get("mediaItems", [])
            items.extend(batch)
            page_token = resp.get("nextPageToken")
            if not page_token or not batch:
                break

        items = items[:limit]
        return {
            "ok": True,
            "returned": len(items),
            "photos": [_media_item_to_dict(i) for i in items],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def get_photo_metadata(media_item_id: str) -> dict:
    """Get full metadata for a single Google Photos media item.

    Args:
        media_item_id: The Google Photos media item ID (from search_photos).
    """
    try:
        item = _api_get(f"mediaItems/{media_item_id}")
        return {"ok": True, "photo": _media_item_to_dict(item)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@mcp.tool()
def download_photo(media_item_id: str, dest_dir: str = "") -> dict:
    """Download the original photo file from Google Photos.

    Downloads the unmodified original (using =d download parameter).
    Computes SHA-256 of the downloaded file for verification.

    Args:
        media_item_id: Google Photos media item ID.
        dest_dir:      Destination directory. Default: ~/.singine/photo-staging/<id>/
    """
    try:
        # Refresh token in base URL
        item = _api_get(f"mediaItems/{media_item_id}")
        meta = _media_item_to_dict(item)

        base_url = item.get("baseUrl", "")
        if not base_url:
            return {"ok": False, "error": "No baseUrl in media item"}

        # =d downloads original; =dv for video original
        is_video = (item.get("mimeType", "").startswith("video/") or
                    "video" in item.get("mediaMetadata", {}))
        download_url = base_url + ("=dv" if is_video else "=d")

        out_dir = Path(dest_dir) if dest_dir else (_STAGING_DIR / media_item_id)
        out_dir.mkdir(parents=True, exist_ok=True)

        filename = meta.get("filename") or f"{media_item_id}.jpg"
        out_path = out_dir / filename

        creds = _load_credentials()
        req = urllib.request.Request(
            download_url,
            headers={"Authorization": f"Bearer {creds.token}"},
        )
        with urllib.request.urlopen(req) as resp, open(out_path, "wb") as fh:
            while chunk := resp.read(65536):
                fh.write(chunk)

        sha256 = hashlib.sha256()
        with open(out_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha256.update(chunk)

        # Write metadata sidecar
        sidecar = {**meta, "downloaded_path": str(out_path), "sha256": sha256.hexdigest(),
                   "downloaded_at": datetime.now(timezone.utc).isoformat()}
        sidecar_path = out_dir / f"{filename}.singine.json"
        sidecar_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

        return {
            "ok": True,
            "media_item_id": media_item_id,
            "downloaded_path": str(out_path),
            "sidecar_path": str(sidecar_path),
            "sha256": sha256.hexdigest(),
            "filename": filename,
            "size_bytes": out_path.stat().st_size,
        }
    except Exception as exc:
        return {"ok": False, "media_item_id": media_item_id, "error": str(exc)}


@mcp.tool()
def generate_deletion_manifest(media_item_ids: list[str], output_csv: str = "") -> dict:
    """Generate a deletion manifest CSV for photos to remove from Google Photos.

    Google Photos API does not support deletion. This tool produces a CSV manifest
    that you can reference while manually deleting photos at photos.google.com,
    or share with anyone who needs to know which photos to remove.

    Each row: id, filename, date, product_url (direct link to open the photo).

    Args:
        media_item_ids: List of Google Photos media item IDs to mark for deletion.
        output_csv:     Output path. Default: ~/.singine/google-photos-deletion-manifest.csv
    """
    try:
        out_path = Path(output_csv) if output_csv else _DELETION_MANIFEST_CSV
        out_path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for media_id in media_item_ids:
            try:
                item = _api_get(f"mediaItems/{media_id}")
                meta = _media_item_to_dict(item)
                rows.append({
                    "id": media_id,
                    "filename": meta.get("filename", ""),
                    "date_created": meta.get("date_created", ""),
                    "camera_model": meta.get("camera_model", ""),
                    "product_url": meta.get("product_url", ""),
                    "status": "pending-deletion",
                })
            except Exception as e:
                rows.append({"id": media_id, "error": str(e), "status": "fetch-error"})

        # Write CSV
        import csv
        fieldnames = ["id", "filename", "date_created", "camera_model", "product_url", "status", "error"]
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

        # Also write JSON sidecar
        json_path = out_path.with_suffix(".json")
        json_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")

        return {
            "ok": True,
            "total": len(rows),
            "manifest_csv": str(out_path),
            "manifest_json": str(json_path),
            "instructions": [
                "Open each photo_url in your browser to delete manually at photos.google.com",
                "Or: Go to photos.google.com → select photos → delete",
                "The CSV can be imported into a spreadsheet to track deletion progress",
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
