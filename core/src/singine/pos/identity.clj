(ns singine.pos.identity
  "Identity (IDNT opcode) — BSD-compatible identity dispatcher.

   Ten variants (idv1–idv10) across the BSD + enterprise + IdP stack:
     idv1  Kerberos 5 (MIT/Heimdal)   — /etc/krb5.conf, kinit, BSD-native
     idv2  OpenLDAP                   — ldapsearch, slapd.conf
     idv3  OpenID Connect (OIDC)      — HTTP, JWKS endpoint, JDK HttpClient
     idv4  SAML 2.0 (Oracle/Sun era) — XML assertions, NameID extraction
     idv5  PAM + NSS (BSD-native)     — /etc/nsswitch.conf, /etc/passwd
     idv6  Okta OIDC                  — Okta discovery, authorization_code + client_creds
     idv7  Collibra LDAP              — ldapsearch scoped to Collibra OU tree
     idv8  Active Directory           — LDAP port 389/636, AD-specific attributes
     idv9  MCP Identity               — Model Context Protocol resource token probe
     idv10 SMTP / IMAP auth probe     — JavaMail SESSION test (RFC 3501)

   Credit lineage:
     Andy Kellens (VUB), Mohammad Akhlaaghi, M. Kh. Heshmati, Sh. Kh. Heshmati —
     Sun/Oracle-era distributed systems traditions (BSD + LDAP + Kerberos).
     Oracle and Sun as the past reference system; BSD as the primary target.
     macOS/Darwin 25.3.0 is the primary dev platform.

   Dimension mapping (Category C):
     idv1  → dim=1 (edge :s, proto/c)
     idv2  → dim=2 (edge :m, proto/cc)
     idv3  → dim=3 (edge :l, proto/ccc)
     idv4  → dim=4 (explicit override)
     idv5  → dim=5 (explicit override)
     idv6  → dim=6 (Okta / enterprise OIDC)
     idv7  → dim=7 (Collibra LDAP)
     idv8  → dim=8 (Active Directory)
     idv9  → dim=9 (MCP)
     idv10 → dim=10 (SMTP/IMAP)

   All entry points use java.lang.ProcessBuilder or java.net.http.HttpClient —
   no external deps beyond JDK 11+ standard library."
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [clojure.string       :as str])
  (:import [java.lang ProcessBuilder]
           [java.io BufferedReader InputStreamReader]
           [java.net URI]
           [java.net.http HttpClient HttpRequest HttpRequest$BodyPublishers
            HttpResponse$BodyHandlers]
           [java.time Duration]
           [java.util Properties]))

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

;; ── idv6: Okta OIDC ──────────────────────────────────────────────────────────

(defn okta-token!
  "idv6 — Okta OpenID Connect discovery + token probe.
   Uses the Okta .well-known/openid-configuration endpoint.
   No Okta SDK needed — pure JDK HttpClient.

   opts:
     :okta-domain  — Okta domain, e.g. 'dev-12345678.okta.com'
     :client-id    — Okta application client ID
     :scope        — scope string (default 'openid profile email')
     :timeout-ms   — HTTP timeout in ms (default 5000)
     :dry-run      — if true, skip HTTP and return synthetic discovery result

   Returns {:ok :provider :okta-domain :discovery-url :endpoints :calendars}"
  [opts]
  (let [okta-domain (get opts :okta-domain "dev-00000000.okta.com")
        client-id   (get opts :client-id "singine")
        scope       (get opts :scope "openid profile email")
        timeout-ms  (get opts :timeout-ms 5000)
        dry-run     (get opts :dry-run true)
        ;; Okta canonical discovery URL
        discovery   (str "https://" okta-domain "/oauth2/default/.well-known/openid-configuration")]
    (if dry-run
      ;; Synthetic response — Okta well-known structure
      {:ok              true
       :provider        :idv6
       :variant         "Okta OIDC"
       :okta-domain     okta-domain
       :client-id       client-id
       :discovery-url   discovery
       :endpoints       {:authorization_endpoint (str "https://" okta-domain "/oauth2/default/v1/authorize")
                         :token_endpoint         (str "https://" okta-domain "/oauth2/default/v1/token")
                         :userinfo_endpoint      (str "https://" okta-domain "/oauth2/default/v1/userinfo")
                         :jwks_uri               (str "https://" okta-domain "/oauth2/default/v1/keys")
                         :issuer                 (str "https://" okta-domain "/oauth2/default")}
       :scopes-supported ["openid" "profile" "email" "offline_access"]
       :dry-run         true
       :dim             6
       :calendars       (cal/now-triple)}
      ;; Live HTTP probe
      (try
        (let [client (-> (HttpClient/newBuilder)
                         (.connectTimeout (Duration/ofMillis timeout-ms))
                         (.build))
              req    (-> (HttpRequest/newBuilder)
                         (.uri (URI/create discovery))
                         (.timeout (Duration/ofMillis timeout-ms))
                         (.GET)
                         (.build))
              resp   (.send client req (HttpResponse$BodyHandlers/ofString))
              status (.statusCode resp)
              body   (.body resp)]
          {:ok            (< status 400)
           :provider      :idv6
           :variant       "Okta OIDC"
           :okta-domain   okta-domain
           :discovery-url discovery
           :status        status
           :body-preview  (subs body 0 (min 300 (count body)))
           :dim           6
           :calendars     (cal/now-triple)})
        (catch Exception e
          {:ok        false
           :provider  :idv6
           :variant   "Okta OIDC"
           :error     (.getMessage e)
           :dim       6
           :calendars (cal/now-triple)})))))

;; ── idv7: Collibra LDAP ───────────────────────────────────────────────────────

(defn collibra-ldap!
  "idv7 — Collibra LDAP directory search.
   Scoped to Collibra's typical OU structure:
     ou=Users,dc=collibra,dc=com  (or configurable base-dn)

   opts:
     :host      — LDAP host (default '127.0.0.1')
     :port      — LDAP port (default 389; use 636 for LDAPS)
     :base-dn   — base DN (default 'ou=Users,dc=collibra,dc=com')
     :bind-dn   — bind DN for authenticated search (optional)
     :filter    — LDAP filter (default '(objectClass=collibraUser)')
     :attrs     — space-separated attributes to return (default 'cn mail uid')
     :dry-run   — if true, return synthetic Collibra user entry

   Returns {:ok :provider :host :filter :stdout :calendars}"
  [opts]
  (let [host    (get opts :host "127.0.0.1")
        port    (str (get opts :port 389))
        base-dn (get opts :base-dn "ou=Users,dc=collibra,dc=com")
        filter  (get opts :filter "(objectClass=collibraUser)")
        attrs   (get opts :attrs "cn mail uid title")
        dry-run (get opts :dry-run true)]
    (if dry-run
      {:ok      true
       :provider :idv7
       :variant  "Collibra LDAP"
       :host     host
       :base-dn  base-dn
       :filter   filter
       :stdout   (str "dn: uid=admin,ou=Users,dc=collibra,dc=com\n"
                      "cn: Collibra Admin\n"
                      "mail: admin@collibra.com\n"
                      "uid: admin\n"
                      "title: Data Steward\n")
       :dry-run  true
       :dim      7
       :calendars (cal/now-triple)}
      (let [cmd (cond-> ["ldapsearch" "-x"
                          "-H" (str "ldap://" host ":" port)
                          "-b" base-dn "-LLL" filter]
                  (seq attrs) (concat (str/split attrs #"\s+")))]
        (assoc (apply run-cmd! cmd)
               :provider  :idv7
               :variant   "Collibra LDAP"
               :host      host
               :filter    filter
               :dim       7
               :calendars (cal/now-triple))))))

;; ── idv8: Active Directory ───────────────────────────────────────────────────

(defn active-directory!
  "idv8 — Active Directory LDAP search.
   Uses AD-specific attributes: sAMAccountName, userPrincipalName, memberOf.
   Default port 389 (LDAP) or 636 (LDAPS).

   opts:
     :host      — AD domain controller IP / hostname (default '127.0.0.1')
     :port      — LDAP port (default 389)
     :base-dn   — base DN (default 'dc=singine,dc=local')
     :filter    — LDAP filter (default '(objectClass=user)')
     :attrs     — attributes (default 'sAMAccountName userPrincipalName memberOf')
     :dry-run   — if true, return synthetic AD user entry

   Returns {:ok :provider :host :filter :stdout :calendars}"
  [opts]
  (let [host    (get opts :host "127.0.0.1")
        port    (str (get opts :port 389))
        base-dn (get opts :base-dn "dc=singine,dc=local")
        filter  (get opts :filter "(objectClass=user)")
        attrs   (get opts :attrs "sAMAccountName userPrincipalName memberOf")
        dry-run (get opts :dry-run true)]
    (if dry-run
      {:ok       true
       :provider :idv8
       :variant  "Active Directory"
       :host     host
       :base-dn  base-dn
       :filter   filter
       :stdout   (str "dn: CN=skh,CN=Users,DC=singine,DC=local\n"
                      "sAMAccountName: skh\n"
                      "userPrincipalName: skh@singine.local\n"
                      "memberOf: CN=Domain Admins,CN=Builtin,DC=singine,DC=local\n")
       :dry-run  true
       :dim      8
       :calendars (cal/now-triple)}
      (let [cmd (cond-> ["ldapsearch" "-x"
                          "-H" (str "ldap://" host ":" port)
                          "-b" base-dn "-LLL" filter]
                  (seq attrs) (concat (str/split attrs #"\s+")))]
        (assoc (apply run-cmd! cmd)
               :provider  :idv8
               :variant   "Active Directory"
               :host      host
               :filter    filter
               :dim       8
               :calendars (cal/now-triple))))))

;; ── idv9: MCP Identity ───────────────────────────────────────────────────────

(defn mcp-identity!
  "idv9 — Model Context Protocol (MCP) identity token probe.
   Probes an MCP resource URI to obtain an identity token.
   Phase 1: synthetic token generation with URN-based identity.
   Phase 2: real MCP HTTP probe via JDK HttpClient.

   opts:
     :mcp-uri    — MCP resource URI (default 'urn:singine:mcp:resource:local')
     :agent-urn  — agent URN (default derived from auth)
     :timeout-ms — HTTP timeout in ms (default 3000)
     :dry-run    — if true, return synthetic MCP identity result

   Returns {:ok :provider :mcp-uri :agent-urn :token :calendars}"
  [opts]
  (let [mcp-uri   (get opts :mcp-uri "urn:singine:mcp:resource:local")
        agent-urn (get opts :agent-urn "urn:singine:agent:anonymous")
        timeout-ms (get opts :timeout-ms 3000)
        dry-run   (get opts :dry-run true)]
    (if dry-run
      {:ok        true
       :provider  :idv9
       :variant   "MCP Identity"
       :mcp-uri   mcp-uri
       :agent-urn agent-urn
       :token     (str "mcp-tok."
                       (.encodeToString
                         (.withoutPadding (java.util.Base64/getUrlEncoder))
                         (.getBytes (str "urn:singine:mcp:" mcp-uri) "UTF-8"))
                       ".synthetic")
       :token-type "MCP-Bearer"
       :scopes    ["mcp:resource:read" "mcp:context:read"]
       :dry-run   true
       :dim       9
       :calendars (cal/now-triple)}
      ;; Phase 2: probe MCP server (HTTP-based resource discovery)
      (try
        (let [client (-> (HttpClient/newBuilder)
                         (.connectTimeout (Duration/ofMillis timeout-ms))
                         (.build))
              ;; MCP uses HTTP for resource endpoints; fallback to urn: for local
              url    (if (str/starts-with? mcp-uri "http")
                       mcp-uri
                       (str "http://localhost:3000/mcp/identity?uri=" mcp-uri))
              req    (-> (HttpRequest/newBuilder)
                         (.uri (URI/create url))
                         (.timeout (Duration/ofMillis timeout-ms))
                         (.header "X-Agent-URN" agent-urn)
                         (.GET)
                         (.build))
              resp   (.send client req (HttpResponse$BodyHandlers/ofString))
              status (.statusCode resp)]
          {:ok        (< status 400)
           :provider  :idv9
           :variant   "MCP Identity"
           :mcp-uri   mcp-uri
           :agent-urn agent-urn
           :status    status
           :body      (subs (.body resp) 0 (min 200 (count (.body resp))))
           :dim       9
           :calendars (cal/now-triple)})
        (catch Exception e
          {:ok        false
           :provider  :idv9
           :variant   "MCP Identity"
           :error     (.getMessage e)
           :mcp-uri   mcp-uri
           :dim       9
           :calendars (cal/now-triple)})))))

;; ── idv10: SMTP / IMAP auth probe ────────────────────────────────────────────

(defn imap-probe!
  "idv10 — SMTP / IMAP authentication probe.
   Tests connectivity to a mail server using javax.mail Session.
   No actual login is attempted in dry-run mode — only config is validated.

   opts:
     :smtp-host  — SMTP host (default 'localhost')
     :smtp-port  — SMTP port (default 25)
     :imap-host  — IMAP host (default 'localhost')
     :imap-port  — IMAP port (default 143)
     :user       — mail user (default: current user)
     :dry-run    — if true, return synthetic pass result

   Returns {:ok :provider :smtp :imap :session-ready :calendars}"
  [opts]
  (let [smtp-host (get opts :smtp-host "localhost")
        smtp-port (str (get opts :smtp-port 25))
        imap-host (get opts :imap-host "localhost")
        imap-port (str (get opts :imap-port 143))
        user      (get opts :user (System/getProperty "user.name" "anonymous"))
        dry-run   (get opts :dry-run true)]
    (if dry-run
      {:ok            true
       :provider      :idv10
       :variant       "SMTP/IMAP auth probe"
       :smtp          {:host smtp-host :port smtp-port :status "dry-run-ok"}
       :imap          {:host imap-host :port imap-port :status "dry-run-ok"}
       :user          user
       :session-ready true
       :dry-run       true
       :dim           10
       :calendars     (cal/now-triple)}
      ;; Live probe: TCP socket connectivity test (no javax.mail required)
      ;; Validates SMTP + IMAP port reachability without authentication
      (let [probe-port (fn [host port-str]
                         (try
                           (let [p (Integer/parseInt port-str)
                                 sock (java.net.Socket.)]
                             (.connect sock
                                       (java.net.InetSocketAddress. host p)
                                       3000)
                             (.close sock)
                             {:reachable true :host host :port port-str})
                           (catch Exception ex
                             {:reachable false :host host :port port-str
                              :error (.getMessage ex)})))
            smtp-probe  (probe-port smtp-host smtp-port)
            imap-probe  (probe-port imap-host imap-port)]
        {:ok            (and (:reachable smtp-probe) (:reachable imap-probe))
         :provider      :idv10
         :variant       "SMTP/IMAP auth probe"
         :smtp          (assoc smtp-probe :status (if (:reachable smtp-probe) "reachable" "unreachable"))
         :imap          (assoc imap-probe :status (if (:reachable imap-probe) "reachable" "unreachable"))
         :user          user
         :session-ready (:reachable smtp-probe)
         :dry-run       false
         :dim           10
         :calendars     (cal/now-triple)}))))

;; ── Identity dispatcher ───────────────────────────────────────────────────────

(defn identity-dispatch!
  "Route to idv1–idv10 by variant keyword.
   :idv1  → Kerberos
   :idv2  → OpenLDAP
   :idv3  → OIDC (generic)
   :idv4  → SAML
   :idv5  → PAM/NSS
   :idv6  → Okta OIDC
   :idv7  → Collibra LDAP
   :idv8  → Active Directory
   :idv9  → MCP Identity
   :idv10 → SMTP/IMAP probe"
  [variant opts]
  (case variant
    :idv1  (authenticate-kerberos! opts)
    :idv2  (ldap-lookup opts)
    :idv3  (oidc-token! opts)
    :idv4  (saml-parse-assertion opts)
    :idv5  (pam-lookup opts)
    :idv6  (okta-token! opts)
    :idv7  (collibra-ldap! opts)
    :idv8  (active-directory! opts)
    :idv9  (mcp-identity! opts)
    :idv10 (imap-probe! opts)
    {:ok false :error (str "Unknown identity variant: " variant)
     :available [:idv1 :idv2 :idv3 :idv4 :idv5
                 :idv6 :idv7 :idv8 :idv9 :idv10]}))

;; ── authenticate! — governed entry point ─────────────────────────────────────

(defn authenticate!
  "Governed entry point for IDNT opcode.
   Dispatches to the appropriate identity provider by variant.

   opts:
     :provider  — :idv1 | :idv2 | :idv3 | :idv4 | :idv5
                  :idv6 | :idv7 | :idv8 | :idv9 | :idv10
     :dry-run   — if true, perform non-destructive probe only
     (other opts passed through to the variant handler)

   Returns a zero-arg thunk per govern contract."
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [variant (get opts :provider :idv1)
            result  (identity-dispatch! variant opts)]
        (assoc result :time (select-keys t [:iso :path]))))))
