(ns singine.sinedge.engine
  "sinedge-engine — governed lambda executor.
   Installed at: ~/.local/opt/singine/sinedge/
   Opcode: SNGE   URN: urn:singine:asset:SNGE

   The engine is the backend half of the sinedge pair.
   It receives governed lambda payloads from sinedge-agent
   (via Kafka topic singine.inbound.request) and executes them
   after auth validation. Results go to singine.outbound.response.

   The engine never surfaces SPARQL or MCP to the caller —
   those are sinedge-agent concerns. The engine sees only:
     {:auth {...} :lambda-fn fn :args [...] :t SingineTime}

   Exceptions
   ──────────
   All JVM exceptions are caught and wrapped as ex-info with
   :stage, :opcode, and :cause. Racket callers see only Clojure values."
  (:require [singine.pos.lambda :as lam]))

;; ── execution registry ───────────────────────────────────────────────────────
;; Maps opcode → governed thunk factory.
;; Each factory: (fn [auth args] -> thunk)

(def ^:private registry (atom {}))

(defn register!
  "Register a governed lambda factory for an opcode.
   factory: (fn [auth args] -> zero-arg thunk)"
  [opcode factory]
  (swap! registry assoc opcode factory))

(defn execute!
  "Look up opcode in the registry, build the governed thunk, and call it.
   Returns the thunk result or {:denied ...} or {:error ...}."
  [opcode auth args]
  (if-let [factory (get @registry opcode)]
    (try
      (let [thunk (factory auth args)]
        (thunk))
      (catch Exception e
        {:error true :opcode opcode :cause (.getMessage e)}))
    {:error true :opcode opcode :cause "opcode not registered"}))

;; ── built-in registrations ───────────────────────────────────────────────────

;; SNAP — snapshot processing pipeline stub
(register! "SNAP"
  (fn [auth args]
    (lam/govern auth
      (fn [t]
        {:opcode "SNAP"
         :args   args
         :time   (select-keys t [:iso :path :decade])
         :stages [:ingest :preprocess :ocr :extract :index :triple :nl-query :dispatch]
         :status :queued}))))

;; SNGE — engine self-report
(register! "SNGE"
  (fn [auth _args]
    (lam/govern auth
      (fn [t]
        {:opcode  "SNGE"
         :status  :running
         :install "~/.local/opt/singine/sinedge"
         :time    (select-keys t [:iso :path])}))))

;; ── lifecycle ────────────────────────────────────────────────────────────────

(defn start!
  "Start the sinedge-engine. In production: listens on Kafka.
   In dev: returns a map describing the engine state."
  [& {:keys [install-root] :or {install-root "~/.local/opt/singine/sinedge"}}]
  {:engine      "sinedge-engine"
   :urn         "urn:singine:sinedge:engine"
   :install     install-root
   :opcodes     (keys @registry)
   :kafka-in    "singine.inbound.request"
   :kafka-out   "singine.outbound.response"
   :status      :started})
