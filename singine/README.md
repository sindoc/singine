# Singine Python Package

This package contains the Python-side command-line interface, orchestration helpers, and knowledge-layer integrations for Singine.

Key areas:

- `cli.py` for the command-line entrypoint
- `lens/` for focused views over activities and Collibra-oriented context
- `knowledge_graph.py`, `rdf_ontology.py`, and `fibo_integration.py` for semantic and ontology-oriented work
- `scenario_engine.py` and `storytelling.py` for higher-level orchestration and concept work

The repo root `Makefile` includes a `python-smoke` target to compile this package and catch syntax regressions quickly.
