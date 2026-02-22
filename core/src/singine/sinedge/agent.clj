(ns singine.sinedge.agent
  "sinedge-agent — NL → SPARQL → MCP gateway. User-facing.
   Installed at: ~/.local/opt/singine/sinedge/
   Opcode: SNAG   URN: urn:singine:asset:SNAG

   The agent is the only user-visible interface besides MCP.
   It translates natural language queries to SPARQL, executes them
   against the Jena triple store, and returns structured results
   addressable via MCP URNs.

   Pipeline (user sees only the top and bottom):
     [natural language] → nl-to-sparql → run-sparql → mcp-dispatch → [result]

   Snap queries:
     (snap-query \"what phone number is in this screenshot?\")
     → SPARQL over the Lucene/Jena index of the OCR'd content
     → {:result \"+32 476 55 14 38\" :confidence 0.97 :source :snap-ocr}

   All backend calls are structured OpenAPI calls (schema/sinedge-api.yaml).
   The agent never exposes raw HTTP to the user — only SPARQL + MCP."
  (:require [clojure.string :as str]))

;; ── NL → SPARQL translation ──────────────────────────────────────────────────
;; In production: LLM call (Ollama / OpenAI / Claude).
;; Here: rule-based placeholder that is correct for the snap use-case.

(def ^:private nl-patterns
  "Ordered list of [regex sparql-template] pairs.
   First match wins — Markov-oracle style: most specific pattern first."
  [[#"(?i)phone|number|tel"
    "SELECT ?val WHERE { ?doc snap:phoneNumber ?val }"]
   [#"(?i)name|person|who"
    "SELECT ?val WHERE { ?doc snap:personName ?val }"]
   [#"(?i)email|address|@"
    "SELECT ?val WHERE { ?doc snap:emailAddress ?val }"]
   [#"(?i)username|handle|@"
    "SELECT ?val WHERE { ?doc snap:username ?val }"]
   [#"(?i)uri|url|urn|link"
    "SELECT ?val WHERE { ?doc snap:uri ?val }"]
   [#"(?i)date|when|time"
    "SELECT ?val WHERE { ?doc dcterms:date ?val }"]
   [#"(?i)amount|total|sum|money|€|\\$|£"
    "SELECT ?val WHERE { ?doc snap:amount ?val }"]
   [#"(?i).*"
    "SELECT ?doc ?pred ?val WHERE { ?doc ?pred ?val } LIMIT 20"]])

(defn nl-to-sparql
  "Translate a natural language query string to SPARQL.
   Returns {:sparql string :strategy :nl-to-sparql :matched-pattern regex}."
  [^String query]
  (let [[pat sparql] (first (filter (fn [[pat _]] (re-find pat query)) nl-patterns))]
    {:sparql          sparql
     :strategy        :nl-to-sparql
     :nl-input        query
     :matched-pattern (str pat)}))

;; ── SPARQL execution stub ────────────────────────────────────────────────────
;; In production: Jena ARQ against TDB2 triple store.

(defn run-sparql
  "Execute a SPARQL query string against the Jena triple store.
   Returns a seq of result maps {:binding {:var value ...}}.
   Stub: returns a placeholder result with the query echoed back."
  [sparql & {:keys [limit] :or {limit 20}}]
  {:sparql  sparql
   :results []                        ;; Jena ARQ results go here
   :limit   limit
   :backend :jena-tdb2
   :status  :stub})

;; ── MCP dispatch ─────────────────────────────────────────────────────────────

(defn mcp-dispatch
  "Wrap SPARQL results as MCP-addressable resources.
   Each result gets a URN of the form:
     urn:singine:snap:<doc-id>/<predicate>"
  [sparql-result]
  {:mcp-resources
   (mapv (fn [r]
           {:urn  (str "urn:singine:snap/" (hash r))
            :data r})
         (get sparql-result :results []))
   :strategy :mcp
   :source   sparql-result})

;; ── cosine search stub ───────────────────────────────────────────────────────

(defn cosine-search
  "Embed query, find top-k chunks by cosine similarity.
   Stub: returns the query echoed with a placeholder ranking."
  [^String query & {:keys [top-k] :or {top-k 5}}]
  {:query  query
   :top-k  top-k
   :chunks []       ;; DJL embedding results go here
   :strategy :cosine
   :status :stub})

;; ── snap-query: the user-facing entry point ──────────────────────────────────

(defn snap-query
  "The main entry point for a snap-process natural language query.

   Usage:
     (snap-query \"what phone number is in this screenshot?\")

   Pipeline:
     NL → SPARQL → Jena → MCP resources

   Returns:
     {:nl-input :sparql :sparql-result :mcp-resources :strategy}"
  [^String nl-query]
  (let [translation   (nl-to-sparql nl-query)
        sparql-result (run-sparql (:sparql translation))
        mcp           (mcp-dispatch sparql-result)]
    (merge translation
           {:sparql-result sparql-result
            :mcp-resources (:mcp-resources mcp)})))

;; ── lifecycle ────────────────────────────────────────────────────────────────

(defn start!
  [& {:keys [install-root] :or {install-root "~/.local/opt/singine/sinedge"}}]
  {:agent     "sinedge-agent"
   :urn       "urn:singine:sinedge:agent"
   :install   install-root
   :interface [:sparql :mcp :nl]
   :status    :started})
