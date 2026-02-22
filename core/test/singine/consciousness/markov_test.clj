(ns singine.consciousness.markov-test
  "Tests for Markov kernels — the mathematical foundation.
   If these fail, nothing above them can be trusted."
  (:require [clojure.test :refer [deftest testing is are]]
            [singine.consciousness.markov :as m]))

;; ════════════════════════════════════════════════════════════════════
;; KERNEL CONSTRUCTION
;; ════════════════════════════════════════════════════════════════════

(deftest normalize-row-test
  (testing "normalizes to sum 1"
    (let [row (m/normalize-row [1 2 3 4])]
      (is (< (Math/abs (- 1.0 (reduce + row))) 1e-9))))
  (testing "zero row becomes uniform"
    (let [row (m/normalize-row [0 0 0])]
      (is (every? #(< (Math/abs (- % (/ 1.0 3))) 1e-9) row))))
  (testing "already normalized stays same"
    (let [row (m/normalize-row [0.5 0.3 0.2])]
      (is (< (Math/abs (- 0.5 (first row))) 1e-9)))))

(deftest make-kernel-test
  (testing "creates legitimate kernel from raw matrix"
    (let [k (m/make-kernel [:a :b] [:x :y]
                           [[3 7] [5 5]])]
      (is (m/legitimate? k))
      (is (= [:a :b] (:from-states k)))
      (is (= [:x :y] (:to-states k)))))
  (testing "dimension mismatch throws"
    (is (thrown? AssertionError
          (m/make-kernel [:a :b] [:x :y :z]
                         [[1 2] [3 4]])))))

;; ════════════════════════════════════════════════════════════════════
;; LEGITIMACY — the invariant that keeps the engine alive
;; ════════════════════════════════════════════════════════════════════

(deftest legitimacy-test
  (testing "properly normalized kernel is legitimate"
    (let [k (m/make-kernel [:a :b] [:x :y]
                           [[0.6 0.4] [0.3 0.7]])]
      (is (m/legitimate? k))))
  (testing "any kernel from make-kernel is legitimate by construction"
    (let [k (m/make-kernel [:a :b :c] [:x :y :z]
                           [[1 1 1] [0 0 0] [5 3 2]])]
      (is (m/legitimate? k)))))

;; ════════════════════════════════════════════════════════════════════
;; TRANSITION PROBABILITY
;; ════════════════════════════════════════════════════════════════════

(deftest transition-prob-test
  (testing "returns correct probability"
    (let [k (m/make-kernel [:a :b] [:x :y]
                           [[0.6 0.4] [0.3 0.7]])]
      (is (< (Math/abs (- 0.6 (m/transition-prob k :a :x))) 1e-9))
      (is (< (Math/abs (- 0.7 (m/transition-prob k :b :y))) 1e-9))))
  (testing "unknown state returns nil"
    (let [k (m/make-kernel [:a] [:x] [[1.0]])]
      (is (nil? (m/transition-prob k :z :x))))))

;; ════════════════════════════════════════════════════════════════════
;; SAMPLING — stochastic output must stay in-bounds
;; ════════════════════════════════════════════════════════════════════

(deftest sample-transition-test
  (testing "sample always returns a valid to-state"
    (let [k (m/make-kernel [:a :b] [:x :y :z]
                           [[0.2 0.3 0.5] [0.1 0.8 0.1]])]
      (dotimes [_ 100]
        (is (contains? #{:x :y :z} (m/sample-transition k :a)))
        (is (contains? #{:x :y :z} (m/sample-transition k :b))))))
  (testing "deterministic kernel always returns same state"
    (let [k (m/make-kernel [:a] [:x :y] [[1.0 0.0]])]
      (dotimes [_ 50]
        (is (= :x (m/sample-transition k :a)))))))

;; ════════════════════════════════════════════════════════════════════
;; ENTROPY
;; ════════════════════════════════════════════════════════════════════

(deftest entropy-test
  (testing "deterministic row has zero entropy"
    (is (< (m/entropy [1.0 0.0 0.0]) 1e-9)))
  (testing "uniform row has maximum entropy"
    (let [n 4
          uniform (vec (repeat n (/ 1.0 n)))
          max-ent (Math/log n)]
      (is (< (Math/abs (- max-ent (m/entropy uniform))) 1e-9))))
  (testing "kernel entropy is average of row entropies"
    (let [k (m/make-kernel [:a :b] [:x :y]
                           [[1.0 0.0] [0.5 0.5]])]
      (is (> (m/kernel-entropy k) 0.0)))))

;; ════════════════════════════════════════════════════════════════════
;; CONSCIOUS AGENT — the 6-tuple
;; ════════════════════════════════════════════════════════════════════

(deftest make-agent-test
  (testing "creates valid agent with all components"
    (let [a (m/make-agent [:x1 :x2] [:g1 :g2] [:w1 :w2]
                          [[0.6 0.4] [0.3 0.7]]
                          [[0.5 0.5] [0.8 0.2]]
                          [[0.7 0.3] [0.4 0.6]])]
      (is (= :conscious-agent (:type a)))
      (is (= [:x1 :x2] (:X a)))
      (is (= [:g1 :g2] (:G a)))
      (is (= [:w1 :w2] (:W a)))
      (is (m/legitimate? (:P a)))
      (is (m/legitimate? (:D a)))
      (is (m/legitimate? (:A a)))
      (is (= 0 @(:N a)))
      (is @(:legitimate a)))))

(deftest step-test
  (testing "step produces valid output and increments N"
    (let [a (m/make-agent [:x1 :x2] [:g1 :g2] [:w1 :w2]
                          [[0.6 0.4] [0.3 0.7]]
                          [[0.5 0.5] [0.8 0.2]]
                          [[0.7 0.3] [0.4 0.6]])
          result (m/step a :w1)]
      (is (= :w1 (:world result)))
      (is (contains? #{:x1 :x2} (:experience result)))
      (is (contains? #{:g1 :g2} (:action result)))
      (is (contains? #{:w1 :w2} (:new-world result)))
      (is (= 1 (:n result)))
      (is (:legitimate result))))
  (testing "100 steps maintain legitimacy"
    (let [a (m/make-agent [:x1 :x2] [:g1 :g2] [:w1 :w2]
                          [[0.6 0.4] [0.3 0.7]]
                          [[0.5 0.5] [0.8 0.2]]
                          [[0.7 0.3] [0.4 0.6]])]
      (loop [w :w1 i 0]
        (when (< i 100)
          (let [r (m/step a w)]
            (is (:legitimate r) (str "Lost legitimacy at step " i))
            (recur (:new-world r) (inc i))))))))

;; ════════════════════════════════════════════════════════════════════
;; AGENT COMPOSITION / FUSION
;; ════════════════════════════════════════════════════════════════════

(deftest compose-kernels-test
  (testing "identity-like composition preserves structure"
    (let [k1 (m/make-kernel [:a :b] [:m :n]
                            [[0.6 0.4] [0.3 0.7]])
          k2 (m/make-kernel [:m :n] [:x :y]
                            [[0.5 0.5] [0.8 0.2]])
          composed (m/compose-kernels k1 k2)]
      (is (m/legitimate? composed))
      (is (= [:a :b] (:from-states composed)))
      (is (= [:x :y] (:to-states composed))))))

(deftest fuse-agents-test
  (testing "fused agent is itself a conscious agent"
    (let [a1 (m/make-agent [:x1 :x2] [:g1 :g2] [:w1 :w2]
                           [[0.6 0.4] [0.3 0.7]]
                           [[0.5 0.5] [0.8 0.2]]
                           [[0.7 0.3] [0.4 0.6]])
          a2 (m/make-agent [:y1 :y2] [:h1 :h2] [:w1 :w2]
                           [[0.4 0.6] [0.5 0.5]]
                           [[0.3 0.7] [0.6 0.4]]
                           [[0.8 0.2] [0.2 0.8]])
          fused (m/fuse-agents a1 a2)]
      (is (= :conscious-agent (:type fused)))
      ;; Cartesian product: 2×2 = 4 experience states
      (is (= 4 (count (:X fused))))
      (is (= 4 (count (:G fused))))
      ;; Shared world preserved
      (is (= [:w1 :w2] (:W fused)))
      ;; All kernels legitimate
      (is (m/legitimate? (:P fused)))
      (is (m/legitimate? (:D fused)))
      (is (m/legitimate? (:A fused)))
      ;; Fused agent can step
      (let [r (m/step fused :w1)]
        (is (:legitimate r))))))
