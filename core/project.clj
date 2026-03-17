;; singine/core/project.clj — Leiningen project for the singine-core JVM layer.
;;
;; This file provides a Leiningen-compatible entry point alongside the primary
;; Clojure CLI (deps.edn) and the Ant/Maven/Gradle build files.
;;
;; JVM selection: set $JAVA_HOME before invoking lein.
;;   JAVA_HOME=/usr/lib/jvm/java-21-openjdk lein javac
;;
;; cacerts:
;;   SINGINE_CACERTS=/etc/pki/ca-trust/extracted/java/cacerts lein test
;;
;; Key tasks:
;;   lein javac            compile Java sources → classes/
;;   lein test             run Clojure test suite
;;   lein run -m singine.local.SingineLocalIntegrationTest   run 15-TC integration test
;;   lein javadoc-xml      generate Norman Walsh XML Javadoc (delegates to ant)
;;   lein docker-centos    build and run CentOS LTS Docker test

(defproject com.sindoc/singine-core "0.2.0"
  :description "Singine JVM core: Activity model, authentication (JwsToken, CertAuthority),
               local network layer (singine.local:2000), and Apache Camel EIP backbone."
  :url "https://github.com/sindoc/singine"

  :license {:name "Proprietary — Sina Khakbaz / sindoc"
            :url  "https://sina.khakbaz.com"}

  ;; ── Source paths ────────────────────────────────────────────────────────

  :source-paths   ["src"]
  :java-source-paths ["java"]
  :resource-paths ["resources"]
  :compile-path   "classes"
  :target-path    "target/lein"
  :test-paths     ["test"]

  ;; ── Dependencies ────────────────────────────────────────────────────────

  :dependencies
  [[org.clojure/clojure                "1.12.0"]
   [org.clojure/data.json              "2.5.1"]
   [org.clojure/tools.logging          "1.3.0"]
   [org.xerial/sqlite-jdbc             "3.45.3.0"]

   ;; Apache Camel 4.4 LTS
   [org.apache.camel/camel-core        "4.4.4"]
   [org.apache.camel/camel-mail        "4.4.4"]
   [org.apache.camel/camel-http        "4.4.4"]
   [org.apache.camel/camel-jetty       "4.4.4"]
   [org.apache.camel/camel-jackson     "4.4.4"]

   ;; Jakarta Mail
   [jakarta.mail/jakarta.mail-api      "2.1.3"]
   [org.eclipse.angus/angus-mail       "2.0.3"]

   ;; Commons
   [org.apache.commons/commons-lang3   "3.14.0"]
   [commons-io/commons-io              "2.15.1"]
   [commons-codec/commons-codec        "1.17.0"]]

  ;; xmldoclet — provided scope (used only for javadoc-xml generation)
  :profiles
  {:xmldoclet {:dependencies [[com.saxonica/xmldoclet "0.17.0"]]}
   :centos    {:plugins [[lein-shell "0.5.0"]]}
   :dev       {:source-paths ["test"]}}

  ;; ── Java compilation ─────────────────────────────────────────────────────

  ;; lein-javac: respects $JAVA_HOME via :javac-options
  :javac-options ["-target" "11" "-source" "11" "-encoding" "UTF-8"]

  ;; ── JVM options ──────────────────────────────────────────────────────────

  ;; Pass cacerts path and singine.local settings to the test/run JVM.
  ;; Override with: SINGINE_CACERTS=/path/to/cacerts lein test
  :jvm-opts
  ~(let [cacerts  (or (System/getenv "SINGINE_CACERTS")
                      (str (or (System/getenv "JAVA_HOME")
                               (System/getProperty "java.home"))
                           "/conf/security/cacerts"))]
     [(str "-Djavax.net.ssl.trustStore=" cacerts)
      "-Dsingine.local.host=singine.local"
      "-Dsingine.local.port=2000"
      "-Dfile.encoding=UTF-8"])

  ;; ── Aliases ──────────────────────────────────────────────────────────────

  :aliases
  {"test-local"
   ["run" "-m" "singine.local.SingineLocalIntegrationTest"]

   ;; Delegate XML Javadoc to Ant (uses xmldoclet auto-detection from ~/.m2)
   "javadoc-xml"
   ["shell" "ant" "-f" "build.xml" "javadoc-xml"]

   ;; Build and run CentOS LTS Docker tests
   "docker-centos"
   ["shell" "ant" "-f" "build.xml" "test-centos"]

   ;; Provision JVM environment via Ansible
   "ansible-jvm"
   ["shell" "ant" "-f" "build.xml" "ansible-jvm"]}

  ;; ── Manifest ─────────────────────────────────────────────────────────────

  :manifest
  {"Singine-Version"    "0.2.0"
   "Singine-Local-Port" "2000"
   "Singine-Local-Host" "singine.local"
   "Built-By"           "leiningen"})
