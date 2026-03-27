from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DEFAULT_BASE_URL = "https://api.zotero.org"
DEFAULT_PROFILE = "singine-dev"


class ZoteroError(RuntimeError):
    pass


@dataclass
class ZoteroConfig:
    api_key: str
    profile: str
    base_url: str
    library_type: str
    library_id: str

    @property
    def library_path(self) -> str:
        if self.library_type == "group":
            return f"/groups/{self.library_id}"
        return f"/users/{self.library_id}"


def _profile_token(profile: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", profile).strip("_").upper()


def resolve_config(
    *,
    api_key: Optional[str] = None,
    profile: str = DEFAULT_PROFILE,
    base_url: Optional[str] = None,
    library_type: Optional[str] = None,
    user_id: Optional[str] = None,
    group_id: Optional[str] = None,
) -> ZoteroConfig:
    suffix = _profile_token(profile)
    api_key = (
        api_key
        or os.environ.get(f"ZOTERO_API_KEY_{suffix}")
        or os.environ.get("ZOTERO_API_KEY")
    )
    if not api_key:
        raise ZoteroError(
            f"Missing Zotero API key. Set ZOTERO_API_KEY_{suffix} or ZOTERO_API_KEY."
        )

    base_url = (base_url or os.environ.get("ZOTERO_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    library_type = (library_type or os.environ.get("ZOTERO_LIBRARY_TYPE") or "user").strip().lower()
    if library_type not in {"user", "group"}:
        raise ZoteroError("library type must be 'user' or 'group'")

    if library_type == "group":
        library_id = group_id or os.environ.get("ZOTERO_GROUP_ID")
        if not library_id:
            raise ZoteroError("Missing group library ID. Set --group-id or ZOTERO_GROUP_ID.")
    else:
        library_id = user_id or os.environ.get("ZOTERO_USER_ID")
        if not library_id:
            raise ZoteroError("Missing user library ID. Set --user-id or ZOTERO_USER_ID.")

    return ZoteroConfig(
        api_key=api_key,
        profile=profile,
        base_url=base_url,
        library_type=library_type,
        library_id=str(library_id),
    )


def _request_json(
    config: ZoteroConfig,
    method: str,
    path: str,
    *,
    body: Any = None,
    params: Optional[Dict[str, Any]] = None,
) -> Any:
    url = f"{config.base_url}{path}"
    if params:
        filtered = {k: v for k, v in params.items() if v not in (None, "", [])}
        if filtered:
            url += "?" + urllib.parse.urlencode(filtered, doseq=True)

    data = None
    headers = {
        "Zotero-API-Key": config.api_key,
        "Zotero-API-Version": "3",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = resp.read().decode("utf-8")
            return json.loads(payload) if payload else {}
    except Exception as exc:  # pragma: no cover - exercised via callers/tests
        raise ZoteroError(str(exc)) from exc


def find_collection(config: ZoteroConfig, name: str, *, parent_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    collections = _request_json(
        config,
        "GET",
        f"{config.library_path}/collections",
        params={"q": name, "qmode": "title", "limit": 100},
    )
    for collection in collections:
        data = collection.get("data", {})
        if data.get("name") != name:
            continue
        if parent_key is not None and data.get("parentCollection") != parent_key:
            continue
        return collection
    return None


def ensure_collection(
    config: ZoteroConfig,
    name: str,
    *,
    parent_key: Optional[str] = None,
    create: bool = False,
) -> Dict[str, Any]:
    collection = find_collection(config, name, parent_key=parent_key)
    if collection:
        return collection
    if not create:
        raise ZoteroError(f"Collection not found: {name}")

    payload: Dict[str, Any] = {"name": name}
    if parent_key:
        payload["parentCollection"] = parent_key
    _request_json(config, "POST", f"{config.library_path}/collections", body=[payload])
    created = find_collection(config, name, parent_key=parent_key)
    if not created:
        raise ZoteroError(f"Collection creation did not yield a resolvable collection: {name}")
    return created


def add_item(
    config: ZoteroConfig,
    *,
    collection_name: str,
    url: str,
    title: Optional[str] = None,
    item_type: str = "webpage",
    website_title: Optional[str] = None,
    publication_title: Optional[str] = None,
    date: Optional[str] = None,
    access_date: Optional[str] = None,
    note: Optional[str] = None,
    tags: Optional[List[str]] = None,
    create_collection: bool = False,
    parent_collection: Optional[str] = None,
) -> Dict[str, Any]:
    parent_key = None
    if parent_collection:
        parent = ensure_collection(config, parent_collection, create=create_collection)
        parent_key = parent["key"]

    collection = ensure_collection(
        config,
        collection_name,
        parent_key=parent_key,
        create=create_collection,
    )

    payload: Dict[str, Any] = {
        "itemType": item_type,
        "title": title or url,
        "url": url,
        "collections": [collection["key"]],
    }
    if website_title:
        payload["websiteTitle"] = website_title
    if publication_title:
        payload["publicationTitle"] = publication_title
    if date:
        payload["date"] = date
    if access_date:
        payload["accessDate"] = access_date
    if note:
        payload["abstractNote"] = note
    if tags:
        payload["tags"] = [{"tag": tag} for tag in tags]

    response = _request_json(config, "POST", f"{config.library_path}/items", body=[payload])
    return {
        "ok": True,
        "profile": config.profile,
        "library_type": config.library_type,
        "library_id": config.library_id,
        "collection": {
            "name": collection_name,
            "key": collection["key"],
            "parent_key": parent_key,
        },
        "item": payload,
        "response": response,
    }
