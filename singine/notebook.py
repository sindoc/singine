"""singine notebook SDK.

The entry point for Collibra notebooks, Databricks notebooks, and Jupyter.

    import singine
    from singine import notebook as nb

    # Look up a zip code
    profile = nb.lookup("10001")                     # US
    profile = nb.lookup("1000", country="BE")        # Brussels
    profile = nb.lookup("1030", country="BE", langs=["en", "fr", "nl", "ar"])

    # Explore
    profile.summary()                    # print human-readable overview
    profile.life_phases()                # list life phase tendencies
    profile.communities()                # community pattern codes
    profile.wikipedia_links()            # per-language Wikipedia article titles

    # Publish
    md  = profile.to_markdown()
    xml = profile.to_xml()
    js  = profile.to_json()
    mw  = profile.to_mediawiki()

    # Send through messaging pipeline
    result = profile.send()              # raw → staging → Kafka → Lambda
    result = profile.send(stage="raw")  # raw only

    # Log to git
    profile.log()
    profile.log(commit=True, message="session: zip community analysis")

    # Collibra catalog integration
    profile.collibra_codes()             # dict of Collibra asset codes
    profile.register_in_collibra()       # POST to Collibra REST API

    # Full demo bundle (multiple zip codes)
    demo = nb.demo()
    demo = nb.demo(zip_codes=["1000", "1030", "1060"], country="BE")
    demo.render_all(output_dir=Path("./output"))

Databricks / Collibra notebook:

    %pip install singine
    import singine
    from singine import notebook as nb
    profile = nb.lookup("1000", country="BE")
    display(profile.to_json())
"""

from __future__ import annotations

import json
import os
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gitlog import GitLog, record as _gitlog_record
from .pipeline import Pipeline, publish as _pipeline_publish
from .zip_neighborhood_demo import (
    DEMO_ROWS,
    render_markdown as _render_markdown,
    render_mediawiki as _render_mediawiki,
    render_xml as _render_xml,
    write_zip_neighborhood_demo_bundle,
)


# ── Language catalogue (ISO 639-1 → display name + Wikidata code) ────────────

ISO_LANGUAGES: Dict[str, Dict[str, str]] = {
    "en":  {"name": "English",    "wikidata": "Q1860",  "wikipedia_prefix": "en"},
    "fr":  {"name": "French",     "wikidata": "Q150",   "wikipedia_prefix": "fr"},
    "nl":  {"name": "Dutch",      "wikidata": "Q7411",  "wikipedia_prefix": "nl"},
    "de":  {"name": "German",     "wikidata": "Q188",   "wikipedia_prefix": "de"},
    "ar":  {"name": "Arabic",     "wikidata": "Q13955", "wikipedia_prefix": "ar"},
    "es":  {"name": "Spanish",    "wikidata": "Q1321",  "wikipedia_prefix": "es"},
    "pt":  {"name": "Portuguese", "wikidata": "Q5146",  "wikipedia_prefix": "pt"},
    "it":  {"name": "Italian",    "wikidata": "Q652",   "wikipedia_prefix": "it"},
    "pl":  {"name": "Polish",     "wikidata": "Q809",   "wikipedia_prefix": "pl"},
    "tr":  {"name": "Turkish",    "wikidata": "Q256",   "wikipedia_prefix": "tr"},
    "fa":  {"name": "Persian",    "wikidata": "Q9168",  "wikipedia_prefix": "fa"},
    "ru":  {"name": "Russian",    "wikidata": "Q7737",  "wikipedia_prefix": "ru"},
    "zh":  {"name": "Chinese",    "wikidata": "Q7850",  "wikipedia_prefix": "zh"},
    "ja":  {"name": "Japanese",   "wikidata": "Q5287",  "wikipedia_prefix": "ja"},
}

# Life phase taxonomy with Collibra codes and Wikidata mappings
LIFE_PHASES: Dict[str, Dict[str, str]] = {
    "early-career-student":      {"collibra": "LIFE-EARLY",    "wikidata": "Q215439", "label": "Young adults & students (18–30)"},
    "family-forming":            {"collibra": "LIFE-FAMILY",   "wikidata": "Q131257", "label": "Family formation (25–40)"},
    "established-family":        {"collibra": "LIFE-ESTAB",    "wikidata": "Q131257", "label": "Established families (35–55)"},
    "active-midlife":            {"collibra": "LIFE-MIDLIFE",  "wikidata": "Q21198",  "label": "Active midlife (45–60)"},
    "pre-retirement":            {"collibra": "LIFE-PRERET",   "wikidata": "Q1337660","label": "Pre-retirement (55–67)"},
    "active-senior":             {"collibra": "LIFE-SENIOR",   "wikidata": "Q130834", "label": "Active seniors (65–80)"},
    "creative-professional":     {"collibra": "LIFE-CREATIVE", "wikidata": "Q214536", "label": "Creative professionals (25–55)"},
    "migrant-entrepreneurial":   {"collibra": "LIFE-MIGRANT",  "wikidata": "Q8461",   "label": "Migrant & entrepreneurial (all ages)"},
    "mixed-aging":               {"collibra": "LIFE-MIXED",    "wikidata": "Q21198",  "label": "Mixed aging (35–65)"},
}

# Community pattern taxonomy
COMMUNITY_PATTERNS: Dict[str, Dict[str, str]] = {
    "civic-institutional":   {"collibra": "COMM-CIVIC",    "wikidata": "Q189553", "label": "Civic institutions & government"},
    "creative-cultural":     {"collibra": "COMM-CULTURE",  "wikidata": "Q8 10912","label": "Arts, culture & nightlife"},
    "family-suburban":       {"collibra": "COMM-SUBURB",   "wikidata": "Q748110", "label": "Suburban family services"},
    "migrant-commercial":    {"collibra": "COMM-MIGRANT",  "wikidata": "Q1497648","label": "Diaspora commerce & associations"},
    "tech-innovation":       {"collibra": "COMM-TECH",     "wikidata": "Q1127788","label": "Tech & innovation hubs"},
    "health-services":       {"collibra": "COMM-HEALTH",   "wikidata": "Q31207",  "label": "Healthcare & medical services"},
    "academic-research":     {"collibra": "COMM-ACADEMIC", "wikidata": "Q3918",   "label": "Academic & research clusters"},
    "industrial-legacy":     {"collibra": "COMM-INDUSTRY", "wikidata": "Q35958",  "label": "Industrial legacy neighbourhoods"},
    "school-commerce":       {"collibra": "COMM-SCHOOL",   "wikidata": "Q748110", "label": "Schools, small commerce & services"},
}

# Extended zip code registry
_ZIP_REGISTRY: Dict[str, Dict[str, Any]] = {}
for _row in DEMO_ROWS:
    _ZIP_REGISTRY[f"{_row['country_code']}-{_row['zip_code']}"] = _row


# Additional zip codes to extend the demo
_EXTRA_ROWS: List[Dict[str, Any]] = [
    {
        "zip_code": "1050",
        "country_code": "BE",
        "municipality": "Ixelles / Elsene",
        "neighborhood": "Place Flagey",
        "life_phase_tendency": "creative-professional",
        "community_pattern": "arts venues, cafés, international community, and cycle infrastructure",
        "languages": ["en", "fr", "nl", "es", "ar"],
        "wikidata": "Q221094",
        "wikipedia": {
            "en": "Ixelles",
            "fr": "Ixelles",
            "nl": "Elsene",
            "es": "Ixelles",
        },
        "collibra_codes": {
            "zip": "ZIP-BE-1050",
            "life_phase": "LIFE-CREATIVE",
            "community": "COMM-CULTURE",
        },
    },
    {
        "zip_code": "1090",
        "country_code": "BE",
        "municipality": "Jette",
        "neighborhood": "Jette Centre",
        "life_phase_tendency": "established-family",
        "community_pattern": "residential suburbs, health services, and French-speaking community",
        "languages": ["fr", "nl", "en"],
        "wikidata": "Q188869",
        "wikipedia": {
            "en": "Jette,_Brussels",
            "fr": "Jette_(Bruxelles)",
            "nl": "Jette_(Brussel)",
        },
        "collibra_codes": {
            "zip": "ZIP-BE-1090",
            "life_phase": "LIFE-ESTAB",
            "community": "COMM-HEALTH",
        },
    },
    {
        "zip_code": "1210",
        "country_code": "BE",
        "municipality": "Saint-Josse-ten-Noode",
        "neighborhood": "Botanique",
        "life_phase_tendency": "migrant-entrepreneurial",
        "community_pattern": "Turkish and North African commerce, dense housing, transit hub",
        "languages": ["fr", "tr", "ar", "nl", "en"],
        "wikidata": "Q257008",
        "wikipedia": {
            "en": "Saint-Josse-ten-Noode",
            "fr": "Saint-Josse-ten-Noode",
            "nl": "Sint-Joost-ten-Node",
            "tr": "Saint-Josse-ten-Noode",
        },
        "collibra_codes": {
            "zip": "ZIP-BE-1210",
            "life_phase": "LIFE-MIGRANT",
            "community": "COMM-MIGRANT",
        },
    },
    {
        "zip_code": "10001",
        "country_code": "US",
        "municipality": "New York",
        "neighborhood": "Midtown Manhattan / Hudson Yards",
        "life_phase_tendency": "early-career-student",
        "community_pattern": "finance, tech, high-density commuter, international professionals",
        "languages": ["en", "es", "zh", "fr", "ar"],
        "wikidata": "Q60",
        "wikipedia": {
            "en": "New_York_City",
            "es": "Ciudad_de_Nueva_York",
            "fr": "New_York",
            "zh": "纽约",
            "ar": "مدينة_نيويورك",
        },
        "collibra_codes": {
            "zip": "ZIP-US-10001",
            "life_phase": "LIFE-EARLY",
            "community": "COMM-TECH",
        },
    },
    {
        "zip_code": "94103",
        "country_code": "US",
        "municipality": "San Francisco",
        "neighborhood": "SoMa / Tenderloin",
        "life_phase_tendency": "creative-professional",
        "community_pattern": "tech startups, arts, LGBTQ+ community, social services, housing diversity",
        "languages": ["en", "es", "zh", "fa", "ar"],
        "wikidata": "Q62",
        "wikipedia": {
            "en": "San_Francisco",
            "es": "San_Francisco_(California)",
            "zh": "旧金山",
            "fa": "سان_فرانسیسکو",
        },
        "collibra_codes": {
            "zip": "ZIP-US-94103",
            "life_phase": "LIFE-CREATIVE",
            "community": "COMM-TECH",
        },
    },
    {
        "zip_code": "M5V",
        "country_code": "CA",
        "municipality": "Toronto",
        "neighborhood": "Entertainment District / King West",
        "life_phase_tendency": "early-career-student",
        "community_pattern": "condos, finance, nightlife, multicultural young professionals",
        "languages": ["en", "fr", "zh", "ar", "pt"],
        "wikidata": "Q172",
        "wikipedia": {
            "en": "Toronto",
            "fr": "Toronto",
            "zh": "多伦多",
            "ar": "تورنتو",
        },
        "collibra_codes": {
            "zip": "ZIP-CA-M5V",
            "life_phase": "LIFE-EARLY",
            "community": "COMM-CULTURE",
        },
    },
]

for _row in _EXTRA_ROWS:
    _ZIP_REGISTRY[f"{_row['country_code']}-{_row['zip_code']}"] = _row


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── ZipProfile ────────────────────────────────────────────────────────────────

class ZipProfile:
    """Enriched zip code profile with messaging, publication, and git logging."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = deepcopy(data)
        self._pipeline: Optional[Pipeline] = None
        self._log: Optional[GitLog] = None

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def zip_code(self) -> str:
        return self._data.get("zip_code", "")

    @property
    def country(self) -> str:
        return self._data.get("country_code", "")

    @property
    def municipality(self) -> str:
        return self._data.get("municipality", "")

    @property
    def neighborhood(self) -> str:
        return self._data.get("neighborhood", "")

    def life_phases(self) -> Dict[str, str]:
        lp = self._data.get("life_phase_tendency", "")
        info = LIFE_PHASES.get(lp, {})
        return {
            "tendency": lp,
            "collibra_code": info.get("collibra", f"LIFE-{lp[:8].upper()}"),
            "wikidata": info.get("wikidata", ""),
            "label": info.get("label", lp),
        }

    def communities(self) -> Dict[str, str]:
        # Extract pattern key from free-form description
        pat = self._data.get("community_pattern", "")
        codes = self._data.get("collibra_codes", {})
        comm_code = codes.get("community", "COMM-UNKNOWN")
        # Map back to taxonomy
        entry = next(
            (v for v in COMMUNITY_PATTERNS.values() if v["collibra"] == comm_code),
            {"label": pat, "wikidata": ""},
        )
        return {
            "pattern": pat,
            "collibra_code": comm_code,
            "wikidata": entry.get("wikidata", ""),
            "label": entry.get("label", pat),
        }

    def wikipedia_links(self) -> Dict[str, str]:
        wiki = self._data.get("wikipedia", {})
        return {
            lang: f"https://{lang}.wikipedia.org/wiki/{title}"
            for lang, title in wiki.items()
        }

    def wikidata_uri(self) -> str:
        qcode = self._data.get("wikidata", "")
        return f"https://www.wikidata.org/wiki/{qcode}" if qcode else ""

    def languages(self) -> List[Dict[str, str]]:
        return [
            {
                "code": code,
                **ISO_LANGUAGES.get(code, {"name": code, "wikidata": "", "wikipedia_prefix": code}),
                "collibra_code": f"LANG-{code.upper()}",
            }
            for code in self._data.get("languages", [])
        ]

    def collibra_codes(self) -> Dict[str, str]:
        codes = deepcopy(self._data.get("collibra_codes", {}))
        for lang in self._data.get("languages", []):
            codes[f"lang_{lang}"] = f"LANG-{lang.upper()}"
        return codes

    # ── Summary ───────────────────────────────────────────────────────────────

    def summary(self) -> None:
        lp = self.life_phases()
        comm = self.communities()
        langs = self.languages()
        wiki = self.wikipedia_links()

        print(f"\n{'═'*60}")
        print(f"  {self.zip_code}  {self.municipality} / {self.neighborhood}")
        print(f"  Country: {self.country}")
        print(f"{'─'*60}")
        print(f"  Life phase:  {lp['label']}")
        print(f"               {lp['collibra_code']}  Wikidata: {lp['wikidata']}")
        print(f"  Community:   {comm['label']}")
        print(f"               {comm['collibra_code']}  Wikidata: {comm['wikidata']}")
        print(f"{'─'*60}")
        print(f"  Languages ({len(langs)}):")
        for lang in langs:
            print(f"    [{lang['code']}] {lang['name']:12s}  {lang['collibra_code']}  Wikidata: {lang['wikidata']}")
        if wiki:
            print(f"{'─'*60}")
            print(f"  Wikipedia:")
            for lang, url in wiki.items():
                print(f"    {lang}: {url}")
        if self.wikidata_uri():
            print(f"  Wikidata: {self.wikidata_uri()}")
        print(f"{'═'*60}\n")

    # ── Publication ───────────────────────────────────────────────────────────

    def _envelope(self) -> Dict[str, Any]:
        """Wrap into the demo envelope format for renderers."""
        from .zip_neighborhood_demo import _message_topology, _row_payload, _slug
        slug = f"nb-{_slug(self.zip_code)}"
        topology = _message_topology(slug)
        row = _row_payload(self._data)
        return {
            "demo_id": slug,
            "title": f"{self.zip_code} {self.municipality}",
            "generated_at": _now(),
            "topology": topology,
            "datasets": [row],
            "messages": {"raw": [], "staging": [], "kafka": []},
        }

    def to_markdown(self) -> str:
        lp = self.life_phases()
        comm = self.communities()
        langs = self.languages()
        wiki = self.wikipedia_links()
        lines = [
            f"# {self.zip_code} {self.municipality} / {self.neighborhood}",
            "",
            f"- zip-code:: {self.zip_code}",
            f"- country:: {self.country}",
            f"- life-phase:: {lp['tendency']}",
            f"- life-phase-label:: {lp['label']}",
            f"- life-phase-collibra:: {lp['collibra_code']}",
            f"- community-pattern:: {comm['pattern']}",
            f"- community-collibra:: {comm['collibra_code']}",
            f"- wikidata:: {self.wikidata_uri()}",
            "",
            "## Languages",
            "",
        ]
        for lang in langs:
            lines.append(f"- [{lang['code']}] {lang['name']} — {lang['collibra_code']} — Wikidata {lang['wikidata']}")
        lines.append("")
        if wiki:
            lines.append("## Wikipedia")
            lines.append("")
            for lang, url in wiki.items():
                lines.append(f"- [{lang}] {url}")
        return "\n".join(lines).strip() + "\n"

    def to_xml(self) -> str:
        root = ET.Element("zip-profile", {
            "zip-code": self.zip_code,
            "country": self.country,
        })
        ET.SubElement(root, "municipality").text = self.municipality
        ET.SubElement(root, "neighborhood").text = self.neighborhood
        ET.SubElement(root, "wikidata-uri").text = self.wikidata_uri()

        lp = self.life_phases()
        lp_el = ET.SubElement(root, "life-phase", {"collibra": lp["collibra_code"], "wikidata": lp["wikidata"]})
        ET.SubElement(lp_el, "tendency").text = lp["tendency"]
        ET.SubElement(lp_el, "label").text = lp["label"]

        comm = self.communities()
        comm_el = ET.SubElement(root, "community", {"collibra": comm["collibra_code"], "wikidata": comm["wikidata"]})
        ET.SubElement(comm_el, "label").text = comm["label"]
        ET.SubElement(comm_el, "pattern").text = comm["pattern"]

        langs_el = ET.SubElement(root, "languages")
        for lang in self.languages():
            ET.SubElement(langs_el, "language", {
                "code": lang["code"],
                "collibra": lang["collibra_code"],
                "wikidata": lang.get("wikidata", ""),
            }).text = lang["name"]

        wiki_el = ET.SubElement(root, "wikipedia")
        for lang, url in self.wikipedia_links().items():
            ET.SubElement(wiki_el, "article", {"lang": lang}).text = url

        return ET.tostring(root, encoding="unicode", xml_declaration=False)

    def to_json(self) -> str:
        return json.dumps({
            "zip_code": self.zip_code,
            "country": self.country,
            "municipality": self.municipality,
            "neighborhood": self.neighborhood,
            "life_phase": self.life_phases(),
            "community": self.communities(),
            "languages": self.languages(),
            "wikipedia": self.wikipedia_links(),
            "wikidata_uri": self.wikidata_uri(),
            "collibra_codes": self.collibra_codes(),
            "generated_at": _now(),
        }, indent=2, ensure_ascii=False)

    def to_mediawiki(self) -> str:
        lp = self.life_phases()
        comm = self.communities()
        langs = self.languages()
        wiki = self.wikipedia_links()
        lines = [
            f"= {self.zip_code} {self.municipality} / {self.neighborhood} =",
            "",
            f"; Zip code: {self.zip_code}",
            f"; Country: {self.country}",
            f"; Life phase: [[{lp['wikidata']}|{lp['label']}]] ({lp['collibra_code']})",
            f"; Community: [[{comm['wikidata']}|{comm['label']}]] ({comm['collibra_code']})",
            f"; Wikidata: [{self.wikidata_uri()}]",
            "",
            "== Languages ==",
            "",
        ]
        for lang in langs:
            lines.append(f"* [[wikidata:{lang['wikidata']}|{lang['name']}]] — <code>{lang['code']}</code> — {lang['collibra_code']}")
        lines.append("")
        if wiki:
            lines.append("== Wikipedia articles ==")
            lines.append("")
            for lang, url in wiki.items():
                lines.append(f"* [{url} {lang.upper()}]")
        return "\n".join(lines).strip() + "\n"

    # ── Messaging ─────────────────────────────────────────────────────────────

    def _get_pipeline(self) -> Pipeline:
        if self._pipeline is None:
            self._pipeline = Pipeline()
        return self._pipeline

    def send(self, *, stage: str = "raw", full: bool = False) -> Dict[str, Any]:
        """Send this profile through the messaging pipeline."""
        p = self._get_pipeline()
        payload = json.loads(self.to_json())
        if full:
            return p.publish(payload, key=self.zip_code)
        return p.send(payload, stage=stage)

    # ── Git log ───────────────────────────────────────────────────────────────

    def _get_log(self) -> GitLog:
        if self._log is None:
            self._log = GitLog()
        return self._log

    def log(self, *, commit: bool = False, message: str = "") -> Path:
        """Record this profile lookup to the git log."""
        gl = self._get_log()
        frag = gl.record(
            "ZIP_PROFILE_LOOKUP",
            json.loads(self.to_json()),
            subject_id=f"{self.country}-{self.zip_code}",
            note=f"{self.zip_code} {self.municipality}",
        )
        if commit:
            gl.commit(message or f"singine notebook: {self.zip_code} {self.municipality}")
        return frag

    # ── Collibra ──────────────────────────────────────────────────────────────

    def register_in_collibra(self, *, dry_run: bool = True) -> Dict[str, Any]:
        """Register zip profile assets in Collibra catalog (dry_run by default)."""
        codes = self.collibra_codes()
        assets = [
            {"assetType": "DATA_ASSET", "name": f"Zip {self.zip_code}", "collibraCode": codes.get("zip", "")},
            {"assetType": "BUSINESS_TERM", "name": self.life_phases()["label"], "collibraCode": codes.get("life_phase", "")},
            {"assetType": "BUSINESS_TERM", "name": self.communities()["label"], "collibraCode": codes.get("community", "")},
        ]
        for lang in self.languages():
            assets.append({"assetType": "REFERENCE_DATA", "name": lang["name"], "collibraCode": lang["collibra_code"]})

        self._get_log().record(
            "COLLIBRA_REGISTRATION",
            {"zip": self.zip_code, "assets": assets, "dry_run": dry_run},
            subject_id=f"{self.country}-{self.zip_code}",
        )
        return {"dry_run": dry_run, "assets": assets, "count": len(assets)}

    def __repr__(self) -> str:
        return f"ZipProfile({self.country}-{self.zip_code}: {self.municipality}/{self.neighborhood})"


# ── Demo bundle ───────────────────────────────────────────────────────────────

class DemoBundle:
    """Collection of ZipProfiles with batch publication."""

    def __init__(self, profiles: List[ZipProfile]) -> None:
        self.profiles = profiles

    def render_all(
        self,
        output_dir: Path,
        *,
        formats: Optional[List[str]] = None,
    ) -> Dict[str, List[Path]]:
        formats = formats or ["markdown", "xml", "json", "mediawiki"]
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        written: Dict[str, List[Path]] = {f: [] for f in formats}

        for profile in self.profiles:
            slug = f"{profile.country.lower()}-{profile.zip_code}"
            if "markdown" in formats:
                p = output_dir / f"{slug}.md"
                p.write_text(profile.to_markdown(), encoding="utf-8")
                written["markdown"].append(p)
            if "xml" in formats:
                p = output_dir / f"{slug}.xml"
                p.write_text(profile.to_xml(), encoding="utf-8")
                written["xml"].append(p)
            if "json" in formats:
                p = output_dir / f"{slug}.json"
                p.write_text(profile.to_json(), encoding="utf-8")
                written["json"].append(p)
            if "mediawiki" in formats:
                p = output_dir / f"{slug}.mediawiki"
                p.write_text(profile.to_mediawiki(), encoding="utf-8")
                written["mediawiki"].append(p)

        # Write combined index
        index_md = output_dir / "index.md"
        index_lines = ["# singine Zip Community Demo", "", f"Generated: {_now()}", ""]
        for profile in self.profiles:
            index_lines.append(f"- [{profile.zip_code} {profile.municipality}]({profile.country.lower()}-{profile.zip_code}.md)")
        index_md.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
        return written

    def send_all(self, *, stage: str = "raw") -> List[Dict[str, Any]]:
        p = Pipeline()
        results = []
        for profile in self.profiles:
            payload = json.loads(profile.to_json())
            results.append(p.send(payload, stage=stage))
        return results

    def to_json(self) -> str:
        return json.dumps(
            {"profiles": [json.loads(p.to_json()) for p in self.profiles]},
            indent=2,
            ensure_ascii=False,
        )

    def __repr__(self) -> str:
        return f"DemoBundle({len(self.profiles)} profiles)"


# ── Public API ────────────────────────────────────────────────────────────────

def lookup(zip_code: str, *, country: str = "BE", langs: Optional[List[str]] = None) -> ZipProfile:
    """Look up a zip code and return a ZipProfile.

    Falls back to a synthetic profile if the zip code is not in the registry.
    """
    key = f"{country.upper()}-{zip_code}"
    data = deepcopy(_ZIP_REGISTRY.get(key))
    if data is None:
        # Synthetic fallback
        data = {
            "zip_code": zip_code,
            "country_code": country.upper(),
            "municipality": f"{country.upper()} {zip_code}",
            "neighborhood": "Unknown",
            "life_phase_tendency": "mixed-aging",
            "community_pattern": "mixed urban area",
            "languages": langs or ["en"],
            "wikidata": "",
            "wikipedia": {},
            "collibra_codes": {
                "zip": f"ZIP-{country.upper()}-{zip_code}",
                "life_phase": "LIFE-MIXED",
                "community": "COMM-CIVIC",
            },
        }
    if langs:
        data["languages"] = langs
    profile = ZipProfile(data)
    _gitlog_record(
        "ZIP_LOOKUP",
        {"zip_code": zip_code, "country": country, "found": key in _ZIP_REGISTRY},
    )
    return profile


def demo(
    zip_codes: Optional[List[str]] = None,
    *,
    country: str = "BE",
) -> DemoBundle:
    """Return a DemoBundle for multiple zip codes."""
    if zip_codes is None:
        # Default demo set: Brussels + US
        profiles = [ZipProfile(deepcopy(row)) for row in (DEMO_ROWS + _EXTRA_ROWS)]
    else:
        profiles = [lookup(z, country=country) for z in zip_codes]
    return DemoBundle(profiles)


def pipeline_status() -> Dict[str, Any]:
    """Return the current state of the local pipeline buffer."""
    p = Pipeline()
    return {"buffer": p.buffer_summary(), "log": GitLog().status()}


def languages() -> Dict[str, Dict[str, str]]:
    """Return the full ISO 639-1 language catalogue with Wikidata codes."""
    return deepcopy(ISO_LANGUAGES)


def life_phase_taxonomy() -> Dict[str, Dict[str, str]]:
    """Return the full life phase taxonomy with Collibra codes."""
    return deepcopy(LIFE_PHASES)


def community_taxonomy() -> Dict[str, Dict[str, str]]:
    """Return the full community pattern taxonomy with Collibra codes."""
    return deepcopy(COMMUNITY_PATTERNS)
