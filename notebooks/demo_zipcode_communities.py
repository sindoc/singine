"""
singine notebook demo — Zip code → Life phases → Communities → Multilingual output
===================================================================================

Run in any Python notebook (Databricks, Collibra, Jupyter, VS Code):

    %pip install singine          # Databricks / Collibra
    pip install -e /path/to/singine  # local

Then execute cells in order.

Architecture:
    XML source → RabbitMQ (raw) → RabbitMQ (staging) → Kafka stream → Lambda
    Each step logs a markdown fragment (git-tracked).
    All output is available as: Markdown / XML / JSON / MediaWiki / API call.

Messaging infrastructure (optional, degrades gracefully):
    docker compose -f docker/docker-compose.messaging.yml up -d
"""

# ── Cell 1: Import ────────────────────────────────────────────────────────────
# Works in Databricks, Collibra DGC notebook, Jupyter, VS Code Jupyter

import singine
from singine import notebook as nb

print(f"singine version: {singine.__version__ if hasattr(singine, '__version__') else '0.2.0'}")
print(f"Available: nb.lookup(), nb.demo(), nb.languages(), nb.life_phase_taxonomy()")


# ── Cell 2: Language catalogue ────────────────────────────────────────────────
# ISO 639-1 codes mapped to Wikidata URIs and Collibra codes

langs = nb.languages()
print(f"\nISO 639-1 languages registered: {len(langs)}")
for code, info in list(langs.items())[:6]:
    print(f"  [{code}] {info['name']:12s}  Wikidata: {info['wikidata']:8s}  Collibra: LANG-{code.upper()}")


# ── Cell 3: Life phase taxonomy ───────────────────────────────────────────────
# Demographic tendencies with Wikidata alignment

phases = nb.life_phase_taxonomy()
print(f"\nLife phase taxonomy ({len(phases)} phases):")
for key, info in phases.items():
    print(f"  {info['collibra']:14s}  {info['label']}")


# ── Cell 4: Community taxonomy ────────────────────────────────────────────────

communities = nb.community_taxonomy()
print(f"\nCommunity pattern taxonomy ({len(communities)} types):")
for key, info in communities.items():
    print(f"  {info['collibra']:14s}  {info['label']}")


# ── Cell 5: Single zip code lookup — Brussels Pentagon Centre ─────────────────

profile = nb.lookup("1000", country="BE")
profile.summary()


# ── Cell 6: Multilingual Wikipedia mapping ────────────────────────────────────

print("Wikipedia links (multilingual):")
for lang, url in profile.wikipedia_links().items():
    print(f"  [{lang}] {url}")

print(f"\nWikidata URI: {profile.wikidata_uri()}")

print("\nLanguage codes with Collibra and Wikidata:")
for lang in profile.languages():
    print(f"  [{lang['code']}] {lang['name']:12s}  {lang['collibra_code']:12s}  Wikidata: {lang['wikidata']}")


# ── Cell 7: Collibra codes ────────────────────────────────────────────────────

codes = profile.collibra_codes()
print("\nCollibra codes:")
for k, v in codes.items():
    print(f"  {k:20s} → {v}")


# ── Cell 8: Publication formats ───────────────────────────────────────────────

md = profile.to_markdown()
print("── Markdown ──")
print(md)

xml_out = profile.to_xml()
print("── XML ──")
print(xml_out)

mw = profile.to_mediawiki()
print("── MediaWiki ──")
print(mw)

js = profile.to_json()
print("── JSON ──")
print(js[:400], "...[truncated]")


# ── Cell 9: Send through messaging pipeline ───────────────────────────────────
# Degrades gracefully if RabbitMQ/Kafka are not running

raw_result = profile.send(stage="raw")
print(f"\nRabbitMQ raw:     {raw_result}")

staging_result = profile.send(stage="staging")
print(f"RabbitMQ staging: {staging_result}")

# To run the full pipeline (raw → staging → Kafka → Lambda):
# full_result = profile.send(full=True)


# ── Cell 10: Log to git ───────────────────────────────────────────────────────

frag_path = profile.log()
print(f"\nGit log fragment written: {frag_path}")

# To commit:
# profile.log(commit=True, message="demo session: 1000 Brussels")


# ── Cell 11: Register in Collibra (dry run) ───────────────────────────────────

reg = profile.register_in_collibra(dry_run=True)
print(f"\nCollibra dry-run registration: {reg['count']} assets")
for asset in reg["assets"]:
    print(f"  {asset['assetType']:20s}  {asset['collibraCode']:16s}  {asset['name']}")


# ── Cell 12: Schaerbeek — family forming + migrant entrepreneurial ────────────

schaerbeek = nb.lookup("1030", country="BE")
schaerbeek.summary()
print(schaerbeek.to_mediawiki())


# ── Cell 13: US zip code — New York ──────────────────────────────────────────

nyc = nb.lookup("10001", country="US")
nyc.summary()


# ── Cell 14: San Francisco — tech + creative ──────────────────────────────────

sf = nb.lookup("94103", country="US")
sf.summary()

print("Wikipedia:")
for lang, url in sf.wikipedia_links().items():
    print(f"  [{lang}] {url}")


# ── Cell 15: Full demo bundle ─────────────────────────────────────────────────
# All registered zip codes across BE, US, CA

bundle = nb.demo()
print(f"\nDemo bundle: {bundle}")
print(f"Profiles: {len(bundle.profiles)}")
for p in bundle.profiles:
    print(f"  {p.country:4s}  {p.zip_code:8s}  {p.municipality:30s}  {p.life_phases()['collibra_code']}")


# ── Cell 16: Render all to output directory ───────────────────────────────────
# Produces: *.md, *.xml, *.json, *.mediawiki, index.md

from pathlib import Path

output_dir = Path("/tmp/singine-demo-zipcode")
written = bundle.render_all(output_dir)

print(f"\nRendered to {output_dir}:")
for fmt, paths in written.items():
    print(f"  {fmt:10s}: {len(paths)} files")
print(f"  index:      {output_dir / 'index.md'}")


# ── Cell 17: Full messaging pipeline for bundle ───────────────────────────────
# Sends all profiles through RabbitMQ raw queue

send_results = bundle.send_all(stage="raw")
delivered = sum(1 for r in send_results if r.get("delivered"))
buffered  = sum(1 for r in send_results if r.get("buffered_locally"))
print(f"\nBatch send ({len(send_results)} messages):")
print(f"  Delivered to RabbitMQ: {delivered}")
print(f"  Buffered locally:      {buffered}")


# ── Cell 18: Pipeline status ──────────────────────────────────────────────────

status = nb.pipeline_status()
print(f"\nPipeline buffer: {len(status['buffer'])} messages")
if status["buffer"]:
    latest = status["buffer"][0]
    print(f"  Latest: stage={latest['stage']}  delivered={latest['delivered']}  at={latest['sent_at']}")

log_status = status["log"]
print(f"\nGit log:")
print(f"  Branch: {log_status['git_branch']}")
print(f"  Head:   {log_status['git_head'][:12]}...")
print(f"  Log dir: {log_status['log_dir']}")


# ── Cell 19: XML → JSON → API call — transformation protocol ─────────────────
# Demonstrates the markdown → xml → json → mediawiki → api call chain

import json
import xml.etree.ElementTree as ET

profile_1000 = nb.lookup("1000", country="BE")

# XML source
xml_src = profile_1000.to_xml()

# Parse XML → enrich → emit JSON
root = ET.fromstring(xml_src)
enriched = {
    "zip": root.attrib.get("zip-code"),
    "country": root.attrib.get("country"),
    "life_phase": root.findtext("life-phase/tendency"),
    "community_collibra": root.find("community").attrib.get("collibra") if root.find("community") is not None else None,
    "languages": [el.attrib.get("code") for el in root.findall("languages/language")],
    "wikipedia_urls": {el.attrib.get("lang"): el.text for el in root.findall("wikipedia/article")},
}

print("── XML → JSON transform ──")
print(json.dumps(enriched, indent=2, ensure_ascii=False))

# API call representation
api_call = (
    f"curl -X POST http://localhost:8090/invoke "
    f"-H 'Content-Type: application/json' "
    f"-d '{json.dumps({\"topic\": \"singine.datastreaming.zip.v1\", \"key\": \"1000\", \"payload\": enriched})}'"
)
print("\n── API call ──")
print(api_call)


# ── Cell 20: Full demo bundle write (with git logging) ────────────────────────
# Uses the existing write_zip_neighborhood_demo_bundle for messaging artefacts

from singine.zip_neighborhood_demo import write_zip_neighborhood_demo_bundle

bundle_dir = Path("/tmp/singine-messaging-bundle")
manifest = write_zip_neighborhood_demo_bundle(
    output_dir=bundle_dir,
    title="Zip Neighbourhood Community Demo — First Run",
    domain_db=Path("/tmp/humble-idp.db"),
    actor_id="notebook",
)

print(f"\nMessaging bundle written to: {bundle_dir}")
print(f"  demo_id:   {manifest['demo']['demo_id']}")
print(f"  kafka:     {manifest['demo']['topology']['kafka']['topic']}")
print(f"  lambda:    {manifest['demo']['topology']['lambda']['function_name']}")
print(f"  artefacts: {list(manifest['artifacts'].keys())}")

print("\nMarkdown publication:")
print(open(manifest["artifacts"]["markdown"]).read())
