(ns singine.loc.action
  "Location-Action Correlation (LAC) engine — governed pipeline.

   Correlates a location (IATA / ZIP / country code) with an action
   (email, task, decision, approval) and evaluates feasibility based on:
     · Time constraints  — is the deadline within an acceptable window?
     · Space constraints — is the target within a radius from a reference?
     · Impact score      — is the urgency × severity below the threshold?

   All functions return governed thunks via `lam/govern`.

   Entry points:
     (correlate! auth opts)         — full pipeline → decision map
     (impact!    auth opts)         — impact score only
     (decide!    auth opts threshold) — gate: publish decision to Kafka

   Use case:
     'Correlate location and action data to make a decision based on
      the impact and constraints — both time and space constraints.'

   Kafka topic: singine.events.decision

   URN: urn:singine:loc:action"
  (:require [singine.pos.lambda  :as lam]
            [singine.broker.core :as broker]
            [singine.pos.location :as loc-probe]
            [clojure.string      :as str])
  (:import [singine.loc ConstraintEvaluator]))

;; ── java-map->clj (local, recursive) ─────────────────────────────────────────

(defn- java-map->clj [m]
  (cond
    (instance? java.util.Map m)
    (reduce (fn [acc [k v]] (assoc acc (keyword k) (java-map->clj v))) {} m)
    (instance? java.util.List m)
    (mapv java-map->clj m)
    :else m))

;; ── Action URN builder ────────────────────────────────────────────────────────

(defn- action-urn
  "Build a URN for an action.
   urn:singine:action:<type>:<uuid>"
  [action-type]
  (str "urn:singine:action:" (name (or action-type :task)) ":"
       (str (java.util.UUID/randomUUID))))

;; ── correlate! ────────────────────────────────────────────────────────────────

(defn correlate!
  "Correlate a location with an action and evaluate feasibility.

   Returns a governed thunk yielding a decision map:
   {:feasible bool
    :location-urn str
    :action-urn   str
    :time-window  {:feasible bool :hours-remaining N ...}
    :space-window {:feasible bool :distance-km N ...}
    :impact       {:impact-score N :breach-probability N ...}
    :decision     {:feasible bool :reason str :decision-id str ...}
    :time         {:iso str :path str}}

   opts:
     :location        — IATA code, ISO-2 country, or ZIP (string)
     :action          — map: {:type :task|:email|:decision|:approval
                               :deadline-iso ISO-8601 string (optional)
                               :agent-type :human|:machine|:collaborative
                               :entity-count N (default 1)}
     :time-constraint — map: {:from-iso ISO-8601 :to-iso ISO-8601} (optional)
     :space-constraint— map: {:reference-iata str :radius-km N} (optional)
     :impact-threshold — double 0.0–1.0 (default 0.8)
     :dry-run          — boolean (default false)"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [{:keys [location action time-constraint space-constraint
                    impact-threshold dry-run]
             :or   {impact-threshold 0.8 dry-run false}} opts
            ;; Location resolution
            location-urn  (or (get-in opts [:location-urn])
                              (str "urn:singine:location:XX:" (str/upper-case (or location "UNK"))))
            ;; Action params
            action-type   (get action :type :task)
            deadline-iso  (get action :deadline-iso "")
            agent-type    (get action :agent-type "human")
            entity-count  (int (get action :entity-count 1))
            act-urn       (action-urn action-type)
            ;; Time constraint evaluation
            from-iso  (get time-constraint :from-iso "")
            to-iso    (get time-constraint :to-iso "")
            time-res  (java-map->clj
                        (ConstraintEvaluator/evaluateTimeWindow from-iso to-iso deadline-iso))
            ;; Space constraint evaluation
            ref-iata  (get space-constraint :reference-iata (str/upper-case (or location "BRU")))
            radius-km (double (get space-constraint :radius-km 500.0))
            ;; Target IATA = same as reference when not specified (always feasible)
            tgt-iata  (get space-constraint :target-iata ref-iata)
            space-res (java-map->clj
                        (ConstraintEvaluator/evaluateSpaceRadius ref-iata tgt-iata radius-km))
            ;; Impact scoring
            deadline-close? (< (or (:hours-remaining time-res) 999) 24)
            impact-res (java-map->clj
                         (ConstraintEvaluator/scoreImpact
                           (name action-type) (name agent-type)
                           entity-count deadline-close?))
            ;; Final decision
            decision   (java-map->clj
                         (ConstraintEvaluator/decide
                           (into {} (map (fn [[k v]] [(name k) v]) time-res))
                           (into {} (map (fn [[k v]] [(name k) v]) space-res))
                           (into {} (map (fn [[k v]] [(name k) v]) impact-res))
                           impact-threshold))]
        {:feasible     (:feasible decision)
         :location-urn location-urn
         :action-urn   act-urn
         :time-window  time-res
         :space-window space-res
         :impact       impact-res
         :decision     decision
         :dry-run      dry-run
         :time         (select-keys t [:iso :path])}))))

;; ── impact! ───────────────────────────────────────────────────────────────────

(defn impact!
  "Estimate impact score for an action. Returns a governed thunk.
   Does NOT evaluate time/space constraints — just the impact heuristic.

   opts: {:action-type :task|:email|:decision|:approval
           :agent-type  :human|:machine|:collaborative
           :entity-count N
           :deadline-close? bool}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [{:keys [action-type agent-type entity-count deadline-close?]
             :or   {action-type :task agent-type :human
                    entity-count 1 deadline-close? false}} opts
            result (java-map->clj
                     (ConstraintEvaluator/scoreImpact
                       (name action-type) (name agent-type)
                       (int entity-count) (boolean deadline-close?)))]
        (assoc result :time (select-keys t [:iso :path]))))))

;; ── decide! ───────────────────────────────────────────────────────────────────

(defn decide!
  "Gate: evaluate correlate! then publish decision to Kafka if not dry-run.
   Returns a governed thunk.

   On feasible=true: publishes JSON to singine.events.decision Kafka topic.
   On feasible=false: publishes to dead-letter queue singine.broker.dead.

   opts: same as correlate!
   threshold: maximum acceptable impact (default 0.8)"
  [auth opts threshold]
  (lam/govern auth
    (fn [t]
      (let [threshold (or threshold 0.8)
            correlation ((correlate! auth (assoc opts :impact-threshold threshold)))
            decision    (:decision correlation)
            feasible    (:feasible decision)
            ;; Build Kafka event body
            event-body  (str "{\"decision-id\":\"" (:decision-id decision) "\""
                             ",\"location-urn\":\"" (:location-urn correlation) "\""
                             ",\"action-urn\":\"" (:action-urn correlation) "\""
                             ",\"feasible\":" (if feasible "true" "false")
                             ",\"impact-score\":" (:impact-score (:impact correlation))
                             ",\"reason\":\"" (str/replace (str (:reason decision)) "\"" "'") "\""
                             ",\"decided-at\":\"" (:decided-at decision) "\"}")
            ;; Publish to Kafka (dry-run if requested)
            dry-run     (:dry-run opts false)
            topic       (if feasible :events-decision :broker-dead)
            broker-result ((broker/publish! auth
                             {:broker  :kafka
                              :topic   topic
                              :body    event-body
                              :dry-run dry-run}))]
        (assoc correlation
               :published       (:ok broker-result)
               :topic           (name topic)
               :broker-checksum (:checksum broker-result)
               :time            (select-keys t [:iso :path]))))))
