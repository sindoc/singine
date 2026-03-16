"""XML request/response scenario matrix for the Singine bridge.

This module generates XML requests, executes bridge-backed scenarios across
multiple query dimensions, and emits XML responses plus heatmap summaries.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET

from .cortex_bridge import BridgeDB


DIMENSIONS = ["sql", "sparql", "graphql"]
CYCLIC_PERIODS = ["P0", "P1", "P2"]


@dataclass
class ScenarioSpec:
    scenario_id: str
    label: str
    search_text: str
    sparql_query: str
    graphql_query: str
    sql_query: str
    sql_params: Tuple[Any, ...]
    min_expected: int = 0
    origin: str = "builtin"
    shock_search_text: Optional[str] = None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def lambda_expression() -> str:
    return "λ(period, scenario, dimension, category) = preserve_causality(period) ∘ measure_baseline(period) ∘ apply_shock(period+1 mod cycle) ∘ momentum(post_shock - baseline)"


def period_for_index(index: int) -> str:
    return CYCLIC_PERIODS[index % len(CYCLIC_PERIODS)]


def causality_preserved(baseline_period: str, shock_period: str) -> bool:
    baseline_idx = CYCLIC_PERIODS.index(baseline_period)
    shock_idx = CYCLIC_PERIODS.index(shock_period)
    return shock_idx == ((baseline_idx + 1) % len(CYCLIC_PERIODS))


def category_for_source_name(name: str) -> str:
    if name.startswith("singine:"):
        return "logseq"
    if name == "silkpage":
        return "web-content"
    if name == "claude":
        return "agent-claude"
    if name == "codex":
        return "agent-codex"
    if name == "knowyourai":
        return "reference-rdf"
    return name


def bridge_categories(db: BridgeDB) -> List[str]:
    names = {category_for_source_name(row["name"]) for row in db.list_sources()}
    return sorted(names)


def built_in_scenarios() -> List[ScenarioSpec]:
    return [
        ScenarioSpec(
            scenario_id="SCN-MARKDOWN",
            label="Markdown pages by type",
            search_text="markdown",
            sparql_query='SELECT ?s ?label WHERE { ?s a markdown ; rdfs:label ?label . } LIMIT 100',
            graphql_query='{ sparql(query:"SELECT ?s ?label WHERE { ?s a markdown ; rdfs:label ?label . } LIMIT 100") { rows } }',
            sql_query=(
                "SELECT e.iri, e.label, src.name AS source_name "
                "FROM entities e JOIN sources src ON src.source_id=e.source_id "
                "WHERE e.entity_type = ? LIMIT 100"
            ),
            sql_params=("markdown",),
            min_expected=1,
        ),
        ScenarioSpec(
            scenario_id="SCN-KERNEL",
            label="Kernel search across fragments",
            search_text="kernel",
            sparql_query='SELECT ?s WHERE { ?s <http://www.w3.org/2000/01/rdf-schema#label> "kernel" . } LIMIT 100',
            graphql_query='{ search(text:"kernel", limit:100) { iri label source_name snippet } }',
            sql_query=(
                "SELECT e.iri, e.label, src.name AS source_name, substr(f.text, 1, 200) AS snippet "
                "FROM fragments f "
                "JOIN entities e ON e.entity_id=f.entity_id "
                "JOIN sources src ON src.source_id=e.source_id "
                "WHERE lower(f.text) LIKE ? LIMIT 100"
            ),
            sql_params=("%kernel%",),
            min_expected=1,
        ),
        ScenarioSpec(
            scenario_id="SCN-SESSION",
            label="Session content search",
            search_text="session",
            sparql_query='SELECT ?s WHERE { ?s <http://purl.org/dc/terms/source> "claude" . } LIMIT 100',
            graphql_query='{ search(text:"session", limit:100) { iri label source_name snippet } }',
            sql_query=(
                "SELECT e.iri, e.label, src.name AS source_name, substr(f.text, 1, 200) AS snippet "
                "FROM fragments f "
                "JOIN entities e ON e.entity_id=f.entity_id "
                "JOIN sources src ON src.source_id=e.source_id "
                "WHERE lower(f.text) LIKE ? LIMIT 100"
            ),
            sql_params=("%session%",),
            min_expected=1,
        ),
        ScenarioSpec(
            scenario_id="SCN-TODO",
            label="TODO content search",
            search_text="todo",
            sparql_query='SELECT ?s WHERE { ?s a task . } LIMIT 100',
            graphql_query='{ search(text:"TODO", limit:100) { iri label source_name snippet } }',
            sql_query=(
                "SELECT e.iri, e.label, src.name AS source_name, substr(f.text, 1, 200) AS snippet "
                "FROM fragments f "
                "JOIN entities e ON e.entity_id=f.entity_id "
                "JOIN sources src ON src.source_id=e.source_id "
                "WHERE lower(f.text) LIKE ? LIMIT 100"
            ),
            sql_params=("%todo%",),
            min_expected=1,
        ),
        ScenarioSpec(
            scenario_id="TC003",
            label="System shock momentum after choc",
            search_text="session",
            shock_search_text="todo",
            sparql_query='SELECT ?s WHERE { ?s <http://purl.org/dc/terms/source> "claude" . } LIMIT 100',
            graphql_query='{ search(text:"session", limit:100) { iri label source_name snippet } }',
            sql_query=(
                "SELECT e.iri, e.label, src.name AS source_name, substr(f.text, 1, 200) AS snippet "
                "FROM fragments f "
                "JOIN entities e ON e.entity_id=f.entity_id "
                "JOIN sources src ON src.source_id=e.source_id "
                "WHERE lower(f.text) LIKE ? LIMIT 100"
            ),
            sql_params=("%session%",),
            min_expected=1,
        ),
    ]


def discover_file_scenarios(repo_root: Path) -> List[ScenarioSpec]:
    scenarios_dir = repo_root / "scenarios"
    specs: List[ScenarioSpec] = []
    if not scenarios_dir.exists():
        return specs

    for path in sorted(scenarios_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in {".rq", ".txt"}:
            continue
        term = path.stem.replace("-", " ").replace("_", " ").split()[0] if path.stem else path.name
        scenario_id = "SCN-" + path.stem.upper().replace("-", "_").replace(".", "_")
        specs.append(
            ScenarioSpec(
                scenario_id=scenario_id[:48],
                label=f"Scenario file {path.name}",
                search_text=term.lower(),
                sparql_query=f'SELECT ?s WHERE {{ ?s <http://www.w3.org/2000/01/rdf-schema#label> "{term.lower()}" . }} LIMIT 50',
                graphql_query=f'{{ search(text:"{term.lower()}", limit:50) {{ iri label source_name snippet }} }}',
                sql_query=(
                    "SELECT e.iri, e.label, src.name AS source_name, substr(f.text, 1, 200) AS snippet "
                    "FROM fragments f "
                    "JOIN entities e ON e.entity_id=f.entity_id "
                    "JOIN sources src ON src.source_id=e.source_id "
                    "WHERE lower(f.text) LIKE ? LIMIT 50"
                ),
                sql_params=(f"%{term.lower()}%",),
                min_expected=0,
                origin=str(path.relative_to(repo_root)),
            )
        )
    return specs


def source_name_for_iri(db: BridgeDB, iri: str) -> Optional[str]:
    row = db.conn.execute(
        "SELECT src.name FROM entities e JOIN sources src ON src.source_id=e.source_id WHERE e.iri = ?",
        (iri,),
    ).fetchone()
    return row["name"] if row else None


def execute_sql(db: BridgeDB, scenario: ScenarioSpec) -> List[Dict[str, Any]]:
    rows = db.conn.execute(scenario.sql_query, scenario.sql_params).fetchall()
    return [dict(row) for row in rows]


def execute_sparql(db: BridgeDB, scenario: ScenarioSpec) -> List[Dict[str, Any]]:
    result = db.sparql(scenario.sparql_query)
    rows: List[Dict[str, Any]] = []
    for row in result["rows"]:
        iri = row.get("s") or row.get("o")
        source_name = source_name_for_iri(db, iri) if iri else None
        item = dict(row)
        if source_name:
            item["source_name"] = source_name
        rows.append(item)
    return rows


def execute_graphql(db: BridgeDB, scenario: ScenarioSpec) -> List[Dict[str, Any]]:
    payload = db.graphql(scenario.graphql_query)
    data = payload.get("data", {})
    if "search" in data:
        return data["search"]
    if "sparql" in data and isinstance(data["sparql"], dict):
        return data["sparql"].get("rows", [])
    return []


def run_dimension(db: BridgeDB, scenario: ScenarioSpec, dimension: str) -> List[Dict[str, Any]]:
    if dimension == "sql":
        return execute_sql(db, scenario)
    if dimension == "sparql":
        return execute_sparql(db, scenario)
    if dimension == "graphql":
        return execute_graphql(db, scenario)
    raise ValueError(f"Unknown dimension: {dimension}")


def category_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for row in rows:
        category = category_for_source_name(row.get("source_name") or "unknown")
        counts[category] = counts.get(category, 0) + 1
    return counts


def heat_level(count: int) -> str:
    if count <= 0:
        return "cold"
    if count <= 2:
        return "warm"
    if count <= 10:
        return "hot"
    return "critical"


def heat_score(count: int) -> int:
    if count <= 0:
        return 0
    return min(9, int(math.log2(count + 1) * 3))


def xml_to_string(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode")


def build_request_xml(scenarios: Sequence[ScenarioSpec], dimensions: Sequence[str], categories: Sequence[str]) -> ET.Element:
    root = ET.Element("singine-request", {"kind": "scenario-matrix"})
    lambda_el = ET.SubElement(root, "lambda", {"args": "period scenario dimension category", "governed": "true"})
    lambda_el.text = lambda_expression()
    cycles_el = ET.SubElement(root, "cyclic-periods")
    for period in CYCLIC_PERIODS:
        ET.SubElement(cycles_el, "period", {"id": period})
    dims_el = ET.SubElement(root, "dimensions")
    for dimension in dimensions:
        ET.SubElement(dims_el, "dimension", {"id": dimension})

    cats_el = ET.SubElement(root, "data-categories")
    for category in categories:
        ET.SubElement(cats_el, "category", {"id": category})

    scenarios_el = ET.SubElement(root, "scenarios")
    for scenario in scenarios:
        sc_el = ET.SubElement(
            scenarios_el,
            "scenario",
            {"id": scenario.scenario_id, "label": scenario.label, "origin": scenario.origin},
        )
        ET.SubElement(sc_el, "sql").text = scenario.sql_query
        ET.SubElement(sc_el, "sparql").text = scenario.sparql_query
        ET.SubElement(sc_el, "graphql").text = scenario.graphql_query
        if scenario.shock_search_text:
            shock_el = ET.SubElement(sc_el, "shock")
            ET.SubElement(shock_el, "baseline-search").text = scenario.search_text
            ET.SubElement(shock_el, "shock-search").text = scenario.shock_search_text
    return root


def build_response_xml(results: List[Dict[str, Any]]) -> ET.Element:
    root = ET.Element("singine-response", {"kind": "scenario-matrix-result"})
    results_el = ET.SubElement(root, "results")
    for result in results:
        attrs = {
            "scenario-id": result["scenario_id"],
            "dimension": result["dimension"],
            "data-category": result["data_category"],
            "count": str(result["count"]),
            "score": str(result["score"]),
            "heat": result["heat"],
            "status": result["status"],
            "momentum": str(result.get("momentum", 0)),
            "baseline-period": result["baseline_period"],
            "shock-period": result["shock_period"],
            "causality": "preserved" if result["causality_preserved"] else "violated",
        }
        item = ET.SubElement(results_el, "result", attrs)
        ET.SubElement(item, "query").text = result["query"]
        if "baseline_count" in result:
            shock_el = ET.SubElement(item, "shock")
            ET.SubElement(shock_el, "baseline-count").text = str(result["baseline_count"])
            ET.SubElement(shock_el, "post-shock-count").text = str(result["post_shock_count"])
            ET.SubElement(shock_el, "baseline-at").text = result["baseline_at"]
            ET.SubElement(shock_el, "shock-at").text = result["shock_at"]
    return root


def build_heatmap_xml(results: List[Dict[str, Any]], scenarios: Sequence[ScenarioSpec], dimensions: Sequence[str], categories: Sequence[str]) -> ET.Element:
    root = ET.Element("heatmap", {"kind": "scenario-dimension-category"})
    for scenario in scenarios:
        scenario_el = ET.SubElement(root, "scenario", {"id": scenario.scenario_id, "label": scenario.label})
        for dimension in dimensions:
            dim_el = ET.SubElement(scenario_el, "dimension", {"id": dimension})
            for category in categories:
                match = next(
                    (
                        item for item in results
                        if item["scenario_id"] == scenario.scenario_id
                        and item["dimension"] == dimension
                        and item["data_category"] == category
                    ),
                    None,
                )
                attrs = {"id": category, "count": "0", "score": "0", "heat": "cold", "status": "empty"}
                if match:
                    attrs = {
                        "id": category,
                        "count": str(match["count"]),
                        "score": str(match["score"]),
                        "heat": match["heat"],
                        "status": match["status"],
                        "momentum": str(match.get("momentum", 0)),
                        "baseline-period": match["baseline_period"],
                        "shock-period": match["shock_period"],
                        "causality": "preserved" if match["causality_preserved"] else "violated",
                    }
                ET.SubElement(dim_el, "cell", attrs)
    return root


def execute_matrix(db_path: Path, repo_root: Path, output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db = BridgeDB(db_path)
    try:
        db.setup()
        scenarios = built_in_scenarios() + discover_file_scenarios(repo_root)
        categories = bridge_categories(db)

        request_xml = build_request_xml(scenarios, DIMENSIONS, categories)
        results: List[Dict[str, Any]] = []

        for scenario in scenarios:
            for dimension_index, dimension in enumerate(DIMENSIONS):
                baseline_period = period_for_index(dimension_index)
                shock_period = period_for_index(dimension_index + 1)
                rows = run_dimension(db, scenario, dimension)
                counts = category_counts(rows)
                total_count = sum(counts.values())
                passed = total_count >= scenario.min_expected if scenario.min_expected > 0 else True
                baseline_at = now_iso()
                shock_at = now_iso()
                shock_counts: Dict[str, int] = {}
                if scenario.shock_search_text:
                    shock_rows = db.search(scenario.shock_search_text, limit=100) if dimension == "graphql" else []
                    if dimension == "sql":
                        shock_rows = [
                            dict(row) for row in db.conn.execute(
                                scenario.sql_query,
                                (f"%{scenario.shock_search_text.lower()}%",),
                            ).fetchall()
                        ]
                    elif dimension == "sparql":
                        shock_rows = [
                            dict(row) for row in db.sparql('SELECT ?s WHERE { ?s a task . } LIMIT 100')["rows"]
                        ]
                        for item in shock_rows:
                            iri = item.get("s") or item.get("o")
                            source_name = source_name_for_iri(db, iri) if iri else None
                            if source_name:
                                item["source_name"] = source_name
                    shock_counts = category_counts(shock_rows)
                    shock_at = now_iso()
                causality_ok = causality_preserved(baseline_period, shock_period)
                for category in categories:
                    count = counts.get(category, 0)
                    score = heat_score(count)
                    baseline_count = count
                    post_shock_count = shock_counts.get(category, count) if scenario.shock_search_text else count
                    momentum = abs(post_shock_count - baseline_count)
                    results.append(
                        {
                            "scenario_id": scenario.scenario_id,
                            "dimension": dimension,
                            "data_category": category,
                            "count": count,
                            "score": score,
                            "heat": heat_level(count),
                            "status": "pass" if (passed and causality_ok) else "fail",
                            "query": getattr(scenario, f"{dimension}_query"),
                            "baseline_count": baseline_count,
                            "post_shock_count": post_shock_count,
                            "momentum": momentum,
                            "baseline_period": baseline_period,
                            "shock_period": shock_period,
                            "causality_preserved": causality_ok,
                            "baseline_at": baseline_at,
                            "shock_at": shock_at,
                        }
                    )

        response_xml = build_response_xml(results)
        heatmap_xml = build_heatmap_xml(results, scenarios, DIMENSIONS, categories)

        request_path = output_dir / "request.xml"
        response_path = output_dir / "response.xml"
        heatmap_path = output_dir / "heatmap.xml"

        request_path.write_text(xml_to_string(request_xml), encoding="utf-8")
        response_path.write_text(xml_to_string(response_xml), encoding="utf-8")
        heatmap_path.write_text(xml_to_string(heatmap_xml), encoding="utf-8")

        return {
            "db_path": str(db_path),
            "output_dir": str(output_dir),
            "request_xml": str(request_path),
            "response_xml": str(response_path),
            "heatmap_xml": str(heatmap_path),
            "scenario_count": len(scenarios),
            "dimension_count": len(DIMENSIONS),
            "category_count": len(categories),
            "result_count": len(results),
            "failures": len([item for item in results if item["status"] == "fail"]),
        }
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate XML request/response scenario matrices for Singine.")
    parser.add_argument("--db", default="/tmp/sqlite.db")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--output-dir", default="/tmp/singine-xml-matrix")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = execute_matrix(
        Path(args.db).expanduser(),
        Path(args.repo_root).expanduser(),
        Path(args.output_dir).expanduser(),
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
