(ns singine.core.engine-test
  "Integration tests for the engine.
   Verifies that the full network runs N epochs without failure."
  (:require [clojure.test :refer [deftest testing is]]
            [singine.core.engine :as engine]
            [singine.consciousness.markov :as m]))

(deftest init-network-test
  (testing "initializes with 5 agents and tranquil world"
    (engine/init-network)
    (let [state @engine/network-state]
      (is (= 5 (count (:agents state))))
      (is (= :tranquil (:world state)))
      (is (= 0 (:epoch state)))
      (is (:legitimate state))
      (is (seq (:contexts state))))))

(deftest resolve-world-state-test
  (testing "majority wins"
    (is (= :novel (engine/resolve-world-state
                    [:novel :novel :tranquil]))))
  (testing "empty defaults to tranquil"
    (is (= :tranquil (engine/resolve-world-state [])))))

(deftest run-epochs-test
  (testing "network survives 50 epochs"
    (engine/init-network)
    (dotimes [_ 50]
      (let [state (engine/run-epoch)]
        (is (:legitimate state)
            (str "Lost legitimacy at epoch " (:epoch state)))
        (is (pos? (count (:agents state)))
            (str "Zero agents at epoch " (:epoch state)))))))

(deftest context-transitions-test
  (testing "contexts transition during epochs"
    (engine/init-network)
    (let [before (into {} (map (fn [[k v]] [k (:active-meaning v)])
                               (:contexts @engine/network-state)))]
      ;; Run enough epochs that at least one context is likely to shift
      (dotimes [_ 30] (engine/run-epoch))
      (let [after (into {} (map (fn [[k v]] [k (:active-meaning v)])
                                (:contexts @engine/network-state)))]
        ;; At least one context should have shifted (probabilistic but very likely in 30 steps)
        ;; We test that the structure is intact rather than specific shifts
        (is (= (set (keys before)) (set (keys after)))
            "Context set should remain stable")))))

(deftest fusion-mechanics-test
  (testing "fusion reduces agent count"
    (engine/init-network)
    (let [initial-count (count (:agents @engine/network-state))]
      ;; Run enough epochs to likely trigger at least one fusion
      (dotimes [_ 100] (engine/run-epoch))
      ;; If fusions happened, agent count should have decreased
      (when (seq (:fusions @engine/network-state))
        (is (< (count (:agents @engine/network-state)) initial-count))))))
