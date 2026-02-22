(ns singine.core.features
  "Feature flags for version-gated capabilities.

   Singine is a PIS kernel — Personal Information System kernel.
   Features are introduced across versions and can be toggled
   at runtime for safe data migration and code migration.

   Feature flags serve three purposes:
   1. Version gating: new features ship dark, enabled per-version
   2. Migration safety: old data paths remain until migration completes
   3. Rollback: if a feature breaks, disable without code change

   Each flag has:
   - :version     — the semver where it was introduced
   - :status      — :alpha | :beta | :stable | :deprecated
   - :default     — default on/off
   - :description — what it does
   - :migration   — optional migration fn to run when enabling")

;; ════════════════════════════════════════════════════════════════════
;; VERSION
;; ════════════════════════════════════════════════════════════════════

(def version
  "Current engine version. Follows semver."
  {:major 0 :minor 2 :patch 0
   :label "alpha"
   :string "0.2.0-alpha"})

(defn version>=
  "True if current version is >= the given [major minor patch]."
  [[maj min pat]]
  (let [{:keys [major minor patch]} version]
    (or (> major maj)
        (and (= major maj) (> minor min))
        (and (= major maj) (= minor min) (>= patch pat)))))

;; ════════════════════════════════════════════════════════════════════
;; FEATURE FLAG REGISTRY
;; ════════════════════════════════════════════════════════════════════

(def flag-definitions
  "All feature flags. Keys are flag names."
  {;; v0.1.0 — foundational
   :conscious-agent-loop
   {:version [0 1 0] :status :stable :default true
    :description "The P→D→A Markov kernel loop"
    :migration nil}

   :unicode-codebook
   {:version [0 1 0] :status :stable :default true
    :description "Unicode character mapping to consciousness concepts"
    :migration nil}

   :taxonomy-dag
   {:version [0 1 0] :status :stable :default true
    :description "Aristotle→Avicenna→Hoffman faculty graph"
    :migration nil}

   ;; v0.2.0 — personas and context
   :persona-agents
   {:version [0 2 0] :status :beta :default true
    :description "5 persona archetypes with distinct kernel weights"
    :migration nil}

   :agent-fusion
   {:version [0 2 0] :status :beta :default true
    :description "Tensor product composition of conscious agents"
    :migration nil}

   :context-asset-type
   {:version [0 2 0] :status :beta :default true
    :description "Context as Collibra Business Asset with disambiguation semantics"
    :migration nil}

   :context-transitions
   {:version [0 2 0] :status :alpha :default true
    :description "Markov kernel-driven context switching during epochs"
    :migration nil}

   ;; v0.3.0 — planned: PIS kernel features
   :email-ingestion
   {:version [0 3 0] :status :alpha :default false
    :description "Watch /var/mail and ingest into pipeline"
    :migration nil}

   :document-ocr
   {:version [0 3 0] :status :alpha :default false
    :description "Tess4J OCR for scanned documents"
    :migration nil}

   :rdf-triple-store
   {:version [0 3 0] :status :alpha :default false
    :description "Apache Jena TDB2 persistent triple store"
    :migration nil}

   :lucene-index
   {:version [0 3 0] :status :alpha :default false
    :description "Full-text search via Apache Lucene"
    :migration nil}

   ;; v0.4.0 — planned: middleware
   :kafka-events
   {:version [0 4 0] :status :alpha :default false
    :description "Kafka producer/consumer for event streaming"
    :migration nil}

   :edge-replication
   {:version [0 4 0] :status :alpha :default false
    :description "Docker-based edge site replication"
    :migration nil}

   :middle-graph-routing
   {:version [0 4 0] :status :alpha :default false
    :description "Collibra-style middle graph intermediary layer"
    :migration nil}})

;; ════════════════════════════════════════════════════════════════════
;; RUNTIME STATE
;; ════════════════════════════════════════════════════════════════════

(defonce ^:private flag-overrides
  (atom {}))

(defn enabled?
  "Check if a feature flag is enabled.
   Resolution order:
   1. Runtime override (set via enable!/disable!)
   2. Version gate (flag only available if version >= flag version)
   3. Default value from definition"
  [flag-key]
  (if (contains? @flag-overrides flag-key)
    (get @flag-overrides flag-key)
    (if-let [flag (get flag-definitions flag-key)]
      (and (version>= (:version flag))
           (:default flag))
      false)))

(defn enable!
  "Force-enable a feature flag at runtime."
  [flag-key]
  (swap! flag-overrides assoc flag-key true))

(defn disable!
  "Force-disable a feature flag at runtime."
  [flag-key]
  (swap! flag-overrides assoc flag-key false))

(defn reset-overrides!
  "Clear all runtime overrides, returning to defaults."
  []
  (reset! flag-overrides {}))

(defn flags-status
  "Return the current state of all flags."
  []
  (into (sorted-map)
        (map (fn [[k v]]
               [k {:enabled (enabled? k)
                   :status  (:status v)
                   :version (clojure.string/join "." (:version v))}])
             flag-definitions)))

;; ════════════════════════════════════════════════════════════════════
;; MIGRATION SUPPORT
;; ════════════════════════════════════════════════════════════════════

(defn run-migration!
  "Execute the migration function for a feature flag, if any.
   Returns {:ok true} or {:error ...}."
  [flag-key]
  (if-let [flag (get flag-definitions flag-key)]
    (if-let [migrate-fn (:migration flag)]
      (try
        (migrate-fn)
        {:ok true :flag flag-key}
        (catch Exception e
          {:error (.getMessage e) :flag flag-key}))
      {:ok true :flag flag-key :note "no migration needed"})
    {:error "unknown flag" :flag flag-key}))

;; ════════════════════════════════════════════════════════════════════
;; CONDITIONAL EXECUTION MACRO
;; ════════════════════════════════════════════════════════════════════

(defmacro when-feature
  "Execute body only if the feature flag is enabled.
   Usage: (when-feature :agent-fusion (fuse-agents a1 a2))"
  [flag-key & body]
  `(when (enabled? ~flag-key)
     ~@body))
