"""SINGE — SINGE Is Not Generally Expansive

(but it is: it expands @mention tokens into governed identities)

A simple template engine for singine.  Resolves ``@person`` references
using a people registry built from three sources, in priority order:

  1. ``~/.singine/singe.people``  (JSON, user-managed, highest priority)
  2. ``humble-idp/config/users.properties``  (IdP registry)
  3. Built-in registry  (project collaborators + historical figures)

Mention syntax
--------------
  @sina        exact key / alias match
  @si          prefix match  (up to 5 chars)
  @sin         prefix match
  @skh         alias match
  @stal        prefix fuzzy  → Richard Stallman

The engine walks: exact → alias-exact → prefix → fuzzy (difflib).

Recursive acronym
-----------------
  S — SINGE
  I — Is
  N — Not
  G — Generally
  E — Expansive
"""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Person:
    key: str
    display: str
    aliases: List[str] = field(default_factory=list)
    email: str = ""
    urn: str = ""
    note: str = ""

    def short(self) -> str:
        """First name or key if display is not set."""
        return self.display.split()[0] if self.display else self.key

    def all_keys(self) -> List[str]:
        return [self.key] + self.aliases


# ---------------------------------------------------------------------------
# Built-in registry
# ---------------------------------------------------------------------------

_BUILTIN: List[Person] = [
    # ── project collaborators ──────────────────────────────────────────
    Person(
        key="attar",
        display="Sina K. Heshmati",
        aliases=["sindoc", "skh", "sina", "sk", "s"],
        email="sina@khakbaz.com",
        urn="urn:singine:machine:imac-vafa:attar",
        note="Primary developer, singine",
    ),
    Person(
        key="arash",
        display="Arash",
        aliases=["ar"],
        urn="urn:singine:user:arash",
    ),
    Person(
        key="soren",
        display="Soren",
        aliases=["so"],
        urn="urn:singine:user:soren",
    ),
    Person(
        key="kaveh",
        display="Kaveh",
        aliases=["khe", "kav", "k"],
        note="KHE",
    ),
    Person(
        key="ehsan",
        display="Ehsan",
        aliases=["ehe", "eh"],
        note="EHE",
    ),
    Person(
        key="javad",
        display="Javad",
        aliases=["jav", "j"],
    ),
    Person(
        key="robin",
        display="Robin",
        aliases=["rob", "ro"],
        note="roundRobinUserLinkedToCronServiceAccountTimeAgent",
    ),
    # ── historical figures ─────────────────────────────────────────────
    Person(
        key="stallman",
        display="Richard Stallman",
        aliases=["rms", "richard", "stal"],
        note="GNU, FSF, GPL, copyleft — the genius behind free software",
    ),
    Person(
        key="joy",
        display="Bill Joy",
        aliases=["bj", "billjoy"],
        note="BSD, vi, Sun — co-founder of Sun Microsystems",
    ),
    Person(
        key="steele",
        display="Guy L. Steele Jr.",
        aliases=["gls", "guySteele", "steel-lee", "guy"],
        note="Scheme, Common Lisp, Java spec, Fortress — language legend",
    ),
    Person(
        key="walsh",
        display="Norman Walsh",
        aliases=["nw", "norman"],
        note="DocBook, XSL, XML — the DocBook maintainer",
    ),
    Person(
        key="clark",
        display="James Clark",
        aliases=["jc", "james"],
        note="XML, SGML, XPath, XSLT — original XML/XPath/XSLT designer",
    ),
    Person(
        key="kay",
        display="Michael Kay",
        aliases=["mk", "michael"],
        note="Saxon, XSLT, XPath — the XSLT/Saxon author",
    ),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class Registry:
    """Holds all known Person entries; supports fast lookup and fuzzy match."""

    def __init__(self, people: Optional[List[Person]] = None) -> None:
        self._people: List[Person] = list(people or [])
        self._index: Dict[str, Person] = {}
        for p in self._people:
            for k in p.all_keys():
                self._index[k.lower()] = p

    def add(self, person: Person) -> None:
        self._people.append(person)
        for k in person.all_keys():
            self._index.setdefault(k.lower(), person)

    def resolve(self, mention: str) -> Optional[Person]:
        """
        Resolve a mention string (without the leading @) to a Person.

        Resolution order:
          1. Exact key/alias match
          2. Prefix match (shortest unambiguous prefix, up to 5 chars)
          3. difflib fuzzy match (cutoff 0.6)
        """
        q = mention.lower().strip()
        if not q:
            return None

        # 1. exact
        if q in self._index:
            return self._index[q]

        # 2. prefix — collect all keys that start with q
        matches = [p for k, p in self._index.items() if k.startswith(q)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            # prefer the one whose key IS q or whose key is shortest
            exact = [p for k, p in self._index.items() if k == q]
            if exact:
                return exact[0]
            return matches[0]

        # 3. fuzzy
        keys = list(self._index.keys())
        close = difflib.get_close_matches(q, keys, n=1, cutoff=0.6)
        if close:
            return self._index[close[0]]

        return None

    def all_people(self) -> List[Person]:
        seen = set()
        result = []
        for p in self._people:
            if id(p) not in seen:
                seen.add(id(p))
                result.append(p)
        return result


# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------

_HUMBLE_IDP_DIR = Path.home() / "ws" / "today" / "X0-DigitalIdentity" / "humble-idp"
_SINGINE_DIR = Path.home() / ".singine"


def _load_properties(path: Path) -> Dict[str, str]:
    cfg: Dict[str, str] = {}
    if not path.exists():
        return cfg
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            cfg[k.strip()] = v.strip()
    return cfg


def _load_idp_users(registry: Registry) -> None:
    """Merge humble-idp users.properties into registry (only if not already there)."""
    props = _load_properties(_HUMBLE_IDP_DIR / "config" / "users.properties")
    # collect usernames
    usernames = sorted({k.split(".")[0] for k in props if "." in k})
    for uname in usernames:
        if registry.resolve(uname) is not None:
            # already in built-in; enrich email if missing
            existing = registry.resolve(uname)
            if existing and not existing.email:
                existing.email = props.get(f"{uname}.email", "")
            continue
        aliases_raw = props.get(f"{uname}.aliases", "")
        aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
        person = Person(
            key=uname,
            display=uname.capitalize(),
            aliases=aliases,
            email=props.get(f"{uname}.email", ""),
            urn=props.get(f"{uname}.urn", ""),
        )
        registry.add(person)


def _load_user_file(registry: Registry) -> None:
    """Load ~/.singine/singe.people (JSON array of person objects)."""
    people_file = _SINGINE_DIR / "singe.people"
    if not people_file.exists():
        return
    try:
        raw = json.loads(people_file.read_text(encoding="utf-8"))
        for item in raw:
            person = Person(
                key=item["key"],
                display=item.get("display", item["key"]),
                aliases=item.get("aliases", []),
                email=item.get("email", ""),
                urn=item.get("urn", ""),
                note=item.get("note", ""),
            )
            # user file wins: overwrite existing key
            for k in person.all_keys():
                registry._index[k.lower()] = person
            registry._people.append(person)
    except Exception:
        pass


def build_registry() -> Registry:
    """Build the full people registry from all sources."""
    registry = Registry(_BUILTIN)
    _load_idp_users(registry)
    _load_user_file(registry)
    return registry


# ---------------------------------------------------------------------------
# Template engine
# ---------------------------------------------------------------------------

_MENTION_RE = re.compile(r"@([A-Za-z][\w-]{0,19})")


def render(template: str, registry: Optional[Registry] = None, fmt: str = "display") -> str:
    """
    Replace every ``@mention`` token in *template* with the person's name.

    fmt:
      "display"  — full display name  (default)
      "short"    — first name / key
      "email"    — email address (falls back to display if empty)
      "urn"      — URN (falls back to display if empty)
      "key"      — canonical registry key
    """
    if registry is None:
        registry = build_registry()

    def _replace(m: re.Match) -> str:
        token = m.group(1)
        person = registry.resolve(token)
        if person is None:
            return m.group(0)  # leave unchanged
        if fmt == "display":
            return person.display
        if fmt == "short":
            return person.short()
        if fmt == "email":
            return person.email or person.display
        if fmt == "urn":
            return person.urn or person.display
        if fmt == "key":
            return person.key
        return person.display

    return _MENTION_RE.sub(_replace, template)
