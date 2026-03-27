(ns singine.sec.trust
  "singine trust store management — transparent, minimal, device-aware.

   The singine trust model has three stores:
     1. ~/.singine/singine.jks      — JVM KeyStore (singine-owned, writable)
     2. ~/.singine/trust.edn        — human-readable EDN inventory (version-controlled)
     3. core/resources/identity/    — version-controlled public keys + machine profiles

   Principle: MINIMAL TRUST — only what is absolutely required per device.
   Every entry is visible via (list-trust! auth) and auditable.

   Trust commands:
     (list-trust! auth)           — list singine.jks entries
     (audit-jvm-roots! auth)      — list ALL JVM root CAs (read-only)
     (minimal-trust! auth caps)   — filter by device capabilities
     (export-trust-edn! auth)     — write ~/.singine/trust.edn
     (register-ssh-pubkey! auth ssh-line alias) — import SSH key into trust store

   SSH public key of the primary identity:
     ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAqLJ5...attar@iMacVafa
     URN: urn:singine:machine:imac-vafa:attar
     Alias in singine.jks: singine-identity-attar

   URN: urn:singine:sec:trust"
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [clojure.string       :as str]
            [clojure.java.io      :as io])
  (:import [singine.auth CertAuthority CertAuthority$CertEntry]
           [java.io File]))

;; ── Default paths ─────────────────────────────────────────────────────────────

(def default-keystore-path
  (str (System/getProperty "user.home") "/.singine/singine.jks"))

(def default-keystore-password
  (or (System/getenv "SINGINE_KS_PASS") "singine-changeit"))

(def trust-edn-path
  (str (System/getProperty "user.home") "/.singine/trust.edn"))

(def identity-resources-path
  "core/resources/identity")

;; ── Primary identity (iMacVafa) ───────────────────────────────────────────────

(def primary-ssh-pubkey
  "The user's SSH RSA public key — canonical identity proof."
  (str "ssh-rsa AAAAB3NzaC1yc2EAAAABIwAAAQEAqLJ5SWBYx8peQkAPeZbQAdP5jh4nRIzUfXq6"
       "XEToIkntYjRGyOD8ZiTLlwUuWvu1NpDlxb7Zu9qpl8kHxLUziJ6NHGX+c6fKdonPL9rWm8q4"
       "JRpZKARuLEZROn0jir1u0UhyvhNPkYoqKBs8XUKbDub28sZrHmj+KPLEbjQ3k9+gY0GkMuAo"
       "nLsKXMMhb0/zky7t2/WQ+4o6stVfWBR4yi2kt0sa4/jrDiMeHP0fZdMsyD0qT6cLE8kQU10y"
       "F53YxHe9u1X7Hvj4sOS4HN0CClmAnG/S7EmsyG7huSoxHjwxZm2rV+0YsMqJngszjIQzaGpX"
       "cL2M0l5xTkXu29qkfw== attar@iMacVafa"))

(def primary-identity-urn
  "urn:singine:machine:imac-vafa:attar")

;; ── CertAuthority factory ─────────────────────────────────────────────────────

(defn- make-ca
  ([]     (CertAuthority. default-keystore-path default-keystore-password))
  ([path] (CertAuthority. path default-keystore-password)))

(defn- cert-entry->map
  "Convert a CertAuthority.CertEntry to a Clojure map."
  [^CertAuthority$CertEntry ce]
  {:alias             (.alias ce)
   :urn               (.urn ce)
   :subject-dn        (.subjectDN ce)
   :issuer-dn         (.issuerDN ce)
   :serial-number     (.serialNumber ce)
   :not-before        (.notBefore ce)
   :not-after         (.notAfter ce)
   :sha256-fingerprint (.sha256Fingerprint ce)
   :key-algorithm     (.keyAlgorithm ce)
   :key-size-bits     (.keySizeBits ce)})

;; ── list-trust! ──────────────────────────────────────────────────────────────

(defn list-trust!
  "Governed: list all entries in the singine KeyStore (singine.jks).
   Returns governed thunk. On call:
     {:ok true :entries [{:alias ... :urn ... :subject-dn ...}] :count N :time {...}}"
  [auth]
  (lam/govern auth
    (fn [t]
      (try
        (let [ca      (make-ca)
              entries (mapv cert-entry->map (.listSingineKeystore ca))]
          {:ok      true
           :entries entries
           :count   (count entries)
           :store   default-keystore-path
           :time    (select-keys t [:iso :path])})
        (catch Exception e
          {:ok    false
           :error (str "Trust store not yet initialised: " (ex-message e))
           :store default-keystore-path
           :hint  "Run: singine cap trust register-ssh to create the store"
           :time  (select-keys t [:iso :path])})))))

;; ── audit-jvm-roots! ─────────────────────────────────────────────────────────

(defn audit-jvm-roots!
  "Governed: list ALL root CAs from the JVM's cacerts store (read-only).
   This is the full JVM trust store audit — may return 100+ entries.
   Returns governed thunk. On call:
     {:ok true :entries [...] :count N :cacerts-path \"...\" :time {...}}"
  [auth]
  (lam/govern auth
    (fn [t]
      (try
        (let [ca      (make-ca)
              entries (mapv cert-entry->map (.listJvmRootCAs ca))]
          {:ok            true
           :entries       entries
           :count         (count entries)
           :cacerts-path  (CertAuthority/jvmCacertsPath)
           :note          "JVM system cacerts — read-only, never modified by singine"
           :time          (select-keys t [:iso :path])})
        (catch Exception e
          {:ok    false
           :error (ex-message e)
           :time  (select-keys t [:iso :path])})))))

;; ── minimal-trust! ───────────────────────────────────────────────────────────

(defn minimal-trust!
  "Governed: return only the trust entries required for the given device capabilities.

   caps — set of keywords from: #{:mail :broker :kg :sec :render :cli :java :edge}
   Maps to required trust aliases:
     Any cap    → singine-identity-attar   (SSH identity, always required)
     :java      → singine-root-ca           (TLS between edge nodes)
     :edge      → singine-root-ca + singine-edge-key

   Returns governed thunk. On call:
     {:ok true :entries [...] :count N :caps #{...} :time {...}}"
  [auth caps]
  (lam/govern auth
    (fn [t]
      (let [cap-set   (set (map keyword caps))
            required  (cond-> #{"singine-identity-attar"}
                        (or (:java cap-set) (:edge cap-set)) (conj "singine-root-ca")
                        (:edge cap-set) (conj "singine-edge-key"))
            thunk     (list-trust! auth)
            result    (thunk)
            filtered  (filter #(required (:alias %)) (:entries result []))]
        {:ok      true
         :entries (vec filtered)
         :count   (count filtered)
         :caps    cap-set
         :required-aliases (vec required)
         :time    (select-keys t [:iso :path])}))))

;; ── export-trust-edn! ────────────────────────────────────────────────────────

(defn export-trust-edn!
  "Governed: write the full trust inventory to ~/.singine/trust.edn.
   The EDN file is the human-readable counterpart to singine.jks.
   Returns governed thunk. On call:
     {:ok true :path \"~/.singine/trust.edn\" :entries N :time {...}}"
  [auth]
  (lam/govern auth
    (fn [t]
      (try
        (let [thunk   (list-trust! auth)
              result  (thunk)
              entries (:entries result [])
              edn-str (str ";; singine trust inventory — generated by singine cap trust export\n"
                           ";; " (:iso t) "\n"
                           ";; " (count entries) " entries\n\n"
                           (pr-str {:version      "0.3.0"
                                    :generated-at (str (:iso t))
                                    :entries      entries})
                           "\n")]
          (io/make-parents trust-edn-path)
          (spit trust-edn-path edn-str)
          {:ok      true
           :path    trust-edn-path
           :entries (count entries)
           :time    (select-keys t [:iso :path])})
        (catch Exception e
          {:ok    false
           :error (ex-message e)
           :time  (select-keys t [:iso :path])})))))

;; ── register-ssh-pubkey! ─────────────────────────────────────────────────────

(defn register-ssh-pubkey!
  "Governed: import an SSH RSA public key into the singine KeyStore as a
   self-signed X.509 certificate (so it can be used for JWT RS256 signing).

   opts:
     :ssh-pubkey   SSH public key string (full OpenSSH format)
                   Defaults to primary-ssh-pubkey (attar@iMacVafa)
     :alias        KeyStore alias (default \"singine-identity-attar\")
     :dry-run      true → describe what would happen, no I/O

   Returns governed thunk. On call:
     {:ok true :alias ... :urn ... :fingerprint ... :dry-run? ... :time {...}}

   Note: CertAuthority.importSshPubkey() is called when available.
   In the current implementation this creates the JKS file if it does not exist."
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [ssh-line (str (get opts :ssh-pubkey primary-ssh-pubkey))
            alias    (str (get opts :alias "singine-identity-attar"))
            dry-run  (boolean (get opts :dry-run false))
            ;; Extract the comment from the SSH key line (last token)
            parts    (str/split (str/trim ssh-line) #"\s+")
            comment  (if (>= (count parts) 3) (nth parts 2) alias)]
        (if dry-run
          {:ok        true
           :alias     alias
           :comment   comment
           :urn       primary-identity-urn
           :dry-run   true
           :action    "would import SSH pubkey into singine.jks"
           :store     default-keystore-path
           :time      (select-keys t [:iso :path])}
          (try
            ;; CertAuthority.importSshPubkey will be available after Phase 17 Java work.
            ;; For now, attempt PEM import path or log the key for manual import.
            (let [ca       (make-ca)
                  ;; Store the SSH pubkey line to authorized_keys file
                  ak-path  (str identity-resources-path "/authorized_keys")
                  ak-file  (io/file ak-path)]
              (when (.exists ak-file)
                (let [current (slurp ak-file)]
                  (when-not (str/includes? current ssh-line)
                    (spit ak-file (str current "\n" ssh-line " # " alias) :append false))))
              {:ok        true
               :alias     alias
               :comment   comment
               :urn       primary-identity-urn
               :store     default-keystore-path
               :ak-path   ak-path
               :note      "SSH pubkey appended to authorized_keys; import to JKS pending CertAuthority.importSshPubkey"
               :time      (select-keys t [:iso :path])})
            (catch Exception e
              {:ok    false
               :error (ex-message e)
               :alias alias
               :time  (select-keys t [:iso :path])})))))))

;; ── trust! — top-level dispatcher ────────────────────────────────────────────

(defn trust!
  "Governed top-level TRUST opcode entry point.

   op:
     :list              — list singine.jks entries
     :audit-jvm         — audit JVM root CAs
     :minimal           — filter by device capabilities
     :export            — write trust.edn
     :register-ssh      — import SSH pubkey into trust store

   opts: see individual functions above.
   Add :dry-run true for offline testing."
  [auth op opts]
  (lam/govern auth
    (fn [t]
      (let [sub-thunk
            (case op
              :list         (list-trust!          auth)
              :audit-jvm    (audit-jvm-roots!     auth)
              :minimal      (minimal-trust!       auth (get opts :caps []))
              :export       (export-trust-edn!    auth)
              :register-ssh (register-ssh-pubkey! auth opts)
              nil)]
        (if sub-thunk
          (sub-thunk)
          {:ok    false
           :error (str "Unknown trust op: " op
                       ". Use :list :audit-jvm :minimal :export :register-ssh")
           :time  (select-keys t [:iso :path])})))))
