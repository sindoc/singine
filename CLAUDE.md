# CLAUDE.md - Singine Platform Development Context

## Terms of Reference

This document captures the full architectural vision for Singine as a multi-layer platform. All terms below are canonical references for development.

**Key Concepts**: Admin document processing, Paperwork digitisation, OCR pipeline, Intermediary format indexing, RDF triples as interoperability layer, SPARQL + natural language querying, Cosine similarity, Disjoint sets (Union-Find) for entity equality, Self-executing lambdas for late execution, Middle Graphs (Collibra metamodel), Model Context Protocol (MCP) as meta-programming protocol, URI/URL generation for resource identification, Edge site message brokering, Logseq graph projection to SQLite, Kafka event streaming, Quantum-compatible abstractions (qbit environments).

---

## 1. Project Overview

**Singine** is a multi-layer platform built around a core engine that processes admin documents (paperwork), indexes their content, and exposes it through a knowledge graph queryable via both SPARQL and natural language.

The platform originated as a Unix-idiomatic CLI tool for Logseq todo management and is evolving into a full document processing and data governance engine with Collibra metamodel compatibility.

### Current State (v0.2.0)

The project has an existing Python codebase (`singine/`) with:
- Logseq markdown parser, temporal algebra, SQL-like query language
- RDF/OWL semantic layer (DCAT, PROV, ODRL, TIME, FOAF, SCHEMA)
- Collibra Operating Model abstraction, Lens framework
- Contract model with scenario analysis, FIBO integration
- Knowledge graph with multi-source loading

### Target State

A polyglot platform with Clojure at the centre, orchestrating document ingestion, event processing, and knowledge graph queries across distributed edge nodes.

---

## 2. Architecture Layers

Each layer is an independent project. All report to Electron as the presentation shell.

```
+------------------------------------------------------------------+
|                        ELECTRON SHELL                             |
|  (Desktop app, renders all layers, single unified interface)      |
+------------------------------------------------------------------+
         |           |           |           |           |
+--------+--+ +------+-----+ +--+-------+ +-+--------+ +--+-------+
| FRONTEND  | | CLI LAYER   | | SDK      | | MIDDLEWARE| | BACKEND  |
| (UI/UX)   | | (singine    | | (Public  | | (Middle  | | (Storage,|
|            | |  commands)  | |  API for | |  Graph,  | |  Events, |
|            | |             | |  3rd     | |  Routing,| |  Kafka,  |
|            | |             | |  party)  | |  Certs)  | |  Docker) |
+------------+ +-------------+ +---------+ +----------+ +----------+
         |           |           |           |           |
+------------------------------------------------------------------+
|                         CORE LAYER                                |
|  (Clojure: Document processing, OCR, indexing, RDF, SPARQL,      |
|   temporal algebra, query engine, Union-Find, embeddings)         |
+------------------------------------------------------------------+
         |
+------------------------------------------------------------------+
|                    JVM ABSTRACTION LAYER                           |
|  (Java, Python via Jython/GraalPy, NodeJS via GraalJS)           |
+------------------------------------------------------------------+
```

### Layer Responsibilities

| Layer | Language | Responsibility |
|-------|----------|----------------|
| **Core** | Clojure | Document processing, OCR pipeline, RDF triple generation, SPARQL engine, temporal algebra, query language, Union-Find entity resolution, embeddings, cosine similarity |
| **CLI** | Clojure/Python | `singine` command-line interface (existing Python CLI continues as a bridge) |
| **SDK** | Clojure | Public API for third-party integration, URI/URL generation for MCP resources |
| **Middleware** | Clojure | Middle Graph routing, certificate management, event dispatch, Collibra Edge brokering |
| **Backend** | Clojure + Docker | Kafka consumers/producers, SQLite projection, email ingestion (`/var/mail`), HTTPS API |
| **Frontend** | ClojureScript | Electron-hosted UI, Logseq graph visualisation |

---

## 3. Immediate Objective: Local Email Ingestion

**Goal**: Route emails sent to a local address (e.g., `a@localhost`) into the Singine processing pipeline.

### Architecture

```
[External Email / sendmail] --> /var/mail/<user>
        |
        v
[Singine Mail Watcher]  (inotify/polling on /var/mail/)
        |
        v
[Kafka Producer]  --> topic: singine.inbound.email
        |
        v
[Kafka Consumer: Document Processor]
        |
        v
[Apache Tika: Extract text + metadata]
        |
        v
[Intermediary Format]
   +-- [Lucene Index]  (full-text search)
   +-- [RDF Triples]   (Apache Jena / Aristotle)
   +-- [SQLite]        (Logseq graph projection)
```

### Implementation Steps

1. Configure local MTA (Postfix/Exim) to accept mail for the local domain
2. Set up `/var/mail/<user>` as the mailbox directory
3. Create a Clojure file watcher on `/var/mail/` using `java.nio.file.WatchService`
4. Parse email content (MIME) using Apache Tika
5. Publish parsed content to Kafka topic `singine.inbound.email`
6. Consumer processes message through the OCR/indexing pipeline

---

## 4. Document Processing Pipeline (Core Focus)

### 4.1 Ingest Phase: OCR and Text Extraction

The primary focus is converting paperwork (scanned images, PDFs, email attachments) into an intermediary indexed format.

#### Recommended Open Source Libraries (JVM-compatible)

| Library | Purpose | License | Clojure Wrapper |
|---------|---------|---------|-----------------|
| **Apache Tika** | Universal document extraction (PDF, DOCX, email, images, 1000+ formats) | Apache 2.0 | Java interop |
| **Tess4J** | OCR engine (JNA wrapper for Tesseract) | Apache 2.0 | clj-ocr |
| **Apache PDFBox** | PDF text extraction + PDF-to-image rendering | Apache 2.0 | Java interop |
| **JavaCV/OpenCV** | Image pre-processing (deskew, denoise, binarise) | Apache 2.0 / BSD | Java interop |

#### Pipeline

```
[Scanned Image / PDF / Email]
        |
        v
[Pre-processing: JavaCV]   -- deskew, denoise, binarise, rescale to 300 DPI
        |
        v
[OCR: Tess4J / Tesseract]  -- image to text
        |
        v
[Extraction: Apache Tika]  -- text + Dublin Core metadata
        |
        v
[Intermediary Format]       -- indexed, queryable content
```

### 4.2 Transform Phase: Intermediary Format

The extracted text and metadata are stored in two complementary formats:

| Format | Library | Purpose |
|--------|---------|---------|
| **Full-text index** | Apache Lucene (via Clucy or lucene-clj) | Token-based search, fuzzy matching |
| **RDF triple store** | Apache Jena TDB2 (via Aristotle) | Structured knowledge graph, SPARQL queries |
| **SQLite projection** | SQLite (via JDBC) | Logseq graph projection, relational queries |
| **Vector embeddings** | DJL + ONNX Runtime (via clj-djl) | Cosine similarity, semantic search |

### 4.3 Query Phase: SPARQL + Natural Language

Two query strategies, selectable based on query type:

**Strategy A: SPARQL (Structured Queries)**
- For known attributes: date, sender, document type, amount
- Uses Apache Jena ARQ engine
- Clojure data structures as SPARQL queries (via Aristotle)

**Strategy B: Cosine Similarity (Semantic Queries)**
- For content-based questions: "What does clause 3 say about termination?"
- Document chunks embedded via sentence-transformers (DJL + ONNX Runtime)
- Query embedded the same way, cosine similarity finds relevant chunks

**Strategy C: Natural Language to SPARQL (LLM Translation)**
- User asks in natural language
- LLM translates to SPARQL query
- Executed against Jena triple store

---

## 5. Computation Model: Self-Executing Lambdas

Activities in Singine are modelled as self-executing lambdas to enable late execution (deferred evaluation).

```clojure
;; Activity as a self-executing lambda with late binding
(defn make-activity [name f]
  {:name name
   :execute (fn [ctx] (f ctx))
   :status (atom :pending)})

;; Activities compose into pipelines
(defn pipeline [& activities]
  (fn [ctx]
    (reduce (fn [ctx' act]
              (reset! (:status act) :running)
              (let [result ((:execute act) ctx')]
                (reset! (:status act) :completed)
                result))
            ctx activities)))
```

### Disjoint Sets for Entity Equality (Union-Find)

Entity resolution uses Union-Find to determine when two extracted entities refer to the same real-world object:

```clojure
(defn make-union-find []
  (let [parent (atom {})
        find (fn find [x]
               (let [p (get @parent x x)]
                 (if (= p x) x
                   (let [root (find p)]
                     (swap! parent assoc x root)
                     root))))
        union (fn [x y]
                (let [rx (find x) ry (find y)]
                  (when (not= rx ry)
                    (swap! parent assoc rx ry))))]
    {:find find :union union :equal? (fn [x y] (= (find x) (find y)))}))
```

---

## 6. RDF Interoperability Layer

### Standard Vocabularies

| Prefix | Vocabulary | Usage |
|--------|-----------|-------|
| `rdf:` | RDF | Core triple model |
| `rdfs:` | RDF Schema | Class/property hierarchy |
| `owl:` | OWL | Ontology definitions |
| `dcat:` | Data Catalog Vocabulary | Dataset descriptions |
| `prov:` | Provenance Ontology | Activity/agent tracking |
| `odrl:` | Open Digital Rights Language | Intent-based authorisation |
| `time:` | Time Ontology | Temporal constraints |
| `foaf:` | Friend of a Friend | People and relationships |
| `schema:` | Schema.org | General entity descriptions |
| `skos:` | SKOS | Concept hierarchies |
| `dcterms:` | Dublin Core Terms | Document metadata (Tika outputs this natively) |
| `fibo:` | Financial Industry Business Ontology | Financial entities |
| `singine:` | Singine Custom Namespace | Project-specific terms |

### Custom URI/URL Generation

The platform generates URIs and URLs interchangeably to identify any resource, compatible with MCP (Model Context Protocol) as a meta-programming protocol:

```
singine:<type>/<id>          -- URI form (abstract identifier)
https://singine.local/<type>/<id>  -- URL form (resolvable address)
```

Users may provide custom URIs/URLs. The system treats URI and URL as interchangeable resource identifiers.

---

## 7. Middle Graphs (Collibra Metamodel Compatibility)

Middle graphs are the integration pattern from the Collibra metamodel: they connect any source to any target through a typed, governed intermediary layer.

```
[Source A] ---> [Middle Graph] ---> [Target X]
[Source B] -/                  \--> [Target Y]
```

### Collibra Operating Model Alignment

| Collibra Concept | Singine Equivalent |
|------------------|--------------------|
| Asset Type | Document Type (Invoice, Contract, Letter, Form) |
| Domain Type | Processing Domain (Inbound Email, Scanned Doc, API Upload) |
| Relation Type | RDF predicate linking entities |
| Status Workflow | Activity state machine (pending → running → completed) |
| Community | Edge Site / Node |
| Responsibility | Certificate-bound agent identity |

### Collibra Edge Replication

Singine replicates the Collibra Edge architecture for distributed message brokering:

```
+------------------+     +------------------+     +------------------+
| Edge Site A      |     | Central Broker   |     | Edge Site B      |
| (Docker node)    |<--->| (Kafka cluster)  |<--->| (Docker node)    |
| - Local ingestion|     | - Topic routing  |     | - Local ingestion|
| - Local index    |     | - Schema registry|     | - Local index    |
| - Local RDF store|     | - Central graph  |     | - Local RDF store|
+------------------+     +------------------+     +------------------+
```

Each edge site:
- Runs in its own Docker container
- Has a local Lucene index and Jena TDB2 triple store
- Publishes events to Kafka topics
- Synchronises with the central broker
- Identified by a single TLS certificate (mapped to Unix inodes)

---

## 8. Infrastructure

### Docker Environment Strategy

```
environments/
├── dev/          # Development: local volumes, debug logging
├── prod/         # Production: persistent storage, monitoring
└── x/            # Placeholder environment (qbit: undetermined state)
```

The `x` environment represents a quantum-inspired placeholder -- an environment whose assignment is undetermined until observation (deployment decision). In quantum computing terms, it exists in superposition until collapsed to a specific configuration.

### Quantum-Compatible Abstractions

```clojure
;; Environment as a qbit: exists in superposition until observed
(defprotocol QBit
  (observe [this] "Collapse to a definite state")
  (superpose [this states] "Set possible states"))

(defrecord Environment [name state possible-states]
  QBit
  (observe [this]
    (if (= state :undetermined)
      (assoc this :state (first possible-states))
      this))
  (superpose [this states]
    (assoc this :possible-states states :state :undetermined)))

;; The x environment
(def x-env (->Environment "x" :undetermined [:dev :staging :prod :edge]))
```

### Certificate and Trust Model

A single TLS certificate is used across all nodes to create a trustworthy network:

```
[Root CA Certificate]
        |
        +-- [Node Certificate A] --> mapped to inode on host A
        +-- [Node Certificate B] --> mapped to inode on host B
        +-- [Node Certificate C] --> mapped to inode on host C
```

Each certificate maps to a Unix inode, binding cryptographic identity to filesystem identity.

### Kafka Configuration

```
Topics:
  singine.inbound.email    -- Raw email content from /var/mail
  singine.inbound.api      -- Documents uploaded via HTTPS API
  singine.processed.text   -- Extracted text + metadata
  singine.processed.triples -- Generated RDF triples
  singine.events.activity  -- Activity lifecycle events
  singine.edge.sync        -- Edge site synchronisation
```

---

## 9. Technology Stack

### Central Language: Clojure (JVM)

Clojure is the central language. It handles:
- File system communication
- Events triggered by email or HTTPS API
- Coordination between all layers
- Interaction with Logseq as the abstract graph layer

### JVM Ecosystem Access

Through the JVM, the platform has access to:

| Language | Access Method | Usage |
|----------|--------------|-------|
| Java | Native JVM | Apache Tika, PDFBox, Jena, Lucene, Kafka clients |
| Python | GraalPy / subprocess | ML models, NLP, existing singine Python code |
| NodeJS | GraalJS / subprocess | Electron integration, npm ecosystem |
| Clojure | Native | Core platform logic |

### Key Clojure Libraries

| Library | Purpose |
|---------|---------|
| **Aristotle** | Data-oriented RDF/SPARQL/OWL (wraps Apache Jena) |
| **Clucy** | Clojure interface to Lucene full-text search |
| **clj-ocr** | Tesseract OCR wrapper |
| **clj-djl** | Deep Java Library for embeddings + ML inference |
| **clj-pdf** | PDF generation |
| **clj-kafka** | Kafka producer/consumer |
| **Mount / Component** | Lifecycle management for services |

---

## 10. Existing Singine Python Codebase

The current Python implementation continues as a bridge and will be incrementally migrated to Clojure.

### Existing Modules

| Module | Purpose | Migration Priority |
|--------|---------|-------------------|
| `cli.py` | Command-line interface | Bridge (keep as Python entry point) |
| `logseq.py` | Logseq markdown parser | Core (migrate to Clojure) |
| `temporal.py` | Temporal algebra (Pendulum) | Core (migrate to Clojure) |
| `query.py` | WHERE clause parser | Core (migrate to Clojure) |
| `rdf_ontology.py` | RDF/OWL semantic layer | Core (replace with Aristotle) |
| `operating_model.py` | Collibra Operating Model | Middleware (migrate) |
| `knowledge_graph.py` | Multi-source knowledge graph | Core (migrate) |
| `lens/` | Polymorphic metamodel views | Middleware (migrate) |
| `contract_model.py` | Contract abstraction | Core (migrate) |
| `fibo_integration.py` | FIBO + game theory | SDK (migrate) |
| `config.py` | Configuration management | Backend (migrate) |

### Running the Existing CLI

```bash
cd /Users/skh/ws/singine
pip install -e .

# Configuration
# Create ~/.singine/backend.config:
# [logseq]
# graph_path = /path/to/your/logseq/graph

singine ls tasks
singine ls tasks -where 'Last Updated Date >= pastDay#"3 months"'
singine ls tasks -where 'Priority = A'
```

---

## 11. AI Strategies for Document Querying

### Embedding-Based Retrieval (RAG)

1. Chunk extracted document text (by paragraph or fixed token window)
2. Generate embeddings using sentence-transformers via DJL/ONNX Runtime
3. Store embeddings alongside Lucene index
4. At query time: embed the question, find top-k chunks by cosine similarity
5. Optionally feed chunks to an LLM for answer synthesis

### Knowledge Graph Augmented Retrieval

1. Extract entities and relationships from documents using NLP
2. Store as RDF triples in Jena TDB2
3. At query time: translate natural language to SPARQL (via LLM or rule-based)
4. Execute SPARQL, return structured results
5. Combine with embedding-based results for hybrid answers

### Entity Resolution via Disjoint Sets

When processing multiple documents, the same entity may appear under different names. Union-Find resolves these:

1. Extract entity mentions from each document
2. Compare mentions pairwise using cosine similarity of embeddings
3. If similarity > threshold, union the two mentions
4. All mentions in the same set are treated as the same entity
5. The equality function: `(fn [a b] (= (find a) (find b)))`

---

## 12. Development Workflow

### Project Structure (Target)

```
singine/
├── core/                   # Clojure: document processing, RDF, SPARQL, query engine
│   ├── project.clj
│   └── src/singine/core/
├── cli/                    # Clojure + Python bridge: command-line interface
├── sdk/                    # Clojure: public API, URI generation, MCP
├── middleware/              # Clojure: Middle Graph, routing, certificates, Edge
├── backend/                # Clojure + Docker: Kafka, SQLite, email ingestion
├── frontend/               # ClojureScript: Electron UI
├── singine/                # Python: existing codebase (bridge, gradual migration)
├── environments/
│   ├── dev/
│   ├── prod/
│   └── x/
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── certs/                  # Single root CA + node certificates
├── docs/
└── CLAUDE.md               # This file
```

### Quick Commands

```bash
# Existing Python CLI
pip install -e .
singine ls tasks

# Future Clojure core
cd core && lein repl

# Docker environment
docker-compose -f docker/docker-compose.yml up -d

# Kafka
docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092
```

---

## 13. Glossary

| Term | Definition |
|------|-----------|
| **Middle Graph** | Integration pattern from Collibra metamodel; a typed intermediary graph connecting any source to any target |
| **Edge Site** | A distributed node (Docker container) that ingests documents locally and syncs with the central broker |
| **Self-Executing Lambda** | An activity modelled as a closure that captures its execution context and defers evaluation until invoked |
| **Disjoint Set (Union-Find)** | Data structure for tracking entity equivalence classes; the equality function `(= (find a) (find b))` |
| **Cosine Similarity** | Measure of angular distance between embedding vectors; used for semantic document search |
| **Intermediary Format** | The indexed representation of a document after OCR/extraction: Lucene index + RDF triples + SQLite |
| **qbit Environment** | An environment in superposition (undetermined assignment) until deployment collapses it to a specific configuration |
| **MCP** | Model Context Protocol; a meta-programming protocol for resource identification via URIs/URLs |
| **Temporal Algebra** | Singine's natural language date expression system: `pastDay#"3 months"`, `day#"last Monday"` |
| **Lens** | A polymorphic view that transforms heterogeneous data sources into a target metamodel |
| **Logseq Graph Projection** | Mapping a Logseq markdown graph onto a SQLite database for relational queries |

---

## 14. Build Order (Priority)

### Phase 1: Email Ingestion (Current)
1. Configure local MTA for mail delivery to `/var/mail/`
2. Implement Clojure file watcher on mailbox
3. Set up Kafka with `singine.inbound.email` topic
4. Parse email MIME content via Apache Tika
5. Store extracted text in Lucene index

### Phase 2: Document Processing Pipeline
1. Integrate Tess4J for OCR on scanned attachments
2. Implement RDF triple generation via Aristotle/Jena
3. Set up Jena TDB2 persistent triple store
4. Build SPARQL query interface

### Phase 3: Middleware and Edge
1. Implement Middle Graph routing
2. Set up certificate infrastructure (single root CA)
3. Docker containerisation of edge sites
4. Kafka-based edge synchronisation

### Phase 4: SDK and Frontend
1. Public Clojure SDK with URI/URL generation
2. MCP-compatible resource identification
3. Electron shell with ClojureScript frontend
4. Logseq graph visualisation

---

**Last Updated**: 2026-02-07
**Project Status**: Alpha (v0.2.0) -- Transitioning from Python to Clojure
**Primary Developer**: skh
