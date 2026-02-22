(ns singine.pos.category
  "Category C (CATC opcode) — the categorical structure of singine POS.

   Category C = (Objects, Subjects, Predicates, Morphisms)
   ─────────────────────────────────────────────────────────
   Objects   = asset types from root.xml + {:object-kind :conscious-agent} sentinel
   Subjects  = governed lambdas carrying [[t/1]] / urn:singine:topic:t/1
   Predicates = PredicateFactory/make → SingingPredicate with #lang singine header
   Morphisms  = governed thunks with triple-calendar timestamp

   Dimension (pivot):
     dim = (count (distinct (map :block contexts)))
     → proto/c   (dim=1, edge :s)
     → proto/cc  (dim=2, edge :m)
     → proto/ccc (dim=3+, edge :l)

   Activity gate (Jenkins/Flowable pattern):
     (log-ready?) → ≥3 entries in activity-log atom

   Kafka checkpoint (Europe/London):
     (checkpoint-due?) → London minute ∈ [0,1) ∪ [30,31)

   Topic anchor: [[t/1]] / urn:singine:topic:t/1"
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [singine.meta.root    :as root]
            [clojure.string       :as str])
  (:import [singine.pos PredicateFactory]
           [java.time ZonedDateTime ZoneId]))

;; ── Activity log (Jenkins/Flowable gate) ─────────────────────────────────────

(def ^:private activity-log
  "Atom accumulating activity entries. Gate opens at ≥3 entries."
  (atom []))

(defn log-activity!
  "Append an activity entry to the log. Returns entry count after append."
  [entry]
  (count (swap! activity-log conj (assoc entry :ts (str (java.time.Instant/now))))))

(defn log-ready?
  "True if the activity log has ≥3 entries (Jenkins/Flowable gate)."
  []
  (>= (count @activity-log) 3))

(defn reset-log!
  "Clear the activity log. Used in tests."
  []
  (reset! activity-log []))

;; ── Kafka checkpoint (Europe/London :00/:30) ──────────────────────────────────

(defn checkpoint-due?
  "True if the current Europe/London minute is in [0,1) ∪ [30,31).
   Mirrors Kafka flush at top-of-hour and half-hour."
  []
  (let [zdt    (ZonedDateTime/now (ZoneId/of "Europe/London"))
        minute (.getMinute zdt)]
    (or (zero? minute) (= 30 minute))))

;; ── Edge dim mapping ─────────────────────────────────────────────────────────

(defn edge-dim
  "Map edge-size keyword to Category C dimension.
   :s → 1 (proto/c), :m → 2 (proto/cc), :l → 3 (proto/ccc).
   Also accepts an integer directly."
  [contract-or-int]
  (if (integer? contract-or-int)
    (max 1 contract-or-int)
    (case (:edge-size contract-or-int)
      :s 1
      :m 2
      :l 3
      1)))

;; ── Predicates (Category C morphisms) ────────────────────────────────────────

(defn make-predicate
  "Create a SingingPredicate via PredicateFactory.
   Returns {:predicate <SingingPredicate> :header <#lang singine header>}"
  [name condition]
  (let [p (PredicateFactory/make name condition)]
    {:predicate p
     :header    (.header p)
     :name      (.name p)
     :condition (.condition p)}))

(def predicate-registry
  "Standard predicates for Category C morphisms."
  (delay
    {:has-opcode   (make-predicate "has-opcode"   "has-opcode")
     :is-agent     (make-predicate "is-agent"     "is-agent")
     :is-governed  (make-predicate "is-governed"  "is-governed")
     :has-mime     (make-predicate "has-mime"     "has-mime")
     :is-material  (make-predicate "is-material"  "is-material")
     :is-signed    (make-predicate "is-signed"    "is-signed")
     :default      (make-predicate "default"      "default")}))

(defn apply-predicate
  "Apply a named predicate from the registry to a subject map.
   Returns true/false."
  [pred-key subject-map]
  (if-let [entry (get @predicate-registry pred-key)]
    (.test (:predicate entry) subject-map)
    true))

;; ── Objects — asset types + conscious agent sentinel ─────────────────────────

(defn objects
  "Return Category C objects: all root.xml asset types plus the conscious-agent sentinel."
  []
  (let [asset-types (try (root/asset-types) (catch Exception _ []))]
    (conj asset-types {:object-kind :conscious-agent
                       :opcode      "AGNT"
                       :name        "ConsciousAgent"
                       :description "Hoffman 6-tuple conscious agent"})))

;; ── Subjects — governed lambda descriptors ────────────────────────────────────

(defn subjects
  "Return Category C subjects: maps describing governed lambdas with [[t/1]] anchor."
  [processed-blocks]
  (mapv (fn [b]
          {:subject-kind    :governed-lambda
           :block-n         (:block-n b)
           :topic           "[[t/1]]"
           :urn             "urn:singine:topic:t/1"
           :contexts        (count (:contexts b))
           :is-governed     true
           :opcode          "BLKP"})
        processed-blocks))

;; ── Morphisms — the category's arrows ────────────────────────────────────────

(defn morphism
  "Construct a morphism from source object to target subject, gated by predicate.
   Returns {:from :to :predicate-name :allowed :calendars}"
  [from-opcode to-block pred-key]
  (let [subject-map {"opcode"      (:opcode from-opcode "")
                     "governed"    true
                     "type"        "conscious-agent"
                     "material-cat" "masterdata"
                     "contract-signed" true
                     "mime-type"   "application/json"}
        allowed     (apply-predicate pred-key (java.util.HashMap. subject-map))]
    {:from           (:opcode from-opcode "UNKN")
     :to             (:block-n to-block "0")
     :predicate-name (name pred-key)
     :allowed        allowed
     :calendars      (cal/now-triple)}))

;; ── MIME routing ─────────────────────────────────────────────────────────────

(def mime-routes
  "Map MIME type patterns to routing keywords."
  {"text/plain"                  :lookup
   "text/csv"                    :lookup
   "application/json"            :lookup
   "application/xml"             :lookup
   "application/rdf+xml"         :link
   "application/sparql-query"    :link
   "text/turtle"                 :link
   "image/png"                   :binary
   "image/jpeg"                  :binary
   "application/pdf"             :binary
   "application/octet-stream"    :binary
   "application/zip"             :binary})

(defn mime-route
  "Classify a MIME type into :lookup, :link, or :binary route."
  [mime-type]
  (or (get mime-routes mime-type)
      (cond
        (str/starts-with? (or mime-type "") "text/")        :lookup
        (str/starts-with? (or mime-type "") "application/") :lookup
        :else                                                :binary)))

;; ── activate! — governed Category C activation ───────────────────────────────

(defn activate!
  "Governed entry point for CATC opcode.
   Activates Category C over the processed blocks from BLKP.

   Returns a zero-arg thunk per govern contract.

   Output map:
     {:ok :dim :objects :subjects :morphisms :predicates :calendars
      :log-ready :checkpoint-due :time}"
  [auth processed-blocks]
  (lam/govern auth
    (fn [t]
      (let [objs  (objects)
            subs  (subjects processed-blocks)
            dim   (max 1 (count (distinct (mapcat #(mapv :block (:contexts %)) processed-blocks))))
            preds (keys @predicate-registry)

            ;; Seed activity log with boot events
            _ (when (empty? @activity-log)
                (log-activity! {:event "timestamp-self"  :source "exec.rkt"})
                (log-activity! {:event "singine-ls-tasks" :source "shell-history"})
                (log-activity! {:event "singine-inspect"  :source "shell-history"}))

            ready?  (log-ready?)
            chkpt?  (checkpoint-due?)

            morphisms
            (when ready?
              (for [obj  (take 3 objs)
                    sub  (take 3 subs)
                    pred [:is-governed :has-opcode :is-material]]
                (morphism obj sub pred)))]

        {:ok             true
         :dim            dim
         :edge-dir       (cond (= dim 1) "proto/c"
                               (= dim 2) "proto/cc"
                               :else     "proto/ccc")
         :objects        (mapv #(select-keys % [:opcode :name]) objs)
         :subjects       subs
         :predicates     (mapv (fn [k]
                                 (let [e (get @predicate-registry k)]
                                   {:key  (name k)
                                    :name (:name e)
                                    :header (:header e)}))
                               preds)
         :morphisms      (vec morphisms)
         :log-ready      ready?
         :checkpoint-due chkpt?
         :calendars      (cal/now-triple)
         :topic          "[[t/1]]"
         :urn            "urn:singine:topic:t/1"
         :time           (select-keys t [:iso :path])}))))
