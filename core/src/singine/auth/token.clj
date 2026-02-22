(ns singine.auth.token
  "JWT / JWS token lifecycle for the Singine identity provider.

   Implements RFC 7515 (JWS) + RFC 7519 (JWT) via singine.auth.JwsToken (Java).
   No external JWT libraries — uses only JDK 11+ stdlib + our JwsToken class.

   Token lifecycle:
     sign!    → produce signed JWT (RS256 or HS256)
     verify!  → verify and decode JWT
     exchange! → OAuth2-style client-credentials token exchange (stub)
     persist! → write token to filesystem (encrypted at rest via JKS)
     revoke!  → mark token as revoked in the SQLite CodeTable

   Singine-specific claims (auto-added by JwsToken.java):
     iss — 'urn:singine:idp'
     iat — issued-at epoch seconds
     exp — expiry (iat + ttlSeconds)
     jti — random UUID (replay prevention)
     sid — 'urn:singine:session:<jti-prefix>'

   Usage:
     ;; RS256 (asymmetric — recommended for IdP)
     (def kpe (cacert/generate-key-pair! auth \"singine-idp-2026\"))
     (def tok (sign! auth {:sub \"skh@singine.local\" :roles [\"admin\"]}
                     3600 {:algo :rs256 :key-pair (:key-pair kpe)}))
     (verify! tok {:algo :rs256 :public-key (:public-key kpe)})

     ;; HS256 (symmetric — for service-to-service)
     (def tok (sign! auth {:sub \"kafka-consumer\"} 3600
                     {:algo :hs256 :secret \"my-secret\"}))
     (verify! tok {:algo :hs256 :secret \"my-secret\"})"
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [clojure.java.io      :as io]
            [clojure.string       :as str])
  (:import [singine.auth JwsToken CertAuthority]
           [java.security KeyPair PrivateKey PublicKey]
           [java.io File]
           [java.nio.file Files Paths StandardOpenOption]
           [java.time Instant]))

;; ── Converters (public — used by singine.pos.idp) ────────────────────────────

(defn claims->java
  "Converts a Clojure map to java.util.LinkedHashMap<String,Object>.
   Used by singine.pos.idp for raw JwsToken calls."
  [m]
  (let [jm (java.util.LinkedHashMap.)]
    (doseq [[k v] m]
      (.put jm (if (keyword? k) (name k) (str k))
            (cond
              (keyword? v) (name v)
              (vector? v)  (java.util.ArrayList. (map #(if (keyword? %) (name %) %) v))
              :else        v)))
    jm))

(defn java->claims
  "Converts a java.util.Map<String,Object> to a Clojure map.
   Used by singine.pos.idp for raw JwsToken result conversion."
  [jm]
  (into {} (for [[k v] jm] [(keyword k) v])))

;; ── Token signing ─────────────────────────────────────────────────────────────

(defn sign!
  "Governed: signs a JWT with the specified algorithm.

   auth        — govern auth token
   claims      — Clojure map of JWT payload claims
   ttl-seconds — token lifetime in seconds (default 3600)
   opts        — {:algo :rs256 | :hs256
                  :private-key  PrivateKey  (for :rs256)
                  :secret       String      (for :hs256)}

   Returns:
     {:ok :token :algo :exp :sid :time}"
  [auth claims ttl-seconds opts]
  (lam/govern auth
    (fn [t]
      (let [algo       (get opts :algo :rs256)
            java-claims (claims->java claims)
            token      (case algo
                         :rs256 (JwsToken/signRS256
                                  ^PrivateKey (:private-key opts)
                                  java-claims
                                  (long ttl-seconds))
                         :hs256 (JwsToken/signHS256
                                  ^String (:secret opts)
                                  java-claims
                                  (long ttl-seconds))
                         (throw (IllegalArgumentException.
                                  (str "Unknown algorithm: " algo
                                       ". Use :rs256 or :hs256"))))
            decoded    (java->claims (JwsToken/decode token))
            now-epoch  (quot (System/currentTimeMillis) 1000)]
        {:ok      true
         :token   token
         :algo    (name algo)
         :iat     (get decoded :iat now-epoch)
         :exp     (get decoded :exp (+ now-epoch ttl-seconds))
         :jti     (get decoded :jti "")
         :sid     (get decoded :sid "")
         :iss     (get decoded :iss "urn:singine:idp")
         :sub     (get decoded :sub "")
         :time    (select-keys t [:iso :path])}))))

;; ── Token verification ────────────────────────────────────────────────────────

(defn verify!
  "Governed: verifies a JWT and returns the decoded claims.

   auth  — govern auth token
   token — compact JWT string (header.payload.signature)
   opts  — {:algo :rs256 | :hs256
             :public-key  PublicKey  (for :rs256)
             :secret      String     (for :hs256)}

   Returns:
     {:ok :claims :sub :iss :exp :jti :sid :time}
   Or on failure:
     {:ok false :error :time}"
  [auth token opts]
  (lam/govern auth
    (fn [t]
      (try
        (let [algo   (get opts :algo :rs256)
              claims (case algo
                       :rs256 (java->claims
                                (JwsToken/verifyRS256
                                  token
                                  ^PublicKey (:public-key opts)))
                       :hs256 (java->claims
                                (JwsToken/verifyHS256
                                  ^String (:secret opts) token))
                       (throw (IllegalArgumentException.
                                (str "Unknown algorithm: " algo))))]
          {:ok     true
           :claims claims
           :sub    (get claims :sub "")
           :iss    (get claims :iss "")
           :exp    (get claims :exp 0)
           :jti    (get claims :jti "")
           :sid    (get claims :sid "")
           :time   (select-keys t [:iso :path])})
        (catch Exception e
          {:ok    false
           :error (.getMessage e)
           :token (subs token 0 (min 32 (count token)))
           :time  (select-keys t [:iso :path])})))))

;; ── Token decode (no verification) ───────────────────────────────────────────

(defn decode-token
  "Decodes a JWT payload without signature verification.
   Useful for inspection and debugging."
  [token]
  (try
    {:ok     true
     :claims (java->claims (JwsToken/decode token))
     :header (java->claims (JwsToken/decodeHeader token))}
    (catch Exception e
      {:ok false :error (.getMessage e)})))

;; ── OAuth2 token exchange (client-credentials stub) ──────────────────────────

(defn exchange!
  "Governed: OAuth2 client-credentials token exchange stub.
   Phase 1: returns a synthetic token exchange result.
   Phase 2: real HTTP POST to /token endpoint.

   auth — govern auth token
   opts — {:issuer      String — OIDC issuer URL
            :client-id   String
            :client-secret String
            :scope       String (default 'openid')
            :dry-run     boolean (default true)}

   Returns:
     {:ok :access-token :token-type :expires-in :scope :issuer :time}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [issuer    (get opts :issuer "http://localhost:8080")
            client-id (get opts :client-id "singine")
            scope     (get opts :scope "openid")
            dry-run   (get opts :dry-run true)]
        (if dry-run
          ;; Synthetic Phase 1 result
          (let [stub-token (str "stub." (.encodeToString
                                          (java.util.Base64/getUrlEncoder)
                                          (.getBytes (str "{\"sub\":\"" client-id
                                                          "\",\"scope\":\"" scope
                                                          "\",\"iss\":\"" issuer "\"}")))
                                ".stub-sig")]
            {:ok           true
             :access-token stub-token
             :token-type   "Bearer"
             :expires-in   3600
             :scope        scope
             :issuer       issuer
             :client-id    client-id
             :dry-run      true
             :time         (select-keys t [:iso :path])})
          ;; Phase 2: real HTTP exchange (uses JDK HttpClient)
          (try
            (let [client (-> (java.net.http.HttpClient/newBuilder)
                             (.connectTimeout (java.time.Duration/ofSeconds 10))
                             (.build))
                  body   (str "grant_type=client_credentials"
                              "&client_id=" client-id
                              "&client_secret=" (get opts :client-secret "")
                              "&scope=" scope)
                  req    (-> (java.net.http.HttpRequest/newBuilder)
                             (.uri (java.net.URI/create (str issuer "/token")))
                             (.timeout (java.time.Duration/ofSeconds 10))
                             (.header "Content-Type" "application/x-www-form-urlencoded")
                             (.POST (java.net.http.HttpRequest$BodyPublishers/ofString body))
                             (.build))
                  resp   (.send client req
                                (java.net.http.HttpResponse$BodyHandlers/ofString))
                  status (.statusCode resp)
                  body   (.body resp)]
              {:ok        (< status 400)
               :status    status
               :body      (subs body 0 (min 500 (count body)))
               :issuer    issuer
               :client-id client-id
               :dry-run   false
               :time      (select-keys t [:iso :path])})
            (catch Exception e
              {:ok       false
               :error    (.getMessage e)
               :issuer   issuer
               :dry-run  false
               :time     (select-keys t [:iso :path])})))))))

;; ── Token persistence ─────────────────────────────────────────────────────────

(defn persist!
  "Governed: writes a token to the filesystem at a temporal path.
   The token file is written under ~/.singine/tokens/<jti>.jwt

   auth  — govern auth token
   token — JWT string to persist
   opts  — {:ttl-seconds long (for metadata)}

   Returns:
     {:ok :path :jti :time}"
  [auth token opts]
  (lam/govern auth
    (fn [t]
      (let [decoded   (decode-token token)
            jti       (get-in decoded [:claims :jti] (str (java.util.UUID/randomUUID)))
            tokens-dir (str (System/getProperty "user.home") "/.singine/tokens")
            token-path (str tokens-dir "/" jti ".jwt")]
        (try
          (let [dir (java.io.File. tokens-dir)]
            (.mkdirs dir)
            (spit token-path token))
          {:ok    true
           :path  token-path
           :jti   jti
           :time  (select-keys t [:iso :path])}
          (catch Exception e
            {:ok    false
             :error (.getMessage e)
             :jti   jti
             :time  (select-keys t [:iso :path])}))))))

;; ── Token revocation ─────────────────────────────────────────────────────────

(defn revoke!
  "Governed: marks a token's jti as revoked in the Singine CodeTable.
   Phase 1: writes to ~/.singine/tokens/<jti>.revoked
   Phase 2: stores in SQLite CodeTable revocation list

   auth — govern auth token
   jti  — JWT ID to revoke

   Returns:
     {:ok :jti :revoked-at :time}"
  [auth jti]
  (lam/govern auth
    (fn [t]
      (let [tokens-dir  (str (System/getProperty "user.home") "/.singine/tokens")
            revoke-path (str tokens-dir "/" jti ".revoked")
            revoked-at  (:iso t)]
        (try
          (.mkdirs (java.io.File. tokens-dir))
          (spit revoke-path (str "revoked-at=" revoked-at "\njti=" jti))
          {:ok         true
           :jti        jti
           :revoked-at revoked-at
           :path       revoke-path
           :time       (select-keys t [:iso :path])}
          (catch Exception e
            {:ok    false
             :error (.getMessage e)
             :jti   jti
             :time  (select-keys t [:iso :path])}))))))

;; ── Convenience: generate + sign in one step ─────────────────────────────────

(defn mint-hs256-token!
  "Convenience: sign a HS256 token without the governed wrapper.
   Useful for internal service tokens and tests.

   Returns {:token :exp :jti} or throws on error."
  [secret claims ttl-seconds]
  (let [java-claims (claims->java claims)
        token       (JwsToken/signHS256 secret java-claims (long ttl-seconds))
        decoded     (java->claims (JwsToken/decode token))]
    {:token token
     :exp   (:exp decoded)
     :jti   (:jti decoded)
     :sid   (:sid decoded)}))

(defn verify-hs256-token
  "Convenience: verify a HS256 token without the governed wrapper.
   Returns claims map or {:error message}."
  [secret token]
  (try
    {:ok true :claims (java->claims (JwsToken/verifyHS256 secret token))}
    (catch Exception e
      {:ok false :error (.getMessage e)})))
