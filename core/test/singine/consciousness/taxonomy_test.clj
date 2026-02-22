(ns singine.consciousness.taxonomy-test
  "Tests for the consciousness taxonomy DAG.
   Validates structural integrity of the Aristotle→Avicenna→Hoffman lineage."
  (:require [clojure.test :refer [deftest testing is are]]
            [singine.consciousness.taxonomy :as t]))

(deftest levels-test
  (testing "five ontological levels in correct order"
    (is (= [:mineral :vegetative :animal :rational :intellectual] t/levels))
    (is (= 5 (count t/levels)))))

(deftest level-properties-test
  (testing "every level has properties defined"
    (doseq [l t/levels]
      (is (contains? t/level-properties l)
          (str "Missing properties for level " l))))
  (testing "self-awareness progresses through levels"
    (is (false? (:self-awareness (:mineral t/level-properties))))
    (is (false? (:self-awareness (:vegetative t/level-properties))))
    (is (= :partial (:self-awareness (:animal t/level-properties))))
    (is (true? (:self-awareness (:rational t/level-properties))))))

(deftest faculty-graph-structure-test
  (testing "consciousness is root — has no parents"
    (is (nil? (:parents (:consciousness t/faculty-graph)))))
  (testing "every non-root faculty has parents"
    (doseq [[k v] t/faculty-graph
            :when (not= k :consciousness)]
      (is (seq (:parents v))
          (str "Faculty " k " has no parents"))))
  (testing "parent references point to existing faculties"
    (doseq [[k v] t/faculty-graph
            parent (:parents v)]
      (is (contains? t/faculty-graph parent)
          (str "Faculty " k " references non-existent parent " parent))))
  (testing "children references point to existing faculties"
    (doseq [[k v] t/faculty-graph
            child (:children v)]
      (is (contains? t/faculty-graph child)
          (str "Faculty " k " references non-existent child " child)))))

(deftest parent-child-symmetry-test
  (testing "if A lists B as child, B lists A as parent"
    (doseq [[k v] t/faculty-graph
            child (:children v)]
      (let [child-node (get t/faculty-graph child)]
        (is (some #{k} (:parents child-node))
            (str k " lists " child " as child, but "
                 child " does not list " k " as parent"))))))

(deftest kernel-signatures-test
  (testing "every faculty has a kernel signature"
    (doseq [[k v] t/faculty-graph]
      (is (vector? (:kernel-sig v))
          (str "Faculty " k " has no kernel signature"))
      (is (= 2 (count (:kernel-sig v)))
          (str "Faculty " k " kernel sig should be [from to]")))))

(deftest ancestors-test
  (testing "root has no ancestors"
    (is (empty? (t/ancestors :consciousness))))
  (testing "sight traces back to consciousness"
    (let [anc (t/ancestors :sight)]
      (is (contains? anc :external-senses))
      (is (contains? anc :sensitive-soul))
      (is (contains? anc :consciousness))))
  (testing "estimation (Avicenna) traces to internal-senses"
    (let [anc (t/ancestors :estimation)]
      (is (contains? anc :internal-senses)))))

(deftest descendants-test
  (testing "consciousness has all three soul types as descendants"
    (let [desc (t/descendants :consciousness)]
      (is (contains? desc :nutritive-soul))
      (is (contains? desc :sensitive-soul))
      (is (contains? desc :rational-soul))))
  (testing "leaf nodes have no descendants"
    (is (empty? (t/descendants :sight)))
    (is (empty? (t/descendants :memory)))))

(deftest faculties-at-level-test
  (testing "vegetative level has nutritive faculties"
    (let [veg (t/faculties-at-level :vegetative)]
      (is (contains? veg :nutritive-soul))
      (is (contains? veg :growth))))
  (testing "animal level has sensitive faculties"
    (let [animal (t/faculties-at-level :animal)]
      (is (contains? animal :sensitive-soul))
      (is (contains? animal :sight))
      (is (contains? animal :estimation)))))

(deftest thinker-attribution-test
  (testing "Aristotle credited for foundational faculties"
    (is (= :aristotle (:thinker (:nutritive-soul t/faculty-graph))))
    (is (= :aristotle (:thinker (:sensitive-soul t/faculty-graph))))
    (is (= :aristotle (:thinker (:rational-soul t/faculty-graph)))))
  (testing "Avicenna credited for internal senses"
    (is (= :avicenna (:thinker (:internal-senses t/faculty-graph))))
    (is (= :avicenna (:thinker (:estimation t/faculty-graph))))
    (is (= :avicenna (:thinker (:self-awareness t/faculty-graph)))))
  (testing "Hoffman credited for conscious agent formalism"
    (is (= :hoffman (:thinker (:conscious-agent t/faculty-graph))))
    (is (= :hoffman (:thinker (:perception-kernel t/faculty-graph))))))
