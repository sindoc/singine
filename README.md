# Singine

Singine is the main agent orchestrator in this workspace.

The working direction is a secure, privacy-aware command-line and service orchestration system: closer in spirit to an agent shell than a chat wrapper, with stronger boundaries around local execution, data handling, and operational control.

Primary development areas:

- `core/` for the Clojure runtime, routing, and server logic
- `singine/` for the Python CLI and Python-side integration code
- `docker/` for local service packaging
- `docs/` for operational and design notes

Workspace notes:

- linked sibling repos such as `00-tools` and `quickstart-resources` live under `~/ws/git/...`
- unmanaged historical material has been moved into `~/ws/git/local/backlog`
- use the canonical path `~/ws/git/github/sindoc/singine` for development

Start with `make help` at the repo root, or `make help` in `core/` and `docker/` for subproject-specific commands.
