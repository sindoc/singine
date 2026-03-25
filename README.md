# Singine

Singine is the main agent orchestrator in this workspace.

The working direction is a secure, privacy-aware command-line and service orchestration system: closer in spirit to an agent shell than a chat wrapper, with stronger boundaries around local execution, data handling, and operational control.

Primary development areas:

- `core/` for the Clojure runtime, routing, and server logic
- `singine/` for the Python CLI and Python-side integration code
- `docker/` for local service packaging
- `docs/` for operational and design notes

At a high level, the architecture is:

`terminal CLI -> Python command surface -> local HTTP edge/server -> bridge + activity taxonomy + docs/publication pipeline`

The main integration seams are:

- git awareness for repo state, snapshots, and governed review
- docker awareness for local edge packaging
- Java activity/action interfaces under `core/java/singine/activity`
- the canonical activity taxonomy at `core/resources/singine/activity/taxonomy.edn`
- SilkPage publication and spec rendering under `docs/`
- bridge and Logseq APIs for local knowledge access

Workspace notes:

- linked sibling repos such as `00-tools` and `quickstart-resources` live under `~/ws/git/...`
- unmanaged historical material has been moved into `~/ws/git/local/backlog`
- use the canonical path `~/ws/git/github/sindoc/singine` for development

Start with `make help` at the repo root, or `make help` in `core/` and `docker/` for subproject-specific commands.

## Singine command

Install a stable local `singine` command with POSIX shell support:

```bash
make install
# or install the workstation profile, including git-filter-repo
make install-workstation
# or
make install-bash
# or
make install-sh
# or install Apache Ant for the JVM build targets
python3 -m singine.command install ant
# or install Saxonica xmldoclet into ~/.m2 for XML Javadoc generation
python3 -m singine.command install xmldoclet
```

That installs:

- `~/.local/bin/singine`
- `~/.local/share/man/man1/singine.1`
- `~/.local/share/man/man1/singine-bridge.1`

The launcher is `sh`-compatible, so it works from both `bash` and POSIX `sh`.
`make install` updates both `~/.bashrc` and `~/.profile`.
For development machines, prefer `make install-workstation` or
`singine install --mode workstation`; that profile also ensures
`git-filter-repo` is available so history rewrites such as
`singine git rm-public-dir ...` are ready when needed.
Use `singine context` to distinguish the live `terminal context` from the inherited
`sourced environment`, following the glossary under
`/Users/skh/ws/today/00-WORK/morning_glossary_package`.
If `ant` is missing, run `singine install ant` so the Ant-based Singine and SilkPage
targets can execute. If `xmldoclet` is missing, run `singine install xmldoclet`
before `ant javadoc-xml`.
If you only need the history-rewrite tool directly, run
`singine install git-filter-repo`.

Examples:

```bash
singine find filesAboutTopic singine
singine find filesAboutTopic collibra --null | singine mv fileListTo ~/ws/collibra/raw/ --null --mkdir
singine template create maven singine-spec-demo --dir ~/ws/git/local/singine-spec-demo --group-id com.markupware
singine template create npm silkpage-spec-ui --dir ~/ws/git/local/silkpage-spec-ui --scope sindoc
singine context --json
singine man singine
singine man singine-template
singine man singine-bridge
find . -maxdepth 1 -iname '*collibra*' -print0 | singine mv fileListTo ~/ws/collibra/raw/ --null --mkdir
singine runtime inspect
singine runtime exec bridge sources --db /tmp/sqlite.db
singine xml matrix --db /tmp/sqlite.db --output-dir /tmp/singine-xml-matrix
singine server inspect --json
singine server health --json
singine server bridge --action sources --json
singine server test-case /tmp/singine-server-case
singine logseq inspect --json
singine snapshot save --json
```

## Removing an accidental public directory

If a directory should never have landed in the public repo, do not use plain
`git rm` by itself. That only removes the directory from the current tip; it does
not remove it from branch history.

Use the Singine planner to generate the exact rewrite and push commands:

```bash
singine git rm-public-dir github/singine prod/Q3 \
  -all
```

That command prints the `git filter-repo` rewrite step and the explicit
`git push --force-with-lease` commands for each affected branch. The reusable
playbook lives in [`docs/git-rm-public-dir.md`](docs/git-rm-public-dir.md).

## Local server, edge, docker, and snapshots

The default Singine HTTP server surface is the Clojure/Camel runtime in `core/`.
It binds to `0.0.0.0:8080` and is usually queried from the CLI through
`127.0.0.1:8080`.

Use these top-level commands:

```bash
singine server inspect
singine server health
singine server bridge --action sources --json
singine logseq ping --token "$LOGSEQ_API_TOKEN" --json
singine snapshot save --output /tmp/singine-context.json --json
```

`singine server inspect` reports:

- default host and port
- environment type (`local`, `edge`, `docker`)
- docker compose and Dockerfile paths
- git branch and status excerpt
- Java interface roots and taxonomy path
- migration paths such as `/tmp/sqlite.db`, `/tmp/singine-xml-matrix`, and the generated doclet/spec locations

`singine snapshot save` persists the same context into one JSON file under
`~/.singine/context/latest.json` by default.

To generate the whole runnable surface bundle from Singine itself:

```bash
singine server test-case /tmp/singine-server-case
cat /tmp/singine-server-case/README.txt
python3 -m unittest py.tests.test_server_surface_commands -v
```

## Cortex bridge

Use the stdlib bridge module to merge local Singine, Silkpage, Claude, and Codex data into SQLite:

```bash
singine bridge build --db /tmp/sqlite.db
singine jdbc-url --db /tmp/sqlite.db
singine bridge sources --db /tmp/sqlite.db
singine bridge search --db /tmp/sqlite.db "todo"
singine bridge sparql --db /tmp/sqlite.db 'SELECT ?s ?label WHERE { ?s a markdown ; rdfs:label ?label . } LIMIT 10'
singine bridge graphql --db /tmp/sqlite.db '{ search(text:"todo", limit:5) { iri label snippet } }'
singine xml matrix --db /tmp/sqlite.db --output-dir /tmp/singine-xml-matrix
```

The local Singine server exposes the same bridge at `GET /bridge`. Set `SINGINE_CORTEX_DB=/tmp/sqlite.db` before starting `clojure -M:serve` if you want the server to query a non-default database path.

The bridge now also ingests the local `knowyourai-framework` RDF pack, if it exists at `~/ws/git/github/sindoc/knowyourai-framework`. Start with:

```bash
make bridge-build
make bridge-sources
make knowyourai-list
make knowyourai-query QUERY=scenarios/knowyourai/list-concepts.rq
```

The documented query pack lives in `docs/knowyourai-sparql.md`.

## Auth and model commands

Singine now has a simple authentication bootstrap surface for local TOTP-based login flows.
It emits standard `otpauth://` URIs that 1Password and Google Authenticator can import,
with Microsoft Authenticator kept as a planned compatibility target on the same TOTP shape.

Start with:

```bash
make auth-demo
make auth-uri
make auth-code
python3 -m singine.command auth login --state /tmp/singine-totp.json --code 123456
```

The repo also exposes a model catalog so the key objects are discoverable from one place:

```bash
make model-catalog
python3 -m singine.command model inspect code-table
python3 -m singine.command model inspect "Business Term"
```

The catalog covers:

- bootstrap commands
- auth operations
- master data surfaces such as the SQLite code table
- reference data such as scenario codes, IATA mappings, and KnowYourAI RDF
- entity families exposed through the Collibra bridge lens

### Logseq runtime mode

The bridge now uses Singine's existing Logseq integration in two modes:

- API mode: if `LOGSEQ_API_TOKEN` is set and `LOGSEQ_API_URL` is reachable, the bridge ingests the current graph through the Logseq HTTP API.
- Filesystem mode: if the API is unavailable, the bridge falls back to local Logseq graph directories under `~/ws/logseq`.

This gives a layered query path:

`Logseq API or filesystem -> SQLite physical schema -> SPARQL subset -> GraphQL-shaped response`

## XML scenarios and heatmaps

`singine xml matrix` generates:

- `request.xml`
- `response.xml`
- `heatmap.xml`

The matrix runs built-in and discovered scenario specs across:

- query dimensions: `sql`, `sparql`, `graphql`
- data categories derived from the bridge sources, such as `logseq`, `agent-claude`, `agent-codex`, and `web-content`

Each response cell records count, score, heat level, and pass/fail status.

## Action/activity and publication alignment

Singine's action/activity model is anchored in:

- Java interfaces in `core/java/singine/activity/`
- the taxonomy in `core/resources/singine/activity/taxonomy.edn`
- the `singine activity` manpage and CLI surface

That model aligns with the publication pipeline as follows:

- Ant generates HTML and XML Javadoc
- Saxonica `xmldoclet` produces XML suitable for downstream transformation
- `docs/Makefile` turns those artifacts into DocBook/spec material
- SilkPage renders the generated spec HTML
- the same taxonomy also drives XML matrix, GraphQL/SPARQL templates, and Logseq-oriented query artifacts
