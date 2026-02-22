(ns singine.sindoc.parser-test
  "Tests for the sindoc parser bridge.
   Uses the exact sample from the original .42.sindoc specification."
  (:require [clojure.test        :refer [deftest is testing]]
            [clojure.string      :as str]
            [singine.sindoc.parser :as sp]))

(def sample-sindoc
  "#lang racket
I need to write a Racket compiler for Clojure
 This way, I can access my JVM world.
  I don't need repititive characters to make my
  comments beautiful.
 My almost sole requirement is that I can start here,
 #...
 @...
 [a-x]
  [آ -> ی]
--
<timestamp/>
--
</>")

(deftest test-parse-sample
  (testing "parse the canonical .sindoc sample to XML"
    (let [doc (sp/parse-string sample-sindoc :hint "42.sindoc")
          xml (sp/to-xml-string doc)]
      ;; Root element present
      (is (str/includes? xml "<document"))
      ;; lang attribute captured
      (is (str/includes? xml "lang=\"racket\""))
      ;; source-file attribute set
      (is (str/includes? xml "source-file=\"42.sindoc\""))
      ;; separator section exists
      (is (str/includes? xml "<separator"))
      ;; timestamp element exists
      (is (str/includes? xml "<timestamp"))
      ;; close element exists
      (is (str/includes? xml "<close"))
      ;; body prose preserved
      (is (str/includes? xml "Racket compiler"))
      (println "\n── Parsed XML ──────────────────────────────────")
      (println xml)
      (println "────────────────────────────────────────────────"))))

(deftest test-document->map
  (testing "document->map returns a navigable Clojure structure"
    (let [doc (sp/parse-string sample-sindoc :hint "42.sindoc")
          m   (sp/document->map doc)]
      (is (= :document (:tag m)))
      (is (= "racket" (get-in m [:attrs :lang])))
      (is (vector? (:children m)))
      (let [tags (map :tag (filter map? (:children m)))]
        (is (some #(= :header %) tags))
        (is (some #(= :body %) tags))
        (is (some #(= :section %) tags))))))

(deftest test-meta-loader
  (testing "MetaLoader finds rules from the .meta hierarchy"
    (let [loader (sp/make-loader
                  :workspace-root "/Users/skh/ws/singine"
                  :project-root   "/Users/skh/ws/singine/core")]
      ;; The loader itself is a Java object; verify it doesn't throw
      (is (some? loader))
      ;; Verify rules were loaded (reflect via Clojure interop)
      (let [rules (.getRules loader)]
        (is (pos? (.size rules)))
        (println "\n── Loaded meta rules ──────────────────────────")
        (doseq [r rules]
          (printf "  %s:%s → xml-element=%s%n"
                  (.kind r) (.name r)
                  (get (.props r) "xml-element" (.name r))))
        (println "────────────────────────────────────────────────")))))
