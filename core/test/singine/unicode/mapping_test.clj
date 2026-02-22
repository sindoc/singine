(ns singine.unicode.mapping-test
  "Tests for the Unicode-to-consciousness codebook.
   Validates completeness, uniqueness, and Collibra alignment."
  (:require [clojure.test :refer [deftest testing is are]]
            [singine.unicode.mapping :as u]))

(deftest codebook-not-empty-test
  (testing "codebook has substantial entries"
    (is (> (count u/codebook) 40)
        "Codebook should have 40+ entries")))

(deftest unique-concepts-test
  (testing "no two characters map to the same concept"
    (let [concepts (map :concept (vals u/codebook))
          dupes (filter (fn [[_ v]] (> v 1)) (frequencies concepts))]
      (is (empty? dupes)
          (str "Duplicate concepts: " (keys dupes))))))

(deftest unique-characters-test
  (testing "every key in codebook is a distinct character"
    (is (= (count u/codebook)
           (count (set (keys u/codebook)))))))

(deftest every-entry-has-required-fields-test
  (testing "all entries have code, concept, description"
    (doseq [[ch m] u/codebook]
      (is (:code m) (str "Missing :code for " ch))
      (is (:concept m) (str "Missing :concept for " ch))
      (is (:description m) (str "Missing :description for " ch)))))

(deftest hoffman-symbols-present-test
  (testing "all six Hoffman components are mapped"
    (let [concepts (set (map :concept (vals u/markov-kernel-symbols)))]
      (is (contains? concepts :experience-space))
      (is (contains? concepts :action-space))
      (is (contains? concepts :perception-kernel))
      (is (contains? concepts :decision-kernel))
      (is (contains? concepts :action-kernel))
      (is (contains? concepts :world-space))
      (is (contains? concepts :iteration)))))

(deftest aristotle-faculties-present-test
  (testing "three soul types are mapped"
    (let [concepts (set (map :concept (vals u/aristotle-faculties)))]
      (is (contains? concepts :nutritive-soul))
      (is (contains? concepts :sensitive-soul))
      (is (contains? concepts :rational-soul)))))

(deftest avicenna-five-internal-senses-test
  (testing "all five internal senses are mapped"
    (let [concepts (set (map :concept (vals u/avicenna-faculties)))]
      (is (contains? concepts :sensus-communis))
      (is (contains? concepts :retentive-imagination))
      (is (contains? concepts :compositive-imagination))
      (is (contains? concepts :estimation))
      (is (contains? concepts :memory)))))

(deftest lookup-test
  (testing "lookup by character returns entry"
    (let [entry (u/lookup \u0398)]
      (is (some? entry))
      (is (= :perception-kernel (:concept entry))))))

(deftest by-concept-test
  (testing "reverse lookup finds character"
    (is (some? (u/by-concept :perception-kernel)))
    (is (some? (u/by-concept :estimation)))))

(deftest by-thinker-test
  (testing "can filter by thinker"
    (let [aristotle-entries (u/by-thinker :aristotle)]
      (is (> (count aristotle-entries) 5)))
    (let [avicenna-entries (u/by-thinker :avicenna)]
      (is (> (count avicenna-entries) 5)))))

(deftest collibra-type-present-test
  (testing "entries with thinker attribution have collibra-type"
    (doseq [[ch m] (merge u/aristotle-faculties u/avicenna-faculties)]
      (is (:collibra-type m)
          (str "Missing :collibra-type for " (:concept m))))))

(deftest wikipedia-references-test
  (testing "thinker-attributed entries have WP references"
    (doseq [[ch m] (merge u/aristotle-faculties u/avicenna-faculties)]
      (is (:wp m)
          (str "Missing :wp for " (:concept m))))))

(deftest codebook-table-test
  (testing "table format returns sorted sequence"
    (let [table (u/codebook-table)]
      (is (seq table))
      (is (every? :char table))
      (is (every? :concept table)))))
