(ns singine.collibra.context-test
  "Tests for Context as a Collibra Business Asset type.
   Validates disambiguation mechanics, entropy, stability."
  (:require [clojure.test :refer [deftest testing is are]]
            [singine.collibra.context :as ctx]))

(deftest context-asset-type-test
  (testing "asset type is properly defined"
    (is (= "Context" (:name ctx/context-asset-type)))
    (is (= "Business Asset" (:parent-type ctx/context-asset-type)))
    (is (seq (:attributes ctx/context-asset-type)))
    (is (seq (:relations ctx/context-asset-type)))
    (is (seq (:status-workflow ctx/context-asset-type)))))

(deftest make-context-test
  (testing "creates context with disambiguation set"
    (let [c (ctx/make-context "Test"
              ["meaning-a" "meaning-b" "meaning-c"])]
      (is (= "Test" (:name c)))
      (is (= 3 (count (:disambiguation-set c))))
      (is (= "meaning-a" (:active-meaning c)))
      (is (= :context (:type c)))
      (is (= "Active" (:status c)))))
  (testing "default kernel is row-stochastic"
    (let [c (ctx/make-context "Test" ["a" "b" "c"])]
      (doseq [row (:kernel c)]
        (is (< (Math/abs (- 1.0 (reduce + row))) 1e-9)
            "Each row must sum to 1")))))

(deftest context-entropy-test
  (testing "low ambiguity context has low entropy"
    (let [c (ctx/make-context "Clear"
              ["only-meaning" "unlikely" "very-unlikely"]
              :kernel [[0.95 0.03 0.02]
                       [0.10 0.80 0.10]
                       [0.10 0.10 0.80]])]
      (is (< (ctx/context-entropy c) 1.0))))
  (testing "uniform context has higher entropy"
    (let [n 3
          uniform (/ 1.0 n)
          c (ctx/make-context "Ambiguous"
              ["a" "b" "c"]
              :kernel (vec (repeat n (vec (repeat n uniform)))))]
      (is (> (ctx/context-entropy c) 1.0)))))

(deftest context-stability-test
  (testing "diagonal-heavy context is stable"
    (let [c (ctx/make-context "Stable"
              ["primary" "secondary"]
              :kernel [[0.9 0.1] [0.1 0.9]])]
      (is (> (ctx/context-stability c) 0.8))))
  (testing "off-diagonal-heavy context is unstable"
    (let [c (ctx/make-context "Unstable"
              ["flip" "flop"]
              :kernel [[0.2 0.8] [0.8 0.2]])]
      (is (< (ctx/context-stability c) 0.3)))))

(deftest switch-context-test
  (testing "switching always produces valid meaning"
    (let [c (ctx/make-context "Test" ["a" "b" "c"])]
      (dotimes [_ 100]
        (let [switched (ctx/switch-context c)]
          (is (contains? (set (:disambiguation-set c))
                         (:active-meaning switched))))))))

(deftest canonical-contexts-test
  (testing "canonical contexts exist"
    (is (= 6 (count ctx/canonical-contexts))))
  (testing "each canonical context has Wikipedia reference"
    (doseq [c ctx/canonical-contexts]
      (is (:wp-page c)
          (str "Missing wp-page for " (:name c)))))
  (testing "consciousness context has all expected meanings"
    (let [c (first ctx/canonical-contexts)]
      (is (= "Consciousness" (:name c)))
      (is (= 5 (count (:disambiguation-set c)))))))
