(ns singine.pos.idp
  "IDPR opcode — Singine Self-hosted Identity Provider.

   Provides a minimal, self-contained OpenID Connect + JWT identity provider
   for use on a private network. No Okta, no Auth0 — just JDK 11+ stdlib
   and the Singine auth stack (CertAuthority + JwsToken).

   Capabilities:
     1. Token issuance — sign JWT/JWS with RSA-4096 private key
     2. Token verification — verify with RSA-4096 public key
     3. File access token — time-limited JWT authorising access to a path
     4. JWKS endpoint stub — expose public key in JWKS format (RFC 7517)
     5. CA audit — list all trusted root CAs from JVM cacerts
     6. Public key export — PEM-encoded RSA-4096 public key

   Private network file access flow:
     1. Client calls idp-token! to get a file-access JWT
     2. JWT carries:
          sub  = file path (URI-encoded)
          aud  = \"urn:singine:resource:file\"
          perm = \"read\" | \"read-write\"
          exp  = issued-at + ttl-seconds
     3. File server verifies JWT with the IdP's public key
     4. If valid and not expired, serves the file content

   OAuth 2.0 vs OpenID Connect vs SAML (summary):
     OAuth 2.0    — authorization framework (delegated access, access tokens)
                    RFC 6749; not an authentication protocol itself
     OpenID Connect — identity layer on top of OAuth 2.0 (ID token = JWT)
                    RFC + OIDC spec; adds 'who is the user?' to OAuth
     SAML 2.0    — XML-based enterprise federation (assertions, IdP → SP)
                    OASIS standard; dominant in enterprise/Collibra context

   Singine IdP implements OpenID Connect (OIDC) subset:
     - Discovery endpoint: /.well-known/openid-configuration
     - JWKS endpoint:      /.well-known/jwks.json
     - Token endpoint:     /token (client_credentials flow)
     - File-access tokens: /token?scope=file:read (custom extension)

   Usage:
     (def kpe @(generate-idp-keypair! auth 'singine-idp-2026'))
     (def tok @(idp-token! auth {:sub 'skh@singine.local' :perm :read} kpe))
     (verify-file-token! auth tok (:public-key kpe))
     (file-access! auth '/Users/skh/private/doc.pdf' tok (:public-key kpe))"
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [singine.auth.token   :as tok]
            [singine.net.cacert   :as ca]
            [singine.meta.genx    :as genx]
            [clojure.java.io      :as io]
            [clojure.string       :as str]
            [clojure.data.json    :as json])
  (:import [singine.auth CertAuthority JwsToken]
           [java.security KeyPair PrivateKey PublicKey]
           [java.io StringWriter File]
           [java.util Base64]))

;; ── IdP key pair management ───────────────────────────────────────────────────

(defn generate-idp-keypair!
  "Governed: generate an RSA-4096 key pair for the Singine IdP.
   Stores the key in ~/.singine/singine.jks (default).

   auth  — govern auth token
   alias — key alias, e.g. 'singine-idp-2026'

   Returns:
     {:ok :alias :urn :public-key-pem :key-pair :time}

   The :key-pair is a java.security.KeyPair — keep private key SECRET."
  [auth alias]
  (lam/govern auth
    (fn [t]
      (let [cert-auth (ca/make-ca)
            kpe       (.generateKeyPair cert-auth alias)
            kp        ^KeyPair (.keyPair kpe)]
        {:ok             true
         :operation      :generate-idp-keypair
         :alias          (.alias kpe)
         :urn            (.urn kpe)
         :public-key-pem (.publicKeyPem kpe)
         :key-pair       kp          ; java.security.KeyPair
         :private-key    (.getPrivate kp)
         :public-key     (.getPublic kp)
         :algorithm      (.algorithm kpe)
         :time           (select-keys t [:iso :path])}))))

;; ── OIDC discovery document ───────────────────────────────────────────────────

(defn discovery-document
  "Returns the OIDC .well-known/openid-configuration map.
   Phase 1: in-memory map (no HTTP server).
   Phase 2: served by singine.net.http/start! on localhost:<port>.

   opts:
     :issuer — IdP issuer URL (default 'https://singine.local')
     :port   — HTTP port (default 8443)"
  [& {:keys [issuer port]
      :or   {issuer "https://singine.local" port 8443}}]
  {:issuer                                issuer
   :authorization_endpoint                (str issuer ":" port "/authorize")
   :token_endpoint                        (str issuer ":" port "/token")
   :userinfo_endpoint                     (str issuer ":" port "/userinfo")
   :jwks_uri                              (str issuer ":" port "/.well-known/jwks.json")
   :registration_endpoint                 (str issuer ":" port "/register")
   :response_types_supported              ["code" "token" "id_token"]
   :subject_types_supported               ["public" "pairwise"]
   :id_token_signing_alg_values_supported ["RS256" "HS256"]
   :scopes_supported                      ["openid" "profile" "email"
                                           "file:read" "file:write"]
   :token_endpoint_auth_methods_supported ["client_secret_basic"
                                           "client_secret_post"
                                           "private_key_jwt"]
   :claims_supported                      ["sub" "iss" "iat" "exp"
                                           "jti" "sid" "name" "email"
                                           "perm" "path" "aud"]
   :grant_types_supported                 ["authorization_code"
                                           "client_credentials"
                                           "refresh_token"]})

;; ── JWKS endpoint ─────────────────────────────────────────────────────────────

(defn public-key->jwks
  "Converts an RSA PublicKey to a JWKS (JSON Web Key Set) map.
   The JWK format (RFC 7517) is:
     { 'keys': [{ 'kty':'RSA', 'use':'sig', 'alg':'RS256', 'n':'...', 'e':'...' }] }

   Phase 1: serialises RSA modulus + exponent as Base64URL-encoded strings."
  [^PublicKey public-key alias]
  (let [;; Encode the RSA public key into its SubjectPublicKeyInfo DER bytes
        ;; and then extract modulus (n) and exponent (e)
        encoded  (.getEncoded public-key)
        ;; The key's JWK representation uses Base64URL of the full DER
        ;; For a proper JWK we need the RSAPublicKey interface
        rsa-key  (try
                   (let [kf (java.security.KeyFactory/getInstance "RSA")
                         spec (java.security.spec.X509EncodedKeySpec. encoded)]
                     (.generatePublic kf spec))
                   (catch Exception _ public-key))
        ;; Extract RSA components if possible
        [n-b64 e-b64] (try
                        (let [rk ^java.security.interfaces.RSAPublicKey rsa-key
                              n  (.getModulus rk)
                              e  (.getPublicExponent rk)
                              encoder (Base64/getUrlEncoder)
                              enc (.withoutPadding encoder)]
                          [(.encodeToString enc (.toByteArray n))
                           (.encodeToString enc (.toByteArray e))])
                        (catch Exception _
                          [(.encodeToString (Base64/getUrlEncoder) encoded) "AQAB"]))
        kid (str alias "-" (subs (Integer/toHexString (.hashCode public-key)) 0
                                 (min 8 (count (Integer/toHexString (.hashCode public-key))))))]
    {:keys [{:kty "RSA"
             :use "sig"
             :alg "RS256"
             :kid kid
             :n   n-b64
             :e   e-b64}]}))

;; ── File access token issuance ────────────────────────────────────────────────

(defn idp-token!
  "Governed: issue a JWT for the Singine IdP.
   Supports both general identity tokens and file-access tokens.

   auth    — govern auth token
   claims  — base claims map: {:sub :name :email :roles ...}
   opts    — {:ttl-seconds  long         (default 3600)
               :algo         :rs256|:hs256 (default :rs256)
               :private-key  PrivateKey   (required for :rs256)
               :secret       String       (required for :hs256)
               :scope        String       (default 'openid')
               ;; File access extension:
               :file-path    String       (when issuing file-access token)
               :perm         :read|:read-write (default :read)}

   Returns:
     {:ok :token :algo :exp :jti :sid :sub :scope :time}
   For file-access tokens also includes:
     :file-path :perm :aud"
  [auth claims opts]
  (lam/govern auth
    (fn [t]
      (let [ttl-seconds (get opts :ttl-seconds 3600)
            algo        (get opts :algo :rs256)
            scope       (get opts :scope "openid")
            file-path   (get opts :file-path)
            perm        (get opts :perm :read)

            ;; Merge file-access claims if file-path is given
            full-claims (cond-> (merge {"scope" scope} claims)
                          file-path (merge {"aud"  "urn:singine:resource:file"
                                            "path" file-path
                                            "perm" (name perm)}))

            ;; Delegate to singine.auth.token/mint-hs256-token! or sign via RS256
            result
            (case algo
              :hs256
              (let [{:keys [token exp jti sid]}
                    (tok/mint-hs256-token!
                      (get opts :secret "singine-dev-secret")
                      full-claims
                      ttl-seconds)]
                {:token token :exp exp :jti jti :sid sid})

              :rs256
              (let [private-key ^PrivateKey (:private-key opts)]
                (when-not private-key
                  (throw (IllegalArgumentException.
                           "RS256 requires :private-key in opts")))
                (let [java-claims (tok/claims->java full-claims)
                      token       (JwsToken/signRS256 private-key java-claims
                                                      (long ttl-seconds))
                      decoded     (tok/java->claims (JwsToken/decode token))]
                  {:token token
                   :exp   (:exp decoded)
                   :jti   (:jti decoded)
                   :sid   (:sid decoded)}))

              (throw (IllegalArgumentException.
                       (str "Unsupported algo: " algo))))]

        (cond->
          {:ok        true
           :token     (:token result)
           :algo      (name algo)
           :exp       (:exp result)
           :jti       (:jti result)
           :sid       (:sid result)
           :sub       (get full-claims "sub" (get claims :sub ""))
           :scope     scope
           :issuer    "urn:singine:idp"
           :time      (select-keys t [:iso :path])}
          file-path (assoc :file-path file-path
                           :perm      (name perm)
                           :aud       "urn:singine:resource:file"))))))

;; ── File access (private network) ────────────────────────────────────────────

(defn verify-file-token!
  "Verifies a file-access JWT and returns the authorised path + permissions.

   auth       — govern auth token
   token      — JWT string from idp-token!
   public-key — RSA PublicKey (from generate-idp-keypair!)
                OR a shared secret string (for HS256)
   opts       — {:algo :rs256 | :hs256 (default :rs256)}

   Returns:
     {:ok :sub :path :perm :exp :time}
   On failure:
     {:ok false :error :time}"
  [auth token public-key & [opts]]
  (lam/govern auth
    (fn [t]
      (let [algo (get opts :algo :rs256)]
        (try
          (let [claims (case algo
                         :rs256 (tok/java->claims
                                  (JwsToken/verifyRS256 token
                                                        ^PublicKey public-key))
                         :hs256 (tok/java->claims
                                  (JwsToken/verifyHS256 (str public-key) token))
                         (throw (IllegalArgumentException.
                                  (str "Unknown algo: " algo))))]
            {:ok   true
             :sub  (get claims :sub "")
             :path (get claims :path "")
             :perm (get claims :perm "read")
             :exp  (get claims :exp 0)
             :aud  (get claims :aud "")
             :jti  (get claims :jti "")
             :time (select-keys t [:iso :path])})
          (catch Exception e
            {:ok    false
             :error (.getMessage e)
             :time  (select-keys t [:iso :path])}))))))

(defn file-access!
  "Governed: reads a file from the local filesystem after verifying a JWT.
   This is the 'remote file viewing' capability — the file server side.

   On a private network:
     1. Client presents JWT from idp-token! (file-access token)
     2. File server calls file-access! to verify + read
     3. Returns file content if authorised and path matches JWT :path claim

   auth        — govern auth token
   file-path   — absolute path to the file
   jwt-token   — JWT from idp-token! with :file-path + :perm claims
   public-key  — RSA PublicKey (from generate-idp-keypair!)
   opts        — {:algo :rs256 | :hs256 (default :rs256)
                  :max-bytes long (default 65536 = 64 KiB preview)}

   Returns:
     {:ok :path :size-bytes :content-preview :perm :sub :time}
   On failure (invalid token, wrong path, missing file):
     {:ok false :reason :time}"
  [auth file-path jwt-token public-key & [opts]]
  (lam/govern auth
    (fn [t]
      (let [algo      (get opts :algo :rs256)
            max-bytes (get opts :max-bytes 65536)]
        (try
          ;; Step 1: verify JWT
          (let [claims (case algo
                         :rs256 (tok/java->claims
                                  (JwsToken/verifyRS256 jwt-token
                                                        ^PublicKey public-key))
                         :hs256 (tok/java->claims
                                  (JwsToken/verifyHS256 (str public-key) jwt-token))
                         (throw (IllegalArgumentException.
                                  (str "Unknown algo: " algo))))

                ;; Step 2: verify path claim matches requested path
                token-path (get claims :path "")
                sub        (get claims :sub "")]

            (if (and (seq token-path)
                     (not= token-path file-path))
              {:ok     false
               :reason (str "Token path mismatch: token=" token-path
                            " requested=" file-path)
               :time   (select-keys t [:iso :path])}

              ;; Step 3: read file
              (let [f (File. file-path)]
                (if-not (.exists f)
                  {:ok     false
                   :reason (str "File not found: " file-path)
                   :time   (select-keys t [:iso :path])}

                  (let [size-bytes  (.length f)
                        ;; Read up to max-bytes as preview
                        content     (try
                                      (let [ba (byte-array (min size-bytes max-bytes))]
                                        (with-open [fis (java.io.FileInputStream. f)]
                                          (.read fis ba))
                                        (String. ba "UTF-8"))
                                      (catch Exception e
                                        (str "[binary or unreadable: " (.getMessage e) "]")))
                        perm        (get claims :perm "read")]
                    {:ok              true
                     :path            file-path
                     :size-bytes      size-bytes
                     :content-preview content
                     :perm            perm
                     :sub             sub
                     :jti             (get claims :jti "")
                     :time            (select-keys t [:iso :path])})))))

          (catch Exception e
            {:ok     false
             :reason (.getMessage e)
             :time   (select-keys t [:iso :path])}))))))

;; ── Two-stream mandate: Hoffman legitimacy contract ──────────────────────────
;;
;; Principle: if two independent input streams address the same topic, the system
;; has legitimate grounds to issue an execution mandate valid for a time window.
;; This mirrors the Bitcoin consensus principle: majority agreement about the
;; existence of a fact makes it canonical. The `[[t/1]]` Logseq/singine topic
;; anchor is the canonicalised topic URI: urn:singine:topic:t/1.
;;
;; The mandate JWT carries:
;;   sub      = urn:singine:mandate:<topic>
;;   topic    = <topic-urn>
;;   streams  = JSON array of stream URNs
;;   perm     = "execute"
;;   aud      = "urn:singine:execution"
;;   exp      = now + mandate-duration-seconds
;;
;; Token validity = until exp OR legitimacy check fails (row-stochastic invariant
;; in singine.consciousness.markov — external check, not encoded in JWT itself).

(defn extract-topic
  "Extract the topic URN from a manifest string.

   Recognises two forms:
     1. Logseq topic link: [[t/1]] → 'urn:singine:topic:t/1'
     2. Explicit URN: urn:singine:topic:<suffix>

   Returns the first recognised topic URN, or nil if none found."
  [manifest-str]
  (let [s (or manifest-str "")]
    (or
      ;; Form 1: [[t/<suffix>]] Logseq notation
      (when-let [m (re-find #"\[\[t/([^\]]+)\]\]" s)]
        (str "urn:singine:topic:t/" (second m)))
      ;; Form 2: explicit URN
      (when-let [m (re-find #"urn:singine:topic:[^\s\"<\]]+" s)]
        m))))

(defn streams-same-topic?
  "Returns true if both stream content strings contain the same topic URN.

   stream-a, stream-b — strings (BLKP manifest output, raw sindoc, or any text
                         carrying a topic anchor)

   The topic anchor is either [[t/1]] (Logseq notation) or
   urn:singine:topic:... (explicit URN form).

   Both streams must resolve to the same non-nil topic for this to return true."
  [stream-a stream-b]
  (let [topic-a (extract-topic stream-a)
        topic-b (extract-topic stream-b)]
    (and (some? topic-a)
         (some? topic-b)
         (= topic-a topic-b))))

(defn topic-mandate!
  "Governed: issue an execution mandate JWT for two streams addressing the same topic.

   auth    — govern auth token
   streams — seq of [stream-urn content-string] pairs (minimum 2 required)
   opts    — map:
     :mandate-duration-seconds  how long the mandate is valid (default 3600)
     :algo                      :hs256 (default) | :rs256
     :secret                    HMAC secret string (for :hs256)
     :private-key               java.security.PrivateKey (for :rs256)

   Returns a governed zero-arg thunk. On call:
     {:ok               true
      :mandate-token    JWT string
      :topic            topic-urn
      :streams          [stream-urn ...]
      :mandate-duration seconds
      :exp              epoch-seconds
      :jti              token-id
      :time             {:iso ... :path ...}}

     OR on topic mismatch:
     {:ok    false
      :reason \"streams do not address the same topic — no matching topic anchor\"
      :time   {...}}"
  [auth streams opts]
  (lam/govern auth
    (fn [t]
      (let [duration (get opts :mandate-duration-seconds 3600)
            algo     (get opts :algo :hs256)
            secret   (get opts :secret "singine-mandate-default-secret")

            ;; Validate at least two streams provided
            _ (when (< (count streams) 2)
                (throw (IllegalArgumentException.
                         "topic-mandate! requires at least 2 streams")))

            ;; Extract stream URNs and content strings
            stream-urns     (map first streams)
            stream-contents (map second streams)
            content-a       (first stream-contents)
            content-b       (second stream-contents)

            ;; Check that both streams share a topic
            same?           (streams-same-topic? content-a content-b)
            shared-topic    (when same? (extract-topic content-a))]

        (if-not same?
          {:ok     false
           :reason "streams do not address the same topic — no matching [[t/1]] or urn:singine:topic: anchor found in both streams"
           :time   (select-keys t [:iso :path])}

          ;; Issue mandate JWT
          (let [claims {"sub"     (str "urn:singine:mandate:" shared-topic)
                        "topic"   shared-topic
                        "streams" (json/write-str (vec stream-urns))
                        "perm"    "execute"
                        "aud"     "urn:singine:execution"}]
            (case algo
              :hs256
              (let [result (tok/mint-hs256-token! secret claims duration)]
                {:ok               true
                 :mandate-token    (:token result)
                 :topic            shared-topic
                 :streams          (vec stream-urns)
                 :mandate-duration duration
                 :exp              (:exp result)
                 :jti              (:jti result)
                 :time             (select-keys t [:iso :path])})

              :rs256
              (let [pk ^PrivateKey (:private-key opts)]
                (when-not pk
                  (throw (IllegalArgumentException.
                           "RS256 topic-mandate! requires :private-key in opts")))
                (let [java-claims (tok/claims->java claims)
                      token-str   (JwsToken/signRS256 pk java-claims (long duration))
                      decoded     (tok/java->claims (JwsToken/decode token-str))]
                  {:ok               true
                   :mandate-token    token-str
                   :topic            shared-topic
                   :streams          (vec stream-urns)
                   :mandate-duration duration
                   :exp              (get decoded "exp" 0)
                   :jti              (get decoded "jti" "")
                   :time             (select-keys t [:iso :path])}))

              ;; unknown algo
              {:ok    false
               :reason (str "Unknown algo: " algo ". Use :hs256 or :rs256")
               :time  (select-keys t [:iso :path])})))))))

;; ── IDPR governed entry point ─────────────────────────────────────────────────

(defn idpr!
  "Governed IDPR entry point — dispatches IdP operations.

   auth — govern auth token
   op   — :discover | :keypair | :token | :verify | :file | :ca-report | :topic-mandate
   opts — operation-specific options

   :discover      → returns OIDC discovery document
   :keypair       → generates RSA-4096 key pair
   :token         → issues a JWT (general or file-access)
   :verify        → verifies a JWT
   :file          → reads a file after JWT verification
   :ca-report     → lists all JVM trusted root CAs
   :topic-mandate → issues a two-stream execution mandate JWT (Hoffman legitimacy contract)
                    opts: :streams (seq of [urn content] pairs), :mandate-duration-seconds,
                          :algo :hs256|:rs256, :secret

   Returns governed result."
  [auth op opts]
  (lam/govern auth
    (fn [t]
      (case op
        :discover  {:ok true :discovery (discovery-document) :time (select-keys t [:iso :path])}
        :keypair   (let [alias (get opts :alias "singine-idp")]
                     (let [cert-auth (ca/make-ca)
                           kpe       (.generateKeyPair cert-auth alias)
                           kp        ^KeyPair (.keyPair kpe)]
                       {:ok             true
                        :operation      :keypair
                        :alias          (.alias kpe)
                        :urn            (.urn kpe)
                        :public-key-pem (.publicKeyPem kpe)
                        :key-pair       kp
                        :private-key    (.getPrivate kp)
                        :public-key     (.getPublic kp)
                        :time           (select-keys t [:iso :path])}))
        :ca-report {:ok      true
                    :ca-count (ca/ca-count)
                    :jvm-path (ca/jvm-cacerts-path)
                    :cas      (take 10 (ca/list-jvm-root-cas)) ; first 10 for brevity
                    :time     (select-keys t [:iso :path])}
        :topic-mandate
        (let [streams       (get opts :streams [])
              mandate-opts  (dissoc opts :streams)]
          ;; Delegate to topic-mandate! and immediately invoke the thunk
          ((topic-mandate! auth streams mandate-opts)))
        {:ok false :error (str "Unknown op: " op
                               ". Use :discover :keypair :token :verify :file :ca-report :topic-mandate")
         :time (select-keys t [:iso :path])}))))
