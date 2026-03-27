# Wikipedia Contribution Commands

This document defines the `singine wikipedia contrib` command surface as a stable, documented wrapper around standalone Wikipedia-support repositories.

The current maintained topic is `collibra`, backed by the standalone repository at `/Users/skh/ws/git/github/sindoc/datatech-wiki-kg`.

## Goal

Provide one command family that can:

- report current repository and campaign state
- refresh derived knowledge-graph and feed artifacts
- synchronize the visual Logseq working surface
- render a user-friendly process diagram from a standards-based XML protocol
- run one end-to-end command-line test case
- prepare or send opt-in notifications

## Command form

```bash
singine wikipedia contrib collibra [--repo-root PATH] [--action ACTION] [--json]
```

## Supported actions

| Action | Purpose | Underlying command |
|---|---|---|
| `status` | Return workflow metadata without modifying files | none |
| `refresh` | Rebuild derived repository artifacts | `python3 scripts/refresh_repo.py` |
| `kernel-sync` | Project working material into the Singine kernel Logseq graph | `python3 scripts/sync_kernel_views.py` |
| `visualize` | Render the Mermaid process diagram from the XML protocol payload | `python3 scripts/render_process_visual.py` |
| `test-case` | Run the end-to-end verification flow | `python3 scripts/test_case.py` |
| `install-hooks` | Install the repository-local post-commit hook | `python3 scripts/install_hooks.py` |
| `preview-mail` | Render individualized opt-in updates without sending mail | `python3 scripts/send_opt_in_update.py` |
| `send-mail` | Send individualized opt-in updates | `python3 scripts/send_opt_in_update.py --send` |

## Primary examples

```bash
singine wikipedia contrib collibra --json
singine wikipedia contrib collibra --action refresh --json
singine wikipedia contrib collibra --action kernel-sync --json
singine wikipedia contrib collibra --action visualize --json
singine wikipedia contrib collibra --action test-case --json
singine wikipedia contrib collibra --action install-hooks --json
singine wikipedia contrib collibra --action preview-mail --json
```

## Documented companion surfaces

- Man page: `man singine-wikipedia`
- OpenAPI: `schema/singine-wikipedia-api.json`
- Javadoc source: `core/java/singine/wikipedia/`
- SinLisp command model: `runtime/sinlisp/wikipedia_contrib.sinlisp`
- Ballerina bindings: `ballerina/singine.bal`

## Canonical standalone repository files

- `protocol/wikipedia-contrib-process.xml` is the canonical process payload
- `visuals/wikipedia-contrib-process.mmd` is the derived Mermaid workflow
- `site/src/xml/en/` contains the public SilkPage-style XML publication source
- `graph/collibra-support.jsonld` is the generated JSON-LD graph
- `feeds/datatech-collibra.atom` and `feeds/datatech-collibra.rss` are the generated update feeds

## Testing

Repository workflow verification:

```bash
cd /Users/skh/ws/git/github/sindoc/datatech-wiki-kg
make test-case
```

Documentation and command-surface verification:

```bash
cd /Users/skh/ws/git/github/sindoc/singine
python3 -m unittest py.tests.test_wikipedia_docs_surface -v
```

## Interaction model

The CLI wrapper is the executable surface. The OpenAPI document describes a matching local HTTP interaction model for test harnesses and service adapters. The SinLisp file captures the same action inventory in a compact rule-oriented form for command generation and test planning.
