(ns singine.pos.identity
  "Identity (IDNT opcode) — BSD-compatible identity dispatcher.

   Five variants (idv1–idv5) across the BSD identity stack:
     idv1  Kerberos 5 (MIT/Heimdal)   — /etc/krb5.conf, kinit, BSD-native
     idv2  OpenLDAP                   — ldapsearch, slapd.conf
     idv3  OpenID Connect (OIDC)      — HTTP, JWKS endpoint, JDK HttpClient
     idv4  SAML 2.0 (Oracle/Sun era) — XML assertions, NameID extraction
     idv5  PAM + NSS (BSD-native)     — /etc/nsswitch.conf, /etc/passwd

   Credit lineage:
     Andy Kellens (VUB), Mohammad Akhlaaghi, M. Kh. Heshmati, Sh. Kh. Heshmati —
     Sun/Oracle-era distributed systems traditions (BSD + LDAP + Kerberos).
     Oracle and Sun as the past reference system; BSD as the primary target.
     macOS/Darwin 25.3.0 is the primary dev platform.

   Dimension mapping (Category C):
     idv1 → dim=1 (edge :s, proto/c)
     idv2 → dim=2 (edge :m, proto/cc)
     idv3 → dim=3 (edge :l, proto/ccc)
     idv4 → dim=4 (explicit override)
     idv5 → dim=5 (explicit override)

   All entry points use java.lang.ProcessBuilder or java.net.http.HttpClient —
   no external deps beyond JDK 11+ standard library."
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [clojure.string       :as str])
  (:import [java.lang ProcessBuilder]
           [java.io BufferedReader InputStreamReader]
           [java.net URI]
           [java.net.http HttpClient HttpRequest HttpResponse$BodyHandlers]
           [java.time Duration]))

;; ── ProcessBuilder helper ─────────────────────────────────────────────────────

(defn- run-cmd!
  "Run a command via ProcessBuilder. Returns {:ok :exit-code :stdout :stderr}."
  [& cmd-args]
  (try
    (let [pb      (ProcessBuilder. ^java.util.List (vec cmd-args))
          _       (.redirectErrorStream pb false)
          proc    (.start pb)
          stdout  (with-open [r (BufferedReader. (InputStreamReader. (.getInputStream proc)))]
                    (str/join "\n" (line-seq r)))
          stderr  (with-open [r (BufferedReader. (InputStreamReader. (.getErrorStream proc)))]
                    (str/join "\n" (line-seq r)))
          exit    (.waitFor proc)]
      {:ok        (zero? exit)
       :exit-code exit
       :stdout    (str/trim stdout)
       :stderr    (when-not (str/blank? stderr) (str/trim stderr))})
    (catch Exception e
      {:ok false :exit-code -1 :error (.getMessage e)})))

;; ── idv1: Kerberos 5 (MIT/Heimdal, BSD-native) ───────────────────────────────

(defn authenticate-kerberos!
  "idv1 — Kerberos TGT acquisition via kinit.
   BSD-compatible: /etc/krb5.conf, MIT krb5 or Heimdal.

   opts:
     :principal  — Kerberos principal (e.g. 'skh@SINGINE.LOCAL')
     :keytab     — path to keytab file (optional; uses password prompt otherwise)
     :dry-run    — if true, run 'kinit --version' instead of actual kinit

   Returns {:ok :provider :principal :stdout :stderr :calendars}"
  [opts]
  (let [principal (get opts :principal "")
        keytab    (get opts :keytab)
        dry-run   (get opts :dry-run false)
        cmd       (cond
                    dry-run           ["kinit" "--version"]
                    (seq keytab)      ["kinit" "-k" "-t" keytab principal]
                    (seq principal)   ["kinit" principal]
                    :else             ["kinit" "--version"])]
    (assoc (apply run-cmd! cmd)
           :provider   :idv1
           :variant    "Kerberos 5 (MIT/Heimdal)"
           :principal  principal
           :dim        1
           :calendars  (cal/now-triple))))

;; ── idv2: OpenLDAP ───────────────────────────────────────────────────────────

(defn ldap-lookup
  "idv2 — LDAP directory search via ldapsearch (BSD/OpenLDAP).

   opts:
     :host     — LDAP host (default '127.0.0.1')
     :port     — LDAP port (default 389)
     :base-dn  — base DN (default 'dc=singine,dc=local')
     :filter   — LDAP filter (default '(objectClass=*)')
     :dry-run  — if true, just test connectivity with -x

   Returns {:ok :provider :host :filter :stdout :stderr :calendars}"
  [opts]
  (let [host    (get opts :host "127.0.0.1")
        port    (str (get opts :port 389))
        base-dn (get opts :base-dn "dc=singine,dc=local")
        filter  (get opts :filter "(objectClass=*)")
        dry-run (get opts :dry-run false)
        cmd     (if dry-run
                  ["ldapsearch" "-x" "-H" (str "ldap://" host ":" port)
                   "-b" base-dn "-LLL" "-l" "2" filter]
                  ["ldapsearch" "-x" "-H" (str "ldap://" host ":" port)
                   "-b" base-dn filter])]
    (assoc (apply run-cmd! cmd)
           :provider  :idv2
           :variant   "OpenLDAP"
           :host      host
           :filter    filter
           :dim       2
           :calendars (cal/now-triple))))

;; ── idv3: OpenID Connect (OIDC) ──────────────────────────────────────────────

(defn oidc-token!
  "idv3 — OIDC discovery + token stub via JDK 11+ HttpClient.
   No external HTTP library needed.

   opts:
     :issuer     — OIDC issuer URL (e.g. 'https://auth.singine.local')
     :client-id  — client ID
     :scope      — scope string (default 'openid')
     :timeout-ms — HTTP timeout in ms (default 3000)

   Returns {:ok :provider :issuer :status :body :calendars}"
  [opts]
  (let [issuer     (get opts :issuer "http://localhost:8080")
        client-id  (get opts :client-id "singine")
        scope      (get opts :scope "openid")
        timeout-ms (get opts :timeout-ms 3000)
        discovery  (str issuer "/.well-known/openid-configuration")]
    (try
      (let [client  (-> (HttpClient/newBuilder)
                        (.connectTimeout (Duration/ofMillis timeout-ms))
                        (.build))
            req     (-> (HttpRequest/newBuilder)
                        (.uri (URI/create discovery))
                        (.timeout (Duration/ofMillis timeout-ms))
                        (.GET)
                        (.build))
            resp    (.send client req (HttpResponse$BodyHandlers/ofString))
            status  (.statusCode resp)
            body    (.body resp)]
        {:ok        (< status 400)
         :provider  :idv3
         :variant   "OpenID Connect (OIDC)"
         :issuer    issuer
         :client-id client-id
         :scope     scope
         :status    status
         :body      (subs body 0 (min 200 (count body)))
         :dim       3
         :calendars (cal/now-triple)})
      (catch Exception e
        {:ok        false
         :provider  :idv3
         :variant   "OpenID Connect (OIDC)"
         :issuer    issuer
         :error     (.getMessage e)
         :dim       3
         :calendars (cal/now-triple)}))))

;; ── idv4: SAML 2.0 (Oracle/Sun lineage) ──────────────────────────────────────

(defn saml-parse-assertion
  "idv4 — SAML 2.0 assertion NameID extraction from mock XML.
   Oracle/Sun era: XML-first assertion model.

   opts:
     :assertion-xml  — SAML assertion XML string (mock accepted)

   Returns {:ok :provider :name-id :subject :calendars}"
  [opts]
  (let [xml (get opts :assertion-xml
                 "<samlp:Response xmlns:samlp='urn:oasis:names:tc:SAML:2.0:protocol'>
                    <saml:Assertion xmlns:saml='urn:oasis:names:tc:SAML:2.0:assertion'>
                      <saml:Subject>
                        <saml:NameID Format='urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress'>
                          skh@singine.local
                        </saml:NameID>
                      </saml:Subject>
                    </saml:Assertion>
                  </samlp:Response>")]
    ;; Simple regex extraction — no DOM needed for stub; (?s) = dotall (multiline NameID)
    (let [name-id-match (re-find #"(?s)<saml:NameID[^>]*>(.*?)</saml:NameID>" xml)
          name-id       (when name-id-match (str/trim (second name-id-match)))]
      {:ok        (some? name-id)
       :provider  :idv4
       :variant   "SAML 2.0 (Oracle/Sun lineage)"
       :name-id   (or name-id "unknown")
       :subject   (or name-id "unknown")
       :dim       4
       :calendars (cal/now-triple)})))

;; ── idv5: PAM + NSS (BSD-native) ─────────────────────────────────────────────

(defn pam-lookup
  "idv5 — PAM/NSS user lookup via /etc/passwd (BSD-native, macOS/Darwin).

   opts:
     :username  — username to look up (default: current user from 'user.name')

   Returns {:ok :provider :username :passwd-entry :calendars}"
  [opts]
  (let [username (get opts :username (System/getProperty "user.name" "unknown"))
        result   (run-cmd! "grep" (str "^" username ":") "/etc/passwd")]
    {:ok        (:ok result)
     :provider  :idv5
     :variant   "PAM + NSS (BSD-native)"
     :username  username
     :passwd-entry (when (:ok result) (:stdout result))
     :dim       5
     :calendars (cal/now-triple)}))

;; ── Identity dispatcher ───────────────────────────────────────────────────────

(defn identity-dispatch!
  "Route to idv1–idv5 by variant keyword.
   :idv1 → Kerberos, :idv2 → OpenLDAP, :idv3 → OIDC, :idv4 → SAML, :idv5 → PAM"
  [variant opts]
  (case variant
    :idv1 (authenticate-kerberos! opts)
    :idv2 (ldap-lookup opts)
    :idv3 (oidc-token! opts)
    :idv4 (saml-parse-assertion opts)
    :idv5 (pam-lookup opts)
    {:ok false :error (str "Unknown identity variant: " variant)
     :available [:idv1 :idv2 :idv3 :idv4 :idv5]}))

;; ── authenticate! — governed entry point ─────────────────────────────────────

(defn authenticate!
  "Governed entry point for IDNT opcode.
   Dispatches to the appropriate identity provider by variant.

   opts:
     :provider  — :idv1 | :idv2 | :idv3 | :idv4 | :idv5
     :dry-run   — if true, perform non-destructive probe only
     (other opts passed through to the variant handler)

   Returns a zero-arg thunk per govern contract."
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [variant (get opts :provider :idv1)
            result  (identity-dispatch! variant opts)]
        (assoc result :time (select-keys t [:iso :path]))))))
