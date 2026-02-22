(ns singine.net.cacert
  "JVM trusted certificate authority management for the Singine IdP.

   Wraps singine.auth.CertAuthority (Java) to provide:
     1. List all trusted root CAs from the JVM's cacerts store
     2. Import PEM-encoded certificates into the Singine keystore
     3. Document each CA as a URN (urn:singine:ca:<sha256-fingerprint>)
     4. Validate certificate chains

   The Singine keystore is a separate file (default: ~/.singine/singine.jks)
   and NEVER modifies the JVM's system cacerts store.

   URN scheme:
     urn:singine:ca:<sha256-fingerprint-hex>   — root CA
     urn:singine:keypair:<alias>:<fp-prefix>   — generated key pair

   Usage:
     (list-jvm-root-cas)          ; enumerate all JVM-trusted CAs
     (import-pem! auth path alias) ; add a CA cert to Singine keystore
     (generate-key-pair! auth alias) ; create RSA-4096 key pair
     (ca-report auth)              ; full CA audit report as XML"
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [singine.meta.genx    :as genx]
            [clojure.java.io      :as io]
            [clojure.string       :as str])
  (:import [singine.auth CertAuthority CertAuthority$CertEntry CertAuthority$KeyPairEntry]
           [java.io File StringWriter]))

;; ── Default paths ─────────────────────────────────────────────────────────────

(def default-keystore-path
  "Default path for the Singine custom keystore."
  (str (System/getProperty "user.home") "/.singine/singine.jks"))

(def default-keystore-password
  "Default keystore password — override via SINGINE_KS_PASS env var."
  (or (System/getenv "SINGINE_KS_PASS") "singine-changeit"))

;; ── CertAuthority factory ─────────────────────────────────────────────────────

(defn make-ca
  "Creates a CertAuthority instance.
   ks-path and ks-pass default to ~/.singine/singine.jks and env SINGINE_KS_PASS."
  ([]
   (CertAuthority. default-keystore-path default-keystore-password))
  ([ks-path ks-pass]
   (CertAuthority. ks-path ks-pass)))

;; ── Root CA enumeration ───────────────────────────────────────────────────────

(defn entry->map
  "Converts a CertAuthority$CertEntry to a Clojure map."
  [^CertAuthority$CertEntry e]
  {:alias       (.alias e)
   :urn         (.urn e)
   :subject-dn  (.subjectDN e)
   :issuer-dn   (.issuerDN e)
   :serial      (.serialNumber e)
   :not-before  (.notBefore e)
   :not-after   (.notAfter e)
   :sha256      (.sha256Fingerprint e)
   :key-algo    (.keyAlgorithm e)
   :key-bits    (.keySizeBits e)})

(defn list-jvm-root-cas
  "Lists all trusted root CA certificates from the JVM's cacerts store.
   Returns a sequence of CA maps (sorted by alias).

   Each map:
     {:alias :urn :subject-dn :issuer-dn :serial
      :not-before :not-after :sha256 :key-algo :key-bits}"
  []
  (let [ca (make-ca)]
    (mapv entry->map (.listJvmRootCAs ca))))

(defn jvm-cacerts-path
  "Returns the path to the JVM's cacerts file."
  []
  (CertAuthority/jvmCacertsPath))

(defn ca-count
  "Returns the number of trusted root CAs in the JVM's cacerts store."
  []
  (count (list-jvm-root-cas)))

;; ── Custom keystore operations ────────────────────────────────────────────────

(defn import-pem!
  "Governed: imports a PEM-encoded certificate into the Singine keystore.
   Creates the keystore if it does not exist.

   auth     — govern auth token
   pem-path — absolute path to the PEM file
   alias    — certificate alias in the keystore

   Returns governed result with the CertEntry map."
  [auth pem-path alias]
  (lam/govern auth
    (fn [t]
      (let [ca  (make-ca)
            e   (.importPem ca pem-path alias)]
        {:ok        true
         :operation :import-pem
         :alias     alias
         :pem-path  pem-path
         :cert      (entry->map e)
         :time      (select-keys t [:iso :path])}))))

(defn list-singine-keystore
  "Lists all entries in the Singine custom keystore.
   Returns a sequence of CA maps."
  []
  (let [ca (make-ca)]
    (mapv entry->map (.listSingineKeystore ca))))

;; ── Key pair generation ───────────────────────────────────────────────────────

(defn generate-key-pair!
  "Governed: generates an RSA-4096 key pair for JWT/JWS signing.
   Stores the key in the Singine keystore.

   auth  — govern auth token
   alias — human-readable alias (e.g. 'singine-idp-2026')

   Returns:
     {:ok :alias :urn :public-key-pem :algorithm :time}"
  [auth alias]
  (lam/govern auth
    (fn [t]
      (let [ca  (make-ca)
            kpe ^CertAuthority$KeyPairEntry (.generateKeyPair ca alias)]
        {:ok            true
         :operation     :generate-key-pair
         :alias         (.alias kpe)
         :urn           (.urn kpe)
         :public-key-pem (.publicKeyPem kpe)
         :algorithm     (.algorithm kpe)
         :time          (select-keys t [:iso :path])}))))

;; ── CA audit report ───────────────────────────────────────────────────────────

(defn- cert-entry-el
  "Builds a hiccup element for a single CA cert entry."
  [m]
  [:ca:cert
   {:alias      (:alias m)
    :urn        (:urn m)
    :key-algo   (:key-algo m)
    :key-bits   (str (:key-bits m))
    :sha256     (:sha256 m)
    :not-before (:not-before m)
    :not-after  (:not-after m)}
   [:ca:subject {} (:subject-dn m)]
   [:ca:issuer  {} (:issuer-dn m)]])

(defn ca-report
  "Governed: produces a full CA audit report as XML.
   Lists all JVM root CAs + Singine keystore entries.

   Returns:
     {:ok :ca-count :jvm-path :jvm-cas :singine-cas :xml}"
  [auth]
  (lam/govern auth
    (fn [t]
      (let [jvm-cas      (list-jvm-root-cas)
            singine-cas  (try (list-singine-keystore) (catch Exception _ []))
            jvm-path     (jvm-cacerts-path)
            iso-ts       (get-in t [:iso])
            tree
            [:ca:report
             {:xmlns:ca      "urn:singine:net:cacert"
              :generated-at  (str iso-ts)
              :jvm-cacerts   jvm-path
              :jvm-ca-count  (str (count jvm-cas))
              :singine-count (str (count singine-cas))}
             [:ca:jvm-root-cas {}
              (into [:ca:certs {}]
                    (mapv cert-entry-el jvm-cas))]
             [:ca:singine-keystore {}
              (into [:ca:certs {}]
                    (mapv cert-entry-el singine-cas))]]
            sw      (StringWriter.)
            xml-str (genx/emit-document! sw tree)]
        {:ok          true
         :ca-count    (count jvm-cas)
         :jvm-path    jvm-path
         :jvm-cas     jvm-cas
         :singine-cas singine-cas
         :xml         xml-str
         :time        (select-keys t [:iso :path])}))))

;; ── CA summary (for display / documentation) ─────────────────────────────────

(defn summarize-ca
  "Returns a brief summary string for a CA map."
  [m]
  (str (:alias m) " | " (:key-algo m) "/" (:key-bits m)
       " | " (:subject-dn m)))

(defn print-ca-summary!
  "Prints all JVM root CAs to stdout (for interactive use)."
  []
  (let [cas (list-jvm-root-cas)]
    (println (str "JVM cacerts: " (jvm-cacerts-path)))
    (println (str "Trusted root CAs: " (count cas)))
    (println "---")
    (doseq [[i m] (map-indexed vector cas)]
      (println (format "%3d. %s" (inc i) (summarize-ca m))))))
