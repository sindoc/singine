#!/usr/bin/env python3
"""
Compile the Singine XML system diagram into a self-contained interactive HTML file.

Source of truth:
  - singine-system-diagram.xml
Schema for editing:
  - singine-system-diagram.rnc

Output:
  - singine-system-diagram.html
"""

from __future__ import annotations

import html
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def norm(text: str | None) -> str:
    if text is None:
        return ""
    return " ".join(text.split())


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def parse_component(elem: ET.Element) -> dict:
    return {
        "id": elem.attrib["id"],
        "label": elem.attrib["label"],
        "layer": elem.attrib["layer"],
        "defaultOpen": elem.attrib.get("default-open", "false") == "true",
        "summary": norm(elem.findtext("summary")),
        "details": norm(elem.findtext("details")),
        "interfaces": [
            {
                "name": child.attrib["name"],
                "direction": child.attrib["direction"],
                "protocol": child.attrib["protocol"],
                "trust": child.attrib["trust"],
                "summary": norm(child.text),
            }
            for child in elem.findall("interface")
        ],
        "capabilityRefs": [child.attrib["ref"] for child in elem.findall("capability-ref")],
        "children": [parse_component(child) for child in elem.findall("component")],
    }


def parse_xml(source: Path) -> dict:
    root = ET.parse(source).getroot()

    capabilities = [
        {
            "id": elem.attrib["id"],
            "label": elem.attrib["label"],
            "exposure": elem.attrib["exposure"],
            "description": norm(elem.text),
        }
        for elem in root.find("capability-definitions").findall("capability")
    ]

    profiles = [
        {
            "id": elem.attrib["id"],
            "label": elem.attrib["label"],
            "class": elem.attrib["class"],
            "summary": norm(elem.findtext("summary")),
            "components": [parse_component(child) for child in elem.findall("component")],
        }
        for elem in root.find("profiles").findall("profile")
    ]

    deployment_elem = root.find("deployment")
    deployment = {
        "id": deployment_elem.attrib.get("id", ""),
        "label": deployment_elem.attrib["label"],
        "summary": norm(deployment_elem.findtext("summary")),
        "zones": [
            {
                "id": elem.attrib["id"],
                "label": elem.attrib["label"],
                "description": norm(elem.text),
            }
            for elem in deployment_elem.findall("trust-zone")
        ],
        "nodes": [
            {
                "id": elem.attrib["id"],
                "label": elem.attrib["label"],
                "profileRef": elem.attrib["profile-ref"],
                "zoneRef": elem.attrib["zone-ref"],
                "platform": elem.attrib["platform"],
                "summary": norm(elem.findtext("summary")),
                "broadcasts": [
                    {
                        "capabilityRef": child.attrib["capability-ref"],
                        "audience": child.attrib["audience"],
                        "channel": child.attrib["channel"],
                        "cadence": child.attrib["cadence"],
                        "summary": norm(child.text),
                    }
                    for child in elem.findall("broadcast")
                ],
            }
            for elem in deployment_elem.findall("node")
        ],
        "links": [
            {
                "from": elem.attrib["from"],
                "to": elem.attrib["to"],
                "kind": elem.attrib["kind"],
                "label": elem.attrib["label"],
                "trust": elem.attrib["trust"],
            }
            for elem in deployment_elem.findall("link")
        ],
    }

    return {
        "title": root.attrib["title"],
        "subtitle": norm(root.findtext("subtitle")),
        "capabilities": capabilities,
        "profiles": profiles,
        "deployment": deployment,
    }


def render_capability_pill(capability: dict) -> str:
    return (
        f'<div class="capability-pill">{esc(capability["label"])}'
        f' <span>{esc(capability["exposure"])}</span></div>'
    )


def render_component(component: dict, capability_map: dict[str, dict], depth: int = 0) -> str:
    classes = "component"
    if depth > 0:
        classes += " nested"
    open_attr = " open" if component["defaultOpen"] else ""

    interfaces = ""
    if component["interfaces"]:
        items = []
        for item in component["interfaces"]:
            items.append(
                "<div class=\"interface-pill\">"
                f"<strong>{esc(item['name'])}</strong>"
                f"<span>{esc(item['protocol'])} · {esc(item['direction'])} · {esc(item['trust'])}</span>"
                f"<p>{esc(item['summary'])}</p>"
                "</div>"
            )
        interfaces = (
            '<section class="component-block"><h5>Interfaces</h5>'
            f'<div class="interface-list">{"".join(items)}</div></section>'
        )

    capabilities = ""
    if component["capabilityRefs"]:
        items = []
        for ref in component["capabilityRefs"]:
            label = capability_map.get(ref, {}).get("label", ref)
            items.append(f'<div class="component-cap">{esc(label)}</div>')
        capabilities = (
            '<section class="component-block"><h5>Capabilities</h5>'
            f'<div class="component-cap-list">{"".join(items)}</div></section>'
        )

    children = ""
    if component["children"]:
        children = (
            '<section class="component-block"><h5>Subcomponents</h5>'
            f'{"".join(render_component(child, capability_map, depth + 1) for child in component["children"])}'
            "</section>"
        )

    details = (
        f'<p class="component-details">{esc(component["details"])}</p>'
        if component["details"]
        else ""
    )

    return (
        f'<details class="{classes}" data-collapsible="component"{open_attr}>'
        "<summary>"
        f'<div class="component-layer">{esc(component["layer"])}</div>'
        f'<h4>{esc(component["label"])}</h4>'
        f'<p class="component-summary">{esc(component["summary"])}</p>'
        "</summary>"
        '<div class="component-body">'
        f"{details}{interfaces}{capabilities}{children}"
        "</div>"
        "</details>"
    )


def render_node(node: dict, profile: dict, zone: dict, capability_map: dict[str, dict], open_by_default: bool) -> str:
    open_attr = " open" if open_by_default else ""

    broadcasts = []
    for item in node["broadcasts"]:
        capability = capability_map.get(item["capabilityRef"], {"label": item["capabilityRef"]})
        broadcasts.append(
            '<div class="broadcast-item">'
            f'<strong>{esc(capability["label"])}</strong>'
            f'<div class="broadcast-meta">{esc(item["channel"])} · {esc(item["audience"])} · {esc(item["cadence"])}</div>'
            f'<p>{esc(item["summary"])}</p>'
            "</div>"
        )

    components = "".join(render_component(component, capability_map) for component in profile["components"])

    return (
        f'<details class="node-card" data-collapsible="node"{open_attr}>'
        "<summary>"
        '<div class="node-topline">'
        f'<h3 class="node-title">{esc(node["label"])}</h3>'
        '<div class="badge-row">'
        f'<span class="badge accent">{esc(profile["class"])}</span>'
        f'<span class="badge">{esc(zone["label"])}</span>'
        "</div>"
        "</div>"
        '<div class="badge-row">'
        f'<span class="badge">{esc(node["platform"])}</span>'
        f'<span class="badge">{esc(profile["label"])}</span>'
        "</div>"
        f'<p class="node-summary">{esc(node["summary"])}</p>'
        "</summary>"
        '<div class="node-body">'
        '<section class="node-section">'
        "<h4>Broadcasts</h4>"
        f'{"".join(broadcasts)}'
        "</section>"
        '<section class="node-section">'
        "<h4>Profile components</h4>"
        f'<div class="component-tree">{components}</div>'
        "</section>"
        "</div>"
        "</details>"
    )


def build_html(data: dict) -> str:
    capability_map = {cap["id"]: cap for cap in data["capabilities"]}
    profile_map = {profile["id"]: profile for profile in data["profiles"]}
    zone_map = {zone["id"]: zone for zone in data["deployment"]["zones"]}

    capability_strip = "".join(render_capability_pill(cap) for cap in data["capabilities"])

    zone_cards = "".join(
        '<div class="zone-card">'
        f'<strong>{esc(zone["label"])}</strong>'
        f'<span>{esc(zone["description"])}</span>'
        "</div>"
        for zone in data["deployment"]["zones"]
    )

    link_cards = "".join(
        '<div class="link-card">'
        f'<strong>{esc(link["label"])}</strong>'
        f'<span>{esc(link["from"])} → {esc(link["to"])} · {esc(link["kind"])} · {esc(link["trust"])}</span>'
        "</div>"
        for link in data["deployment"]["links"]
    )

    capability_cards = "".join(
        '<div class="zone-card">'
        f'<strong>{esc(cap["label"])}</strong>'
        f'<span>{esc(cap["description"])} Exposure: {esc(cap["exposure"])}.</span>'
        "</div>"
        for cap in data["capabilities"]
    )

    node_cards = "".join(
        render_node(
            node,
            profile_map[node["profileRef"]],
            zone_map[node["zoneRef"]],
            capability_map,
            open_by_default=index == 0,
        )
        for index, node in enumerate(data["deployment"]["nodes"])
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(data["title"])}</title>
  <style>
    :root {{
      --bg: #f4efe8;
      --panel: rgba(255, 252, 247, 0.84);
      --panel-strong: #fffaf3;
      --ink: #1d1917;
      --muted: #655a4e;
      --line: #d7c8b7;
      --accent: #8d3526;
      --accent-soft: rgba(141, 53, 38, 0.12);
      --good: #244b3d;
      --shadow: 0 18px 40px rgba(77, 54, 36, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(255,255,255,0.75), transparent 28%),
        radial-gradient(circle at bottom left, rgba(229,218,199,0.85), transparent 22%),
        linear-gradient(135deg, #f7f2eb 0%, #efe7db 52%, #e7dccd 100%);
    }}
    .page {{
      max-width: 1580px;
      margin: 0 auto;
      padding: 32px 24px 48px;
    }}
    .hero {{
      display: grid;
      grid-template-columns: 1.2fr 0.8fr;
      gap: 18px;
      margin-bottom: 24px;
    }}
    .hero-card, .panel, .node-card {{
      background: var(--panel);
      border: 1px solid rgba(124, 96, 70, 0.16);
      border-radius: 32px;
      box-shadow: var(--shadow);
    }}
    .hero-card {{
      padding: 28px 30px 26px;
    }}
    .eyebrow {{
      margin: 0 0 10px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.18em;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(42px, 7vw, 76px);
      line-height: 0.95;
      letter-spacing: -0.05em;
    }}
    .subtitle {{
      margin: 0 0 18px;
      max-width: 840px;
      color: var(--muted);
      font-size: 20px;
      line-height: 1.45;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .metric {{
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(255,255,255,0.68);
      border: 1px solid rgba(124, 96, 70, 0.14);
    }}
    .metric strong {{
      display: block;
      font-size: 28px;
      line-height: 1;
      margin-bottom: 4px;
    }}
    .metric span {{
      color: var(--muted);
      font-size: 14px;
      text-transform: uppercase;
      letter-spacing: 0.12em;
    }}
    .capability-strip {{
      display: flex;
      flex-direction: column;
      gap: 14px;
      justify-content: center;
    }}
    .capability-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .capability-pill {{
      padding: 10px 14px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      border: 1px solid rgba(141, 53, 38, 0.14);
      font-size: 14px;
      font-weight: 700;
    }}
    .capability-pill span {{
      color: var(--muted);
      margin-left: 6px;
      font-weight: 600;
    }}
    .content {{
      display: grid;
      grid-template-columns: minmax(320px, 0.95fr) minmax(0, 2.05fr);
      gap: 20px;
      align-items: start;
    }}
    .stack, .workspace {{
      display: flex;
      flex-direction: column;
      gap: 18px;
    }}
    .panel {{
      padding: 20px;
    }}
    .panel h2 {{
      margin: 0 0 8px;
      font-size: 20px;
      letter-spacing: -0.03em;
    }}
    .panel p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.45;
    }}
    .zone-list, .link-list, .node-grid {{
      display: grid;
      gap: 14px;
      margin-top: 16px;
    }}
    .node-grid {{
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    }}
    .zone-card, .link-card {{
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(255,255,255,0.6);
      border: 1px solid rgba(124, 96, 70, 0.14);
    }}
    .zone-card strong, .link-card strong {{
      display: block;
      margin-bottom: 6px;
      font-size: 15px;
    }}
    .zone-card span, .link-card span {{
      color: var(--muted);
      font-size: 14px;
      line-height: 1.4;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
    }}
    .toolbar-copy {{
      color: var(--muted);
      font-size: 15px;
      line-height: 1.4;
      max-width: 760px;
    }}
    .toolbar-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    button {{
      appearance: none;
      border: 1px solid rgba(29, 25, 23, 0.12);
      background: rgba(255,255,255,0.72);
      color: var(--ink);
      border-radius: 999px;
      padding: 10px 14px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
    }}
    details > summary {{
      list-style: none;
      cursor: pointer;
    }}
    details > summary::-webkit-details-marker {{
      display: none;
    }}
    .node-card {{
      overflow: hidden;
    }}
    .node-card > summary {{
      padding: 18px 18px 14px;
      border-bottom: 1px solid rgba(124, 96, 70, 0.12);
    }}
    .node-topline {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }}
    .node-title {{
      margin: 0;
      font-size: 24px;
      line-height: 1.05;
      letter-spacing: -0.04em;
    }}
    .badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 7px 10px;
      border-radius: 999px;
      background: rgba(29, 25, 23, 0.05);
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .badge.accent {{
      background: var(--accent-soft);
      color: var(--accent);
    }}
    .node-summary {{
      margin: 0;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.45;
    }}
    .node-body {{
      padding: 16px 18px 18px;
      display: grid;
      gap: 14px;
    }}
    .node-section h4, .component-block h5 {{
      margin: 0 0 10px;
      color: var(--accent);
      font-size: 13px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
    }}
    .broadcast-item {{
      padding: 12px 14px;
      border-radius: 16px;
      background: rgba(141, 53, 38, 0.06);
      border: 1px solid rgba(141, 53, 38, 0.12);
      margin-bottom: 10px;
    }}
    .broadcast-item strong {{
      display: block;
      font-size: 15px;
      margin-bottom: 4px;
    }}
    .broadcast-item p {{
      margin: 0;
      color: var(--muted);
    }}
    .broadcast-meta {{
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }}
    .component-tree {{
      display: grid;
      gap: 10px;
    }}
    .component {{
      border-radius: 18px;
      border: 1px solid rgba(124, 96, 70, 0.14);
      background: rgba(255,255,255,0.76);
      overflow: hidden;
    }}
    .component.nested {{
      margin-top: 8px;
      margin-left: 12px;
      background: rgba(252,249,244,0.92);
    }}
    .component > summary {{
      padding: 14px 16px;
    }}
    .component-layer {{
      color: var(--accent);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.14em;
      margin-bottom: 6px;
    }}
    .component h4 {{
      margin: 0 0 4px;
      font-size: 16px;
      line-height: 1.2;
    }}
    .component-summary, .component-details, .interface-pill p {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.4;
    }}
    .component-body {{
      padding: 0 16px 16px;
      display: grid;
      gap: 12px;
    }}
    .interface-list, .component-cap-list {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .interface-pill, .component-cap {{
      padding: 8px 10px;
      border-radius: 12px;
      font-size: 12px;
      line-height: 1.35;
      border: 1px solid rgba(124, 96, 70, 0.14);
      background: rgba(255,255,255,0.8);
    }}
    .interface-pill strong {{
      display: block;
      margin-bottom: 3px;
      font-size: 12px;
    }}
    .interface-pill span {{
      display: block;
      color: var(--muted);
      margin-bottom: 4px;
    }}
    .component-cap {{
      background: rgba(36, 75, 61, 0.08);
      border-color: rgba(36, 75, 61, 0.14);
      color: var(--good);
      font-weight: 700;
    }}
    .footer-note {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 1080px) {{
      .hero, .content {{
        grid-template-columns: 1fr;
      }}
      .summary-grid {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <div class="hero-card">
        <p class="eyebrow">System Model</p>
        <h1>{esc(data["title"])}</h1>
        <p class="subtitle">{esc(data["subtitle"])}</p>
        <div class="summary-grid">
          <div class="metric"><strong>{len(data["profiles"])}</strong><span>device profiles</span></div>
          <div class="metric"><strong>{len(data["deployment"]["nodes"])}</strong><span>trusted nodes</span></div>
          <div class="metric"><strong>{len(data["capabilities"])}</strong><span>broadcast capabilities</span></div>
        </div>
      </div>
      <div class="hero-card capability-strip">
        <p class="eyebrow">Capability Broadcast</p>
        <h2>{esc(data["deployment"]["label"])}</h2>
        <p class="subtitle" style="font-size:17px;margin-bottom:0">{esc(data["deployment"]["summary"])}</p>
        <div class="capability-list">{capability_strip}</div>
      </div>
    </section>

    <div class="content">
      <aside class="stack">
        <section class="panel">
          <p class="eyebrow">Trust Zones</p>
          <h2>Where Singine lives</h2>
          <p>Nodes inherit device profiles, then advertise capabilities according to trust zone and runtime policy.</p>
          <div class="zone-list">{zone_cards}</div>
        </section>

        <section class="panel">
          <p class="eyebrow">Link Matrix</p>
          <h2>How trust moves</h2>
          <p>These links are deployment relationships, separate from profile internals.</p>
          <div class="link-list">{link_cards}</div>
        </section>

        <section class="panel">
          <p class="eyebrow">Capabilities</p>
          <h2>What nodes can announce</h2>
          <div class="zone-list">{capability_cards}</div>
        </section>
      </aside>

      <main class="workspace">
        <section class="panel">
          <div class="toolbar">
            <div class="toolbar-copy">
              Expand a node to inspect the profile instantiated on that device. Each component is independently collapsible so the diagram can scale from topology view to subsystem detail.
            </div>
            <div class="toolbar-actions">
              <button type="button" data-action="expand-nodes">Expand all nodes</button>
              <button type="button" data-action="collapse-nodes">Collapse all nodes</button>
              <button type="button" data-action="expand-components">Open all components</button>
              <button type="button" data-action="collapse-components">Close all components</button>
            </div>
          </div>
          <div class="node-grid">{node_cards}</div>
          <div class="footer-note">Source of truth: singine-system-diagram.xml. Schema: singine-system-diagram.rnc.</div>
        </section>
      </main>
    </div>
  </div>
  <script>
    (function () {{
      function setOpen(selector, open) {{
        document.querySelectorAll(selector).forEach(function (node) {{
          node.open = open;
        }});
      }}

      document.querySelector('[data-action="expand-nodes"]').addEventListener('click', function () {{
        setOpen('details[data-collapsible="node"]', true);
      }});

      document.querySelector('[data-action="collapse-nodes"]').addEventListener('click', function () {{
        setOpen('details[data-collapsible="node"]', false);
      }});

      document.querySelector('[data-action="expand-components"]').addEventListener('click', function () {{
        setOpen('details[data-collapsible="component"]', true);
      }});

      document.querySelector('[data-action="collapse-components"]').addEventListener('click', function () {{
        setOpen('details[data-collapsible="component"]', false);
      }});
    }})();
  </script>
</body>
</html>
"""


def compile_html(source: Path, target: Path) -> None:
    data = parse_xml(source)
    target.write_text(build_html(data), encoding="utf-8")


def main(argv: list[str]) -> int:
    base = Path(__file__).resolve().parent
    source = Path(argv[1]).resolve() if len(argv) > 1 else base / "singine-system-diagram.xml"
    target = Path(argv[2]).resolve() if len(argv) > 2 else base / "singine-system-diagram.html"
    compile_html(source, target)
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
