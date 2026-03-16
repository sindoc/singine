# singine — Python package reference

The Python half of Singine. Provides the CLI surface (`singine <command>`),
all integration adapters, and the semantic / knowledge layer. The Clojure
runtime in `core/` handles the long-running server and document pipeline;
this package is everything you drive from a terminal or another script.

---

## How it loads

```
~/.local/bin/singine              ← sh-compatible launcher (make install)
  └─ python3 -m singine.command   ← package entry point
       └─ command.py :: main()    ← builds argument tree, dispatches to cmd_*
```

Every `singine <subcommand>` call ends in one `cmd_*` function in
`command.py`. Modules are imported lazily at function call time — startup
is fast regardless of how many modules exist.

---

## Module reference

### `command.py` — CLI entry point and dispatcher

Contains `build_parser()` (the full argparse tree) and a `cmd_*` function
for every leaf subcommand. This is the file to read first when you want to
understand what any `singine` invocation actually does.

**Full subcommand tree**

| Subcommand | Handler | Delegates to |
|---|---|---|
| `context` | `cmd_context` | inline + `cortex_bridge` |
| `bridge build` | `cmd_bridge_build` | `cortex_bridge` |
| `bridge sources / search / entity / sparql / graphql` | `cmd_bridge_passthrough` | `cortex_bridge` |
| `jdbc-url` | `cmd_jdbc_url` | `cortex_bridge` |
| `xml matrix` | `cmd_xml_matrix` | `xml_matrix` |
| `man` | `cmd_man` | filesystem `man/` |
| `install` | `cmd_install` | inline |
| `runtime inspect` | `cmd_runtime_inspect` | inline |
| `runtime exec` | `cmd_runtime_exec` | inline — wraps a **singine** subcommand |
| `runtime exec-external` | `cmd_runtime_exec_external` | inline — wraps **any binary** |
| `auth totp init / uri / code / verify` | `cmd_auth_totp_*` | `auth_totp` |
| `auth login` | `cmd_auth_login` | `auth_totp` → `idp` |
| `idp *` | `build_idp_parser` | `idp` |
| `decide` | `cmd_decide` | inline HTTP |
| `model catalog` | `cmd_model_catalog` | `model_catalog` |
| `model inspect` | `cmd_model_inspect` | `model_catalog` |
| `singe render / people / who` | `cmd_singe_*` | `singe` |
| `transfer sync / ssh / sftp / queue / stack / …` | `cmd_transfer_*` | `transfer` |
| `smtp test / send` | `cmd_smtp_*` | inline `smtplib` |

**`runtime exec` vs `runtime exec-external`**

Both wrap a command in a JSON envelope containing `terminal_context`,
`sourced_environment`, and `runtime_capabilities`.

| | `runtime exec` | `runtime exec-external` |
|---|---|---|
| What it runs | A singine subcommand | Any external binary |
| How | `python3 -m singine.command <args>` | `shutil.which()` + fallback to `~/.local/bin/` |
| Injection safe | Yes — no shell | Yes — no shell |
| Session token | — | Reads `SINGINE_SESSION_TOKEN`, appends prefix to envelope |
| Use case | Wrap a singine call with runtime context | Gate for `collibractl` and similar tools |

`exec-external` is the sanctioned execution gate used by
`SingineRuntimeGate.groovy` in the Collibra toolkit. The binary is resolved
without shell interpolation so there is no command injection surface.

---

### `cortex_bridge.py` — local semantic index (SQLite)

Builds a SQLite database that approximates a small RDF graph. Used as the
local knowledge base — merges Singine, SilkPage, Claude, Logseq, and Codex
content into a single queryable store.

**Three tables**

```
entities        (iri, label, type, source, created_at)
statements      (subject_iri, predicate_iri, object_iri_or_literal, source)
text_fragments  (iri, text, source, created_at)
```

`statements` is the triple table. `text_fragments` holds large text blobs
that would bloat `statements`.

**SPARQL-to-SQL translation** — a narrow subset of SPARQL triple patterns
(`?s ?p ?o`, `?s rdf:type ?type`, filter by predicate) is translated to
`JOIN`s at query time. This is not a full SPARQL engine — it covers the
lookup patterns exposed by `singine bridge sparql`.

**RDF prefixes registered** — `rdf:`, `rdfs:`, `skos:`, `dc:`, `dcterms:`,
`foaf:`, `prov:`, `schema:`, `singine:`, `knowyourai:`.

**`singine:` custom predicates** — `singine:contains`, `singine:linksTo`,
`singine:partOf`, `singine:runtime`, `singine:status` — used to model
Singine-specific relationships between documents and activities.

**CLI surface**

```bash
singine bridge build    --db /tmp/sqlite.db
singine bridge sources  --db /tmp/sqlite.db
singine bridge search   --db /tmp/sqlite.db "elia electricity domain"
singine bridge entity   --db /tmp/sqlite.db <iri>
singine bridge sparql   --db /tmp/sqlite.db "SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 20"
singine bridge graphql  --db /tmp/sqlite.db "{ entity(iri: \"…\") { … } }"
```

This is the discovery layer for Semantic Model 1 (see CLAUDE.md in the repo root).

---

### `operating_model.py` — Collibra operating model in Python

Python dataclasses that mirror Collibra's operating model — the "grammar"
of data governance. Must be the first thing understood before touching
anything Collibra-related.

**Core types**

| Class | What it represents |
|---|---|
| `ResourceType` | Enum: `COMMUNITY`, `DOMAIN`, `ASSET`, `ATTRIBUTE`, `RELATION` |
| `TypeDefinition` | One registered type: `type_id`, `type_name`, `resource_type`, `parent_type_id`, constraints |
| `Scope` | Assigns attribute / relation / domain types to an asset type without creating custom types |
| `OperatingModelConfig` | The complete grammar: `community_types`, `domain_types`, `asset_types` dicts keyed by id |
| `Responsibility` | Role assignment: `{resource_id, role_id, principal_id, principal_type}` |

`TypeDefinition.inherits_from(parent_id)` walks the type hierarchy.
`OperatingModelConfig` is the entry point — build one, populate its type
dicts, then pass it to the lens layer or the REST sync.

This module is the Python counterpart of `CollibraTypeRegistry` in the
Groovy toolkit (`tools-nested/collibra-fs/CollibraFsMapper.groovy`). Both
sides must agree on type UUIDs when syncing.

---

### `model_catalog.py` — static Singine model catalog

A lightweight, import-safe catalog of every named object in the Singine
model. Deliberately avoids importing `lens/` so it works on a minimal
install.

`COLLIBRA_ASSET_TYPES` — all OOB Collibra asset type names.
`COLLIBRA_DOMAIN_TYPES` — domain type names (Glossary, Physical Data
Dictionary, …).
`catalog()` — returns `bootstrappers`, `auth_operations`, `master_data`,
`reference_data`, `entity_families`, `collibra_bridge`. Powers
`singine model catalog --json`.
`inspect_object(name)` — deep-dives on one named model object. Powers
`singine model inspect "Data Element"`.

---

### `lens/` — metamodel transformation layer

A **lens** transforms *source entities* (Logseq pages, CSV rows, RDF
concepts, PROV activities) into a *target metamodel representation*
(Collibra, DCAT, Dublin Core). Each lens is a class implementing the
abstract `Lens` base. See `lens/README.md` for the full design.

**Three lenses currently implemented**

| Module | Lens | Transforms into |
|---|---|---|
| `lens/collibra.py` | `CollibraLens` | Collibra community / domain / asset / relation |
| `lens/activity.py` | `ActivityLens` | PROV-O activity + agent records |
| `lens/base.py` | `Lens` (abstract) | Defines the `LensEntity` carrier and `transform()` contract |

The `CollibraLens` is the bridge between the semantic layer and the
Groovy Collibra sync clients. A `LensEntity` goes in; a `CollibraAsset`
comes out, ready for `CollibraV2Client.upsertAsset()`.

---

### `collibra_translator.py` — structured dict → Collibra payload

Translates Python dicts (from bridge search results, Logseq exports, or
CSV rows) into the exact payload shape expected by `CollibraV2Client` or
`CollibraGraphQLClient`. Sits between `cortex_bridge` / `lens/` and the
Groovy sync layer when running a full import pipeline from Python.

---

### `auth_totp.py` — TOTP authentication

**`TOTPProfile`** — `{secret, issuer, account_name, digits, period, algorithm}`.
**`profile.uri()`** — `otpauth://` provisioning URI for 1Password / Google
Authenticator import.
**`profile.current_code()`** — live 6-digit code.
**`verify_totp(code, secret, …)`** — `{ok, error}`.

`singine auth login` chains TOTP verification → `idp.cmd_idp_login` for
the governed token exchange. The resulting session token is written to
`~/.singine/session.json` and picked up by `SINGINE_SESSION_TOKEN` when
`exec-external` is used.

---

### `idp.py` — humble-IdP CLI surface

Thin HTTP wrappers around the Node.js/Fastify humble-IdP server at
`https://id.singine.local` (overridable via `IDP_URL` env var).

All subcommands are registered via `build_idp_parser(sub)` which is called
from `command.py`'s `build_parser()`.

| Subcommand | What it does |
|---|---|
| `idp login` | Exchange TOTP code for a session token → `~/.singine/session.json` |
| `idp logout` | Invalidate the current session |
| `idp token` | Print the current bearer token |
| `idp whoami` | Resolve current session to a user identity |
| `idp users` | List the IdP user registry |
| `idp api-keys` | Create / list / revoke API keys |
| `idp git snapshot` | Snapshot IdP state to a git-tracked directory |
| `idp git restore` | Restore IdP state from a git snapshot |
| `idp op-read` | Read a 1Password secret reference via `op-read.sh` |

Session file: `~/.singine/session.json` — `{token, user_urn, expires_at}`.

---

### `idp_git.py` — git-backed IdP state management

Snapshot and restore the full humble-IdP configuration (users, API keys,
SMTP settings, certificates) to/from a git-tracked directory. Used by
`singine idp git snapshot` and `singine idp git restore`. Makes the IdP
state auditable and recoverable.

---

### `singe.py` — @mention template engine

**SINGE Is Not Generally Expansive** (but it is — it expands @mentions
into governed identities).

Resolves `@person` tokens in template strings using a three-source
registry in priority order:

| Priority | Source | Format |
|---|---|---|
| 1 (highest) | `~/.singine/singe.people` | JSON, user-managed |
| 2 | `humble-idp/config/users.properties` | IdP registry |
| 3 | Built-in registry | Project collaborators + named figures |

**Match strategy** (in order): exact key → alias exact → prefix (≤ 5 chars)
→ difflib fuzzy. `@skh` → `Sina Khalili Moghaddam`. `@stal` → `Richard
Stallman`.

```bash
singine singe render "reviewed by @skh, inspired by @stal"
singine singe people --json
singine singe who @skh --json
```

---

### `transfer.py` — file transfer, queues, stacks, XML processing

| Subcommand | What it does |
|---|---|
| `transfer sync` | `rsync` or `scp` wrapper — captures output as JSON |
| `transfer ssh` | Run a remote command over SSH, return JSON |
| `transfer sftp` | Get or put a file over SFTP |
| `transfer queue push/pop/peek/list/clear` | Persistent FIFO queue (JSON state file) |
| `transfer stack push/pop/peek/list/clear` | Persistent LIFO stack (JSON state file) |
| `transfer structure` | Introspect a queue or stack state file |
| `transfer process-request` | Parse an XML request into a structured JSON envelope |
| `transfer generate-response` | Generate N response variants from an input (default ×4) |
| `transfer project` | Select (project) fields from a JSON structure |
| `transfer analyze-result` | Compute statistics and shape summary for a JSON result |

Queues and stacks use plain JSON files (default `/tmp/singine-queue.json`)
— no daemon required. Useful for lightweight pipeline state between script
invocations.

---

### `xml_matrix.py` — XML request/response matrix generator

Generates a matrix of XML request and response documents across scenario
dimensions and data categories, using the bridge database as source
material. Outputs XML files and a heatmap to a directory.

```bash
singine xml matrix --db /tmp/sqlite.db --output-dir /tmp/singine-xml-matrix
```

This is step 8 of the Semantic Model 1 sequence (see repo-root `CLAUDE.md`)
and produces the XML baseline for the Elia electricity domain model.

---

### `scenario_engine.py` — declarative scenario runner

Executes multi-step governance and agent scenarios defined as ordered lists
of singine subcommand calls. A scenario is a declarative script (no BPMN
required for simple flows). Each step carries its subcommand, expected
outcome, and a rollback action for failed steps.

Used to capture agent orchestration examples, governance workflows, and
compliance patterns that should eventually become tests or product flows.
See `scenarios/` at the repo root for the scenario pack.

---

### `storytelling.py` — narrative wrapper for scenarios

Wraps a scenario execution in human-readable narrative context. Given a
domain model and a set of actors (resolved via `singe.py`), it generates
audit-trail summaries and decision logs that are understandable to business
stakeholders, not just engineers.

---

### Quick-reference: remaining modules

| Module | Purpose |
|---|---|
| `config.py` | Central config: reads `~/.singine/config.json`, env vars, defaults |
| `context_enrichment.py` | Adds runtime + session + bridge data to a context dict |
| `contract_model.py` | Data contract modelling — schema, SLA, ownership, lineage |
| `eisenhower.py` | Eisenhower matrix task prioritisation (urgency × importance) |
| `fibo_integration.py` | FIBO (Financial Industry Business Ontology) adapter |
| `knowledge_graph.py` | Higher-level KG operations over the bridge: typed traversals, subgraph extraction |
| `logseq.py` | Parse Logseq markdown graph pages and todos |
| `logseq_api.py` | Logseq HTTP API client (local Logseq desktop app) |
| `logseq_url.py` | Build `logseq://` deep-link URLs for pages and blocks |
| `parsers.py` | Shared text / structured data parsers |
| `query.py` | Bridge query builder — SPARQL and GraphQL lookup construction |
| `rdf_ontology.py` | Load, validate, and query RDF/OWL ontology files |
| `temporal.py` | Date/time utilities — business day arithmetic, ISO 8601, CET/CEST |

---

## Where this fits in the larger architecture

```
Electron shell
    │
    ├─ core/        (Clojure) — document pipeline, OCR, Jena RDF, Lucene, Kafka
    │       ↑
    │   This Python package bridges the gap while Clojure migration proceeds.
    │   Modules marked "migrate to Clojure" in CLAUDE.md will eventually
    │   be replaced by Clojure counterparts in core/.
    │
    └─ singine/     (this package)
           ├─ command.py        ← always Python, the CLI entry point
           ├─ cortex_bridge.py  ← Python now, SQLite projection; Clojure core later
           ├─ operating_model.py← Python now, Clojure middleware later
           ├─ lens/             ← Python now, Clojure middleware later
           └─ idp.py            ← thin HTTP wrapper, stays Python
```

The Middle Graph pattern (from CLAUDE.md §7) is implemented here in Python
as `lens/collibra.py`. When the Clojure middleware layer matures it will
absorb this responsibility; the `CollibraLens.transform()` contract will
stay the same.

---

## Reading order if you are new

1. **`command.py`** — read `build_parser()` for the full command tree, then
   pick one `cmd_*` function and trace what it calls.
2. **Run** `singine bridge build && singine bridge search "electricity"` to
   see the SQLite index respond.
3. **`operating_model.py`** — read the dataclasses before touching anything
   Collibra-related.
4. **`lens/README.md`** — understand what a lens is before reading
   `lens/collibra.py`.
5. **`idp.py`** — understand the session model before reading `auth_totp.py`.
6. **`../singine/CLAUDE.md`** (repo root) — the full architecture vision,
   migration plan, and glossary. Read this to understand *why* things are
   structured the way they are.
