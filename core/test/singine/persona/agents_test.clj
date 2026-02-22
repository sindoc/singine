(ns singine.persona.agents-test
  "Tests for persona archetypes.
   Every persona must produce a legitimate conscious agent
   that survives extended operation."
  (:require [clojure.test :refer [deftest testing is are]]
            [singine.persona.agents :as p]
            [singine.consciousness.markov :as m]))

(deftest world-states-test
  (testing "7 universal world states"
    (is (= 7 (count p/world-states)))
    (is (some #{:tranquil} p/world-states))
    (is (some #{:ambiguous} p/world-states))))

(deftest experience-states-test
  (testing "7 universal experience states"
    (is (= 7 (count p/experience-states)))
    (is (some #{:calm} p/experience-states))
    (is (some #{:confused} p/experience-states))))

(deftest action-states-test
  (testing "7 universal action states"
    (is (= 7 (count p/action-states)))
    (is (some #{:observe} p/action-states))
    (is (some #{:disambiguate} p/action-states))
    (is (some #{:connect} p/action-states))))

;; ════════════════════════════════════════════════════════════════════
;; Per-persona legitimacy: the critical invariant
;; ════════════════════════════════════════════════════════════════════

(defn test-persona-legitimacy
  "Generic test: instantiate a persona and verify all kernels."
  [constructor-fn persona-name]
  (let [agent (constructor-fn)]
    (testing (str persona-name " P kernel is legitimate")
      (is (m/legitimate? (:P agent))))
    (testing (str persona-name " D kernel is legitimate")
      (is (m/legitimate? (:D agent))))
    (testing (str persona-name " A kernel is legitimate")
      (is (m/legitimate? (:A agent))))
    (testing (str persona-name " has correct state spaces")
      (is (= p/experience-states (:X agent)))
      (is (= p/action-states (:G agent)))
      (is (= p/world-states (:W agent))))))

(deftest philosopher-legitimacy-test
  (test-persona-legitimacy p/philosopher-agent "philosopher"))

(deftest guardian-legitimacy-test
  (test-persona-legitimacy p/guardian-agent "guardian"))

(deftest explorer-legitimacy-test
  (test-persona-legitimacy p/explorer-agent "explorer"))

(deftest healer-legitimacy-test
  (test-persona-legitimacy p/healer-agent "healer"))

(deftest networker-legitimacy-test
  (test-persona-legitimacy p/networker-agent "networker"))

;; ════════════════════════════════════════════════════════════════════
;; Survival test: run each persona for N steps
;; ════════════════════════════════════════════════════════════════════

(defn test-persona-survival
  "Run a persona for n steps and verify no legitimacy failure."
  [constructor-fn persona-name n]
  (let [agent (constructor-fn)]
    (testing (str persona-name " survives " n " steps")
      (loop [w :tranquil i 0]
        (when (< i n)
          (let [r (m/step agent w)]
            (is (:legitimate r)
                (str persona-name " lost legitimacy at step " i))
            (recur (:new-world r) (inc i))))))))

(deftest philosopher-survival-test
  (test-persona-survival p/philosopher-agent "philosopher" 200))

(deftest guardian-survival-test
  (test-persona-survival p/guardian-agent "guardian" 200))

(deftest explorer-survival-test
  (test-persona-survival p/explorer-agent "explorer" 200))

(deftest healer-survival-test
  (test-persona-survival p/healer-agent "healer" 200))

(deftest networker-survival-test
  (test-persona-survival p/networker-agent "networker" 200))

;; ════════════════════════════════════════════════════════════════════
;; Persona registry
;; ════════════════════════════════════════════════════════════════════

(deftest persona-registry-test
  (testing "all 5 personas registered"
    (is (= 5 (count p/persona-registry)))
    (is (every? #(contains? p/persona-registry %)
                [:philosopher :guardian :explorer :healer :networker])))
  (testing "each persona has required metadata"
    (doseq [[k spec] p/persona-registry]
      (is (:constructor spec) (str k " missing constructor"))
      (is (:dominant-faculty spec) (str k " missing dominant-faculty"))
      (is (:description spec) (str k " missing description")))))

(deftest instantiate-persona-test
  (testing "instantiate-persona works for all known personas"
    (doseq [k (keys p/persona-registry)]
      (let [agent (p/instantiate-persona k)]
        (is (some? agent) (str "Failed to instantiate " k))
        (is (= :conscious-agent (:type agent))))))
  (testing "unknown persona returns nil"
    (is (nil? (p/instantiate-persona :unknown)))))

;; ════════════════════════════════════════════════════════════════════
;; Cross-persona fusion
;; ════════════════════════════════════════════════════════════════════

(deftest cross-persona-fusion-test
  (testing "any two personas can fuse and remain legitimate"
    (let [pairs [[:philosopher :guardian]
                 [:explorer :healer]
                 [:networker :philosopher]
                 [:healer :guardian]]]
      (doseq [[k1 k2] pairs]
        (let [a1 (p/instantiate-persona k1)
              a2 (p/instantiate-persona k2)
              fused (m/fuse-agents a1 a2)]
          (is (m/legitimate? (:P fused))
              (str k1 "+" k2 " P not legitimate"))
          (is (m/legitimate? (:D fused))
              (str k1 "+" k2 " D not legitimate"))
          (is (m/legitimate? (:A fused))
              (str k1 "+" k2 " A not legitimate")))))))
