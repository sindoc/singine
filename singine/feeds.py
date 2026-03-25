"""singine.feeds — Atom 1.0 and RSS 1.0 (RDF-aligned) feed generation.

Produces:
  /feeds/activity.atom   — Atom 1.0 feed of singine domain events
  /feeds/activity.rss    — RSS 1.0 (RDF-aligned) feed
  /feeds/decisions.atom  — Atom feed of governance decisions
  /feeds/decisions.rss   — RSS 1.0 of governance decisions

RSS 1.0 uses the rdf:about URI pattern for full RDF alignment.
SKOS concept URNs tag each item for glossary alignment.

Usage::

    singine feeds generate --output-dir /tmp/feeds
    singine feeds atom    # stdout
    singine feeds rss     # stdout
"""
from __future__ import annotations

import json
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional


FEED_BASE_URL = "https://sindoc.local"
FEED_AUTHOR_NAME = "Sina Heshmati"
FEED_AUTHOR_EMAIL = "skh@sindoc.io"

NAMESPACES = {
    "rdf":  "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss":  "http://purl.org/rss/1.0/",
    "dc":   "http://purl.org/dc/elements/1.1/",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "kya":  "urn:knowyourai:vocab#",
    "sg":   "urn:singine:vocab#",
}


@dataclass
class FeedEntry:
    id: str                  # URN or URL
    title: str
    summary: str
    updated: str             # ISO-8601
    link: str = ""
    author: str = FEED_AUTHOR_NAME
    skos_concept: str = ""   # knowyourai concept URN
    human_led: Optional[bool] = None
    tags: List[str] = field(default_factory=list)


# ── Load domain events from singine DB ────────────────────────────────────────

def _domain_events(limit: int = 20, db: str = "/tmp/humble-idp.db") -> List[Dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["singine", "domain", "event", "log", "--limit", str(limit),
             "--json", "--db", db],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            return data.get("events", data) if isinstance(data, dict) else data
    except Exception:
        pass
    return []


def _governance_decisions(limit: int = 20, db: str = "/tmp/humble-idp.db") -> List[Dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["singine", "domain", "tx", "list", "--json", "--db", db],
            capture_output=True, text=True, timeout=15,
        )
        if proc.returncode == 0:
            data = json.loads(proc.stdout)
            return data.get("transactions", data) if isinstance(data, dict) else data
    except Exception:
        pass
    return []


def _events_to_entries(events: List[Dict[str, Any]]) -> List[FeedEntry]:
    entries = []
    for ev in events:
        event_type = ev.get("event_type", ev.get("type", "EVENT"))
        subject = ev.get("subject_id", ev.get("subject", "unknown"))
        ts = ev.get("created_at", ev.get("timestamp", datetime.now(timezone.utc).isoformat()))
        ev_id = ev.get("id", ev.get("event_id", f"urn:singine:event:{subject}"))
        human = event_type in ("PRESENCE_VERIFIED", "GOVERNANCE_DECISION", "AI_SESSION_STARTED")
        entries.append(FeedEntry(
            id=f"urn:singine:event:{ev_id}",
            title=f"{event_type}: {subject}",
            summary=json.dumps(ev, indent=2),
            updated=ts,
            link=f"{FEED_BASE_URL}/panel/events/{ev_id}",
            skos_concept="urn:singine:net:concept:domain-event",
            human_led=human,
            tags=[event_type.lower().replace("_", "-")],
        ))
    return entries


def _decisions_to_entries(txs: List[Dict[str, Any]]) -> List[FeedEntry]:
    entries = []
    for tx in txs:
        tx_type = tx.get("type", "GOVERNANCE")
        subject = tx.get("subject_id", "unknown")
        status = tx.get("status", "PENDING")
        ts = tx.get("created_at", datetime.now(timezone.utc).isoformat())
        tx_id = tx.get("id", tx.get("tx_id", f"urn:singine:tx:{subject}"))
        entries.append(FeedEntry(
            id=f"urn:singine:tx:{tx_id}",
            title=f"Decision [{status}]: {subject}",
            summary=f"Type: {tx_type}\nStatus: {status}\n{json.dumps(tx, indent=2)}",
            updated=ts,
            link=f"{FEED_BASE_URL}/panel/decisions/{tx_id}",
            skos_concept="urn:singine:net:concept:governance-decision",
            human_led=True,
            tags=["governance", status.lower()],
        ))
    return entries


# ── Atom 1.0 serialiser ────────────────────────────────────────────────────────

def _atom_feed(title: str, feed_id: str, entries: List[FeedEntry]) -> str:
    now = datetime.now(timezone.utc).isoformat()
    items = []
    for e in entries:
        human_tag = ""
        if e.human_led is True:
            human_tag = '    <kya:humanLed xmlns:kya="urn:knowyourai:vocab#">true</kya:humanLed>\n'
        elif e.human_led is False:
            human_tag = '    <kya:humanLed xmlns:kya="urn:knowyourai:vocab#">false</kya:humanLed>\n'
        skos_tag = (f'    <skos:subject xmlns:skos="http://www.w3.org/2004/02/skos/core#"'
                    f' rdf:resource="{escape(e.skos_concept)}"'
                    f' xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"/>\n'
                    if e.skos_concept else "")
        items.append(f"""  <entry>
    <id>{escape(e.id)}</id>
    <title>{escape(e.title)}</title>
    <updated>{escape(e.updated)}</updated>
    <author><name>{escape(e.author)}</name></author>
    <summary type="text">{escape(e.summary)}</summary>
    <link href="{escape(e.link)}" rel="alternate"/>
{human_tag}{skos_tag}  </entry>""")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom"\n'
        '      xmlns:kya="urn:knowyourai:vocab#"\n'
        '      xmlns:skos="http://www.w3.org/2004/02/skos/core#"\n'
        '      xmlns:sg="urn:singine:vocab#">\n'
        f'  <id>{escape(feed_id)}</id>\n'
        f'  <title>{escape(title)}</title>\n'
        f'  <updated>{now}</updated>\n'
        f'  <author><name>{FEED_AUTHOR_NAME}</name><email>{FEED_AUTHOR_EMAIL}</email></author>\n'
        f'  <link href="{FEED_BASE_URL}/feeds/" rel="self"/>\n'
        + "\n".join(items)
        + "\n</feed>\n"
    )


# ── RSS 1.0 serialiser (RDF-aligned) ──────────────────────────────────────────

def _rss10_feed(title: str, feed_id: str, entries: List[FeedEntry]) -> str:
    """RSS 1.0 uses RDF triples — every item is an rdf:Description."""
    now = datetime.now(timezone.utc).isoformat()
    items_ref = "\n".join(
        f'    <rss:item rdf:resource="{escape(e.link or e.id)}"/>'
        for e in entries
    )
    items_body = []
    for e in entries:
        human_tag = ""
        if e.human_led is not None:
            human_tag = (f'\n    <kya:humanLed>{str(e.human_led).lower()}</kya:humanLed>')
        items_body.append(f"""  <rss:item rdf:about="{escape(e.link or e.id)}">
    <rss:title>{escape(e.title)}</rss:title>
    <rss:link>{escape(e.link)}</rss:link>
    <rss:description>{escape(e.summary[:500])}</rss:description>
    <dc:date>{escape(e.updated)}</dc:date>
    <dc:creator>{escape(e.author)}</dc:creator>
    <dc:subject rdf:resource="{escape(e.skos_concept)}"/>
    <sg:singineConcept rdf:resource="{escape(e.id)}"/>{human_tag}
  </rss:item>""")

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rdf:RDF\n'
        '  xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
        '  xmlns:rss="http://purl.org/rss/1.0/"\n'
        '  xmlns:dc="http://purl.org/dc/elements/1.1/"\n'
        '  xmlns:kya="urn:knowyourai:vocab#"\n'
        '  xmlns:skos="http://www.w3.org/2004/02/skos/core#"\n'
        '  xmlns:sg="urn:singine:vocab#">\n\n'
        f'  <rss:channel rdf:about="{escape(feed_id)}">\n'
        f'    <rss:title>{escape(title)}</rss:title>\n'
        f'    <rss:link>{FEED_BASE_URL}/feeds/</rss:link>\n'
        f'    <rss:description>singine activity feed — {escape(title)}</rss:description>\n'
        f'    <dc:date>{now}</dc:date>\n'
        '    <rss:items>\n'
        '      <rdf:Seq>\n'
        f'{items_ref}\n'
        '      </rdf:Seq>\n'
        '    </rss:items>\n'
        '  </rss:channel>\n\n'
        + "\n".join(items_body)
        + "\n</rdf:RDF>\n"
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def activity_atom(db: str = "/tmp/humble-idp.db", limit: int = 20) -> str:
    events = _domain_events(limit=limit, db=db)
    entries = _events_to_entries(events)
    return _atom_feed(
        "singine activity",
        f"{FEED_BASE_URL}/feeds/activity.atom",
        entries,
    )


def activity_rss(db: str = "/tmp/humble-idp.db", limit: int = 20) -> str:
    events = _domain_events(limit=limit, db=db)
    entries = _events_to_entries(events)
    return _rss10_feed(
        "singine activity",
        f"{FEED_BASE_URL}/feeds/activity.rss",
        entries,
    )


def decisions_atom(db: str = "/tmp/humble-idp.db", limit: int = 20) -> str:
    txs = _governance_decisions(limit=limit, db=db)
    entries = _decisions_to_entries(txs)
    return _atom_feed(
        "singine governance decisions",
        f"{FEED_BASE_URL}/feeds/decisions.atom",
        entries,
    )


def decisions_rss(db: str = "/tmp/humble-idp.db", limit: int = 20) -> str:
    txs = _governance_decisions(limit=limit, db=db)
    entries = _decisions_to_entries(txs)
    return _rss10_feed(
        "singine governance decisions",
        f"{FEED_BASE_URL}/feeds/decisions.rss",
        entries,
    )


def generate_all(output_dir: Path, db: str = "/tmp/humble-idp.db") -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    files: Dict[str, str] = {}
    for name, content_fn in [
        ("activity.atom",   lambda: activity_atom(db)),
        ("activity.rss",    lambda: activity_rss(db)),
        ("decisions.atom",  lambda: decisions_atom(db)),
        ("decisions.rss",   lambda: decisions_rss(db)),
    ]:
        path = output_dir / name
        content = content_fn()
        path.write_text(content, encoding="utf-8")
        files[name] = str(path)
    return files


def cmd_generate(args) -> int:
    output_dir = Path(getattr(args, "output_dir", "/tmp/singine-feeds"))
    db = getattr(args, "db", "/tmp/humble-idp.db")
    files = generate_all(output_dir, db=db)
    for name, path in files.items():
        print(f"  {name}  →  {path}")
    return 0


def cmd_atom(args) -> int:
    db = getattr(args, "db", "/tmp/humble-idp.db")
    kind = getattr(args, "kind", "activity")
    fn = decisions_atom if kind == "decisions" else activity_atom
    print(fn(db=db))
    return 0


def cmd_rss(args) -> int:
    db = getattr(args, "db", "/tmp/humble-idp.db")
    kind = getattr(args, "kind", "activity")
    fn = decisions_rss if kind == "decisions" else activity_rss
    print(fn(db=db))
    return 0
