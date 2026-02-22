(ns singine.core.features-test
  "Tests for the feature flag system.
   Validates version gating, overrides, and migration safety."
  (:require [clojure.test :refer [deftest testing is use-fixtures]]
            [singine.core.features :as f]))

(use-fixtures :each
  (fn [test-fn]
    (f/reset-overrides!)
    (test-fn)
    (f/reset-overrides!)))

(deftest version-test
  (testing "version is well-formed"
    (is (string? (:string f/version)))
    (is (nat-int? (:major f/version)))
    (is (nat-int? (:minor f/version)))
    (is (nat-int? (:patch f/version)))))

(deftest version>=-test
  (testing "current version passes its own check"
    (is (f/version>= [(:major f/version)
                       (:minor f/version)
                       (:patch f/version)])))
  (testing "future version fails"
    (is (not (f/version>= [99 0 0])))))

(deftest stable-flags-enabled-test
  (testing "v0.1.0 stable flags are enabled by default"
    (is (f/enabled? :conscious-agent-loop))
    (is (f/enabled? :unicode-codebook))
    (is (f/enabled? :taxonomy-dag))))

(deftest beta-flags-enabled-test
  (testing "v0.2.0 beta flags are enabled (we are v0.2.0)"
    (is (f/enabled? :persona-agents))
    (is (f/enabled? :agent-fusion))
    (is (f/enabled? :context-asset-type))))

(deftest future-flags-disabled-test
  (testing "v0.3.0+ flags are disabled (not yet at that version)"
    (is (not (f/enabled? :email-ingestion)))
    (is (not (f/enabled? :document-ocr)))
    (is (not (f/enabled? :kafka-events)))))

(deftest override-test
  (testing "enable! forces a flag on"
    (is (not (f/enabled? :email-ingestion)))
    (f/enable! :email-ingestion)
    (is (f/enabled? :email-ingestion)))
  (testing "disable! forces a flag off"
    (is (f/enabled? :conscious-agent-loop))
    (f/disable! :conscious-agent-loop)
    (is (not (f/enabled? :conscious-agent-loop)))))

(deftest reset-overrides-test
  (testing "reset clears all overrides"
    (f/enable! :email-ingestion)
    (f/disable! :conscious-agent-loop)
    (f/reset-overrides!)
    (is (not (f/enabled? :email-ingestion)))
    (is (f/enabled? :conscious-agent-loop))))

(deftest unknown-flag-test
  (testing "unknown flags return false"
    (is (not (f/enabled? :nonexistent-flag)))))

(deftest flags-status-test
  (testing "returns map of all flags with status"
    (let [status (f/flags-status)]
      (is (map? status))
      (is (contains? status :conscious-agent-loop))
      (is (boolean? (:enabled (:conscious-agent-loop status)))))))

(deftest when-feature-macro-test
  (testing "when-feature executes body when enabled"
    (is (= 42 (f/when-feature :conscious-agent-loop 42))))
  (testing "when-feature returns nil when disabled"
    (is (nil? (f/when-feature :email-ingestion 42)))))

(deftest migration-test
  (testing "flag with no migration returns ok"
    (let [result (f/run-migration! :conscious-agent-loop)]
      (is (:ok result))))
  (testing "unknown flag returns error"
    (let [result (f/run-migration! :nonexistent)]
      (is (:error result)))))

(deftest all-flags-have-required-fields-test
  (testing "every flag has version, status, default, description"
    (doseq [[k v] f/flag-definitions]
      (is (vector? (:version v)) (str k " missing :version"))
      (is (#{:alpha :beta :stable :deprecated} (:status v))
          (str k " invalid :status"))
      (is (some? (:default v)) (str k " missing :default"))
      (is (string? (:description v)) (str k " missing :description")))))
