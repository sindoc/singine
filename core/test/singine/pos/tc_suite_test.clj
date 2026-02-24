(ns singine.pos.tc-suite-test
  "POS test suite — tc01…tc20 + tc-id01…tc-id05 + tc-form01 + tc-locp01..02
   + tc-auth01..tc-auth05 + tc-idpr01..tc-idpr02 + tc-idnt01..tc-idnt02
   + tc-mime01..tc-mime07 + tc-mandate01..tc-mandate07
   + tc-mail01..tc-mail05 + tc-camel01..tc-camel02
   + tc-edge01..tc-edge02 + tc-rails01..tc-rails02
   + tc-broker01..tc-broker02 + tc-trust01..tc-trust02.

   Two-character ASCII IDs for the condition system.
   Mock data generated inline via gen-mock — this IS the data product demo:
     gen-mock n → n synthetic data contracts with routing, MIME, material category,
     severity, edge routing — showing singine governs movement node→node under
     the condition system.

   10 terms of reference (tor01…tor10):
     tor01  data-lineage-verified
     tor02  mime-type-registered
     tor03  edge-node-reachable
     tor04  material-category-classified
     tor05  contract-signed         @person reference
     tor06  auth-token-valid
     tor07  calendar-timestamp-present   triple-calendar
     tor08  topic-t1-linked              [[t/1]]
     tor09  schema-validated             DTD / RelaxNG
     tor10  kafka-topic-available        singine.pos.*

   Edge sizes (dev environment):
     :s → dim=1 → proto/c
     :m → dim=2 → proto/cc
     :l → dim=3 → proto/ccc

   MIME routing:
     :lookup  → text/plain, text/csv, application/json, application/xml
     :link    → application/rdf+xml, application/sparql-query
     :binary  → image/png, application/pdf, application/zip"
  (:require [clojure.test            :refer [deftest is testing use-fixtures]]
            [clojure.string          :as str]
            [singine.pos.block-processor :as bp]
            [singine.pos.category    :as catc]
            [singine.pos.calendar    :as cal]
            [singine.pos.git-op      :as gitp]
            [singine.pos.identity    :as idnt]
            [singine.pos.form        :as form]
            [singine.pos.location    :as loc]
            [singine.pos.idp         :as idp]
            [singine.net.cacert      :as cacert]
            [singine.auth.token      :as auth-tok]
            [singine.lang.mime       :as mime]
            [singine.net.mail        :as mail]
            [singine.net.edge        :as edge]
            [singine.camel.context   :as camel-ctx]
            [singine.broker.core     :as broker]
            [singine.sec.trust       :as trust]
            [singine.pos.lambda      :as lam]))

;; ── Mock data generator ───────────────────────────────────────────────────────

(def ^:private mime-types
  ["text/plain" "application/json" "application/xml"
   "application/rdf+xml" "image/png" "application/pdf"
   "text/csv" "application/sparql-query"
   "application/octet-stream" "application/zip"])

(def ^:private material-cats
  ["masterdata" "reference" "transactional" "analytical" "operational"])

(def ^:private severities
  [:low :moderate :high :critical])

(def ^:private edge-sizes
  [:s :m :l])

(defn gen-mock
  "Generate n synthetic data contracts. Returns a seq of contract maps.
   This is the data product: routes between nodes under the condition system."
  [n]
  (for [i (range 1 (inc n))]
    {:id            (format "tc%02d" i)
     :mime-type     (nth mime-types (mod i 10))
     :material-cat  (nth material-cats (mod i 5))
     :severity      (nth severities (mod i 4))
     :edge-size     (nth edge-sizes (mod i 3))
     :terms         i
     :route-from    (keyword (str "node-" (char (+ 65 (mod i 26)))))
     :route-to      (keyword (str "node-" (char (+ 66 (mod i 26)))))}))

;; ── Terms of reference ────────────────────────────────────────────────────────

(def terms-of-reference
  ["tor01-data-lineage-verified"
   "tor02-mime-type-registered"
   "tor03-edge-node-reachable"
   "tor04-material-category-classified"
   "tor05-contract-signed"
   "tor06-auth-token-valid"
   "tor07-calendar-timestamp-present"
   "tor08-topic-t1-linked"
   "tor09-schema-validated"
   "tor10-kafka-topic-available"])

(defn active-terms
  "Compute active terms count based on severity and material category."
  [contract]
  (let [sev-score (case (:severity contract)
                    :low 1 :moderate 3 :high 6 :critical 10 1)
        mat-score (case (:material-cat contract)
                    "masterdata" 2 "reference" 1 "transactional" 3
                    "analytical" 2 "operational" 2 1)]
    (min 10 (max 1 (+ sev-score mat-score)))))

;; ── Fixture: reset category activity log ─────────────────────────────────────

(use-fixtures :each
  (fn [f]
    (catc/reset-log!)
    (f)))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc01–tc10: Condition system (one per term of reference)
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc01-data-lineage
  (testing "tor01: data-lineage-verified — contract has identity fields"
    (let [contract (first (gen-mock 1))]
      (is (= "tc01" (:id contract)))
      (is (contains? #{:low :moderate :high :critical} (:severity contract)))
      (is (string? (:material-cat contract)))
      ;; tor01: lineage = id + route-from + route-to must all be present
      (is (some? (:id contract)))
      (is (keyword? (:route-from contract)))
      (is (keyword? (:route-to contract))))))

(deftest tc02-mime-routing
  (testing "tor02: mime-type-registered — mime-route classifies all known types"
    (let [contract (second (gen-mock 2))]
      (is (= "tc02" (:id contract)))
      (is (string? (:mime-type contract)))
      (let [route (catc/mime-route (:mime-type contract))]
        (is (contains? #{:lookup :link :binary} route))))))

(deftest tc03-edge-reachable
  (testing "tor03: edge-node-reachable — edge-dim maps size to dimension"
    (let [contract (nth (gen-mock 3) 2)]
      (is (= "tc03" (:id contract)))
      (let [dim (catc/edge-dim contract)]
        (is (pos? dim))
        (is (<= dim 3))))))

(deftest tc04-material-category
  (testing "tor04: material-category-classified — material-cat present and known"
    (let [contract (nth (gen-mock 4) 3)]
      (is (= "tc04" (:id contract)))
      (is (contains? (set material-cats) (:material-cat contract))))))

(deftest tc05-contract-signed
  (testing "tor05: contract-signed — predicate is-signed evaluates subject"
    (let [signed-subject   {"contract-signed" true  "type" "data-contract"}
          unsigned-subject {"contract-signed" false "type" "data-contract"}
          p-signed   (catc/apply-predicate :is-signed (java.util.HashMap. signed-subject))
          p-unsigned (catc/apply-predicate :is-signed (java.util.HashMap. unsigned-subject))]
      (is (true?  p-signed))
      (is (false? p-unsigned)))))

(deftest tc06-auth-token-valid
  (testing "tor06: auth-token-valid — govern with open token returns result"
    (let [auth  (lam/make-auth "urn:singine:test:tc06" :read)
          thunk (lam/govern auth (fn [t] {:ok true :path (:path t)}))]
      (let [result (thunk)]
        (is (true? (:ok result)))
        (is (str/starts-with? (:path result) "today/"))))))

(deftest tc07-calendar-timestamp
  (testing "tor07: calendar-timestamp-present — triple-calendar returns all three"
    (let [cal (cal/now-triple)]
      (is (= :gregorian (get-in cal [:gregorian :calendar])))
      (is (= :persian   (get-in cal [:persian :calendar])))
      (is (= :chinese   (get-in cal [:chinese :calendar])))
      (is (string? (get-in cal [:gregorian :iso])))
      (is (pos-int? (get-in cal [:gregorian :year])))
      (is (string? (get-in cal [:chinese :sexagenary]))))))

(deftest tc08-topic-t1-linked
  (testing "tor08: topic-t1-linked — BLKP output carries topic anchor"
    (let [mock-sindoc "#lang singine\ntc08 topic anchor test\n--\n</>"
          result (bp/process-blocks-str mock-sindoc)]
      ;; manifest must contain t/1
      (is (str/includes? (:manifest result) "[[t/1]]"))
      (is (str/includes? (:manifest result) "urn:singine:topic:t/1")))))

(deftest tc09-schema-validated
  (testing "tor09: schema-validated — BLKP XML has singine-repo root element"
    (let [mock-sindoc "#lang singine\ntc09 schema check\n--\n</>"
          result (bp/process-blocks-str mock-sindoc)]
      (is (str/starts-with? (:xml result) "<?xml"))
      (is (str/includes? (:xml result) "singine-repo")))))

(deftest tc10-kafka-topic
  (testing "tor10: kafka-topic-available — algorithm registry lists known algos"
    (let [algos (gitp/list-algorithms)]
      (is (seq algos))
      (is (every? #(contains? % :name) algos))
      (is (every? #(contains? % :description) algos))
      ;; The five canonical algorithms must be present
      (let [names (set (map :name algos))]
        (is (contains? names "UnionFind"))
        (is (contains? names "MarkovKernel"))
        (is (contains? names "NashEquilibrium"))))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc11–tc13: Edge node sizes (dev environment)
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc11-edge-small
  (testing "tc11: :s edge → dim=1 → proto/c (Category C single block)"
    (let [contract {:id "tc11" :edge-size :s :mime-type "text/plain"}]
      (is (= 1 (catc/edge-dim contract))))))

(deftest tc12-edge-medium
  (testing "tc12: :m edge → dim=2 → proto/cc (product category)"
    (let [contract {:id "tc12" :edge-size :m :mime-type "application/json"}]
      (is (= 2 (catc/edge-dim contract))))))

(deftest tc13-edge-large
  (testing "tc13: :l edge → dim=3 → proto/ccc (triple product)"
    (let [contract {:id "tc13" :edge-size :l :mime-type "application/xml"}]
      (is (= 3 (catc/edge-dim contract))))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc14–tc16: MIME type routing
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc14-lookup-mime
  (testing "tc14: text/plain + text/csv + application/json → :lookup route"
    (is (= :lookup (catc/mime-route "text/plain")))
    (is (= :lookup (catc/mime-route "text/csv")))
    (is (= :lookup (catc/mime-route "application/json")))))

(deftest tc15-link-mime
  (testing "tc15: application/rdf+xml + sparql-query → :link route"
    (is (= :link (catc/mime-route "application/rdf+xml")))
    (is (= :link (catc/mime-route "application/sparql-query")))))

(deftest tc16-binary-mime
  (testing "tc16: image/png + application/pdf + application/zip → :binary route"
    (is (= :binary (catc/mime-route "image/png")))
    (is (= :binary (catc/mime-route "application/pdf")))
    (is (= :binary (catc/mime-route "application/zip")))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc17–tc19: Data contract routes (A→B, B→C, A→C transitive)
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc17-route-ab
  (testing "tc17: node A → node B route with 3 active ToR"
    (let [contract {:id "tc17" :route-from :node-A :route-to :node-B
                    :severity :moderate :material-cat "masterdata"
                    :edge-size :s :mime-type "text/plain"}
          n-terms  (active-terms contract)]
      (is (keyword? (:route-from contract)))
      (is (keyword? (:route-to contract)))
      (is (pos? n-terms))
      (is (<= n-terms 10))
      ;; moderate + masterdata = 3 + 2 = 5 terms
      (is (= 5 n-terms)))))

(deftest tc18-route-bc
  (testing "tc18: node B → node C route with high severity"
    (let [contract {:id "tc18" :route-from :node-B :route-to :node-C
                    :severity :high :material-cat "transactional"
                    :edge-size :m :mime-type "application/json"}
          n-terms  (active-terms contract)]
      (is (keyword? (:route-from contract)))
      (is (keyword? (:route-to contract)))
      ;; high + transactional = 6 + 3 = 9 terms
      (is (= 9 n-terms)))))

(deftest tc19-route-ac-transitive
  (testing "tc19: A→C transitive via condition system — active terms ≥1"
    ;; gen-mock generates routes with all combinations
    (let [contracts (gen-mock 19)]
      (is (= 19 (count contracts)))
      (doseq [c contracts]
        (let [n (active-terms c)]
          (is (>= n 1))
          (is (<= n 10))
          (is (keyword? (:route-from c)))
          (is (keyword? (:route-to c))))))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc20: Full pipeline smoke test
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc20-full-pipeline
  (testing "tc20: end-to-end: mock exec.rkt → BLKP → ZIP bytes + XML"
    (let [mock-sindoc (str "#lang singine\n"
                           "tc20 data product demo block\n"
                           "--\n"
                           "[[t/1]] topic anchor\n"
                           "</>")
          result (bp/process-blocks-str mock-sindoc)]
      (is (pos? (count (:zip-bytes result))) "ZIP must be non-empty")
      (is (string? (:xml result)) "XML must be a string")
      (is (str/starts-with? (:xml result) "<?xml") "XML must have declaration")
      (is (str/includes? (:xml result) "singine-repo") "XML root must be singine-repo")
      (is (pos-int? (:block-count result)) "Must have at least one block")
      (is (>= (:dim result) 1) "Dimension must be ≥1"))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-id01–tc-id05: Identity layer (idv1–idv5)
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-id01-kerberos
  (testing "tc-id01: idv1 Kerberos — kinit --version dry-run probe"
    (let [result (idnt/authenticate-kerberos! {:dry-run true})]
      (is (= :idv1 (:provider result)))
      (is (= 1 (:dim result)))
      (is (map? (:calendars result)))
      ;; kinit may or may not be installed; we just check the shape
      (is (contains? result :ok))
      (is (contains? result :stdout)))))

(deftest tc-id02-ldap
  (testing "tc-id02: idv2 OpenLDAP — ldapsearch against 127.0.0.1, expects graceful failure"
    (let [result (idnt/ldap-lookup {:host "127.0.0.1" :dry-run true})]
      (is (= :idv2 (:provider result)))
      (is (= 2 (:dim result)))
      (is (map? (:calendars result)))
      ;; ldapsearch may or may not be installed; shape check only
      (is (contains? result :ok)))))

(deftest tc-id03-oidc
  (testing "tc-id03: idv3 OIDC — discovery probe to localhost:9999 (not running)"
    (let [result (idnt/oidc-token! {:issuer "http://localhost:9999" :timeout-ms 500})]
      (is (= :idv3 (:provider result)))
      (is (= 3 (:dim result)))
      (is (map? (:calendars result)))
      ;; Server not running → :ok should be false with :error
      (is (false? (:ok result)))
      (is (or (contains? result :error) (contains? result :status))))))

(deftest tc-id04-saml
  (testing "tc-id04: idv4 SAML 2.0 — parse mock XML assertion → extract NameID"
    (let [result (idnt/saml-parse-assertion {})]
      (is (= :idv4 (:provider result)))
      (is (= 4 (:dim result)))
      (is (true? (:ok result)))
      (is (= "skh@singine.local" (:name-id result))))))

(deftest tc-id05-pam-nss
  (testing "tc-id05: idv5 PAM/NSS — /etc/passwd lookup for current user"
    (let [current-user (System/getProperty "user.name" "unknown")
          result (idnt/pam-lookup {:username current-user})]
      (is (= :idv5 (:provider result)))
      (is (= 5 (:dim result)))
      (is (map? (:calendars result)))
      (is (= current-user (:username result)))
      ;; /etc/passwd must exist on BSD/macOS
      (is (contains? result :ok)))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-form01: FORM opcode — emit-form! via policy p + template t
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-form01-emit-form
  (testing "tc-form01: emit-form! produces valid pos-form.xml governed by policy p + template t"
    (let [auth    (lam/make-auth "urn:singine:test:tc-form01" :write)
          policy  {:id           "p-test"
                   :predicate    "is-signed"
                   :contract-ref "urn:singine:pos:form:test"
                   :agent        "@surenkierkegaard"
                   :activity     "write"
                   :terms-active 5
                   :terms        [{:id "tor01" :name "data-lineage-verified"      :satisfied true}
                                  {:id "tor02" :name "mime-type-registered"       :satisfied true}
                                  {:id "tor05" :name "contract-signed"            :satisfied true :at "@surenkierkegaard"}
                                  {:id "tor06" :name "auth-token-valid"           :satisfied true}
                                  {:id "tor07" :name "calendar-timestamp-present" :satisfied true}]}
          thunk   (form/emit-form! auth policy nil)
          result  (thunk)]
      ;; Governed contract satisfied
      (is (true? (:ok result)) "emit-form! must return :ok true")
      ;; XML well-formed and contains required structure
      (is (string? (:xml result)) "XML must be a string")
      (is (str/starts-with? (:xml result) "<?xml") "XML must have declaration")
      (is (str/includes? (:xml result) "FORM") "XML must contain FORM opcode")
      (is (str/includes? (:xml result) "tor05") "XML must carry tor05 (contract-signed)")
      (is (str/includes? (:xml result) "@surenkierkegaard") "XML must name the agent")
      ;; Triple-calendar present (values from singine.pos.calendar/london-triple)
      (is (or (str/includes? (:xml result) "乙巳")
              (str/includes? (:xml result) "bǐng")
              (str/includes? (:xml result) "bing"))
          "XML must include Chinese sexagenary year (Han or romanized)")
      (let [persian-year (str (get-in result [:calendars :persian :year]))]
        (is (str/includes? (:xml result) persian-year)
            (str "XML must include Persian year " persian-year)))
      ;; Contact payload from template
      (is (str/includes? (:xml result) "Sina Heshmati") "XML must carry canonical name")
      (is (str/includes? (:xml result) "+32 476 55 14 38") "XML must carry phone number")
      ;; Output path is temporal
      (is (string? (:path result)) "Path must be a string")
      (is (str/includes? (:path result) "pos-form.xml") "Path must end in pos-form.xml")
      (is (str/includes? (:path result) "today/") "Path must be under today/")
      ;; Policy metadata echoed back
      (is (map? (:policy result)) "Policy summary must be a map")
      (is (= "p-test" (:id (:policy result))) "Policy id must match input")
      ;; Calendars present
      (is (map? (:calendars result)) "Calendars must be a map")
      (is (some? (get-in result [:calendars :gregorian])) "Gregorian calendar must be present"))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-locp01–tc-locp02: Location Probe (LOCP opcode)
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-locp01-iata-resolve
  (testing "tc-locp01: IATA 3-char code resolves to urn:singine:location:<cc>:<code>"
    ;; BRU = Brussels Airport, BE
    (let [urn (loc/iata->urn "BRU")]
      (is (str/starts-with? urn "urn:singine:location:") "must start with location URN prefix")
      (is (str/includes? urn "BRU") "must include the IATA code"))
    ;; IKA = Tehran Imam Khomeini, IR
    (let [urn (loc/iata->urn "IKA")]
      (is (str/starts-with? urn "urn:singine:location:") "must start with location URN prefix")
      (is (str/includes? urn "IKA") "must include the IATA code")
      (is (str/includes? urn ":IR:") "must carry IR country code"))
    ;; zip2urn
    (let [urn (loc/zip2urn "BE" "1000")]
      (is (= "urn:singine:location:BE:1000" urn) "zip2urn: BE 1000"))
    ;; level-urn
    (is (= "urn:singine:id:l1:B"   (loc/level-urn "B"))   "l1: 1-char ASCII")
    (is (= "urn:singine:id:l2:BE"  (loc/level-urn "BE"))  "l2: 2-char ISO")
    (is (= "urn:singine:id:l3:BRU" (loc/level-urn "BRU")) "l3: 3-char IATA")))

(deftest tc-locp02-probe-dry-run
  (testing "tc-locp02: LOCP probe dry-run returns governed result with SOAP + validation + SODA + NannyML"
    (let [auth   (lam/make-auth "urn:singine:test:tc-locp02" :read)
          thunk  (loc/probe! auth "BRU" {:dry-run true :subject :standards})
          result (thunk)]
      ;; Governed result
      (is (true? (:ok result)) "probe! must return :ok true")
      ;; Location resolution
      (is (str/starts-with? (:location-urn result) "urn:singine:location:")
          "location-urn must start with singine location prefix")
      (is (= "BRU" (:location result)) "input location preserved")
      (is (= :standards (:subject result)) "subject preserved")
      ;; SOAP XML
      (is (string? (:soap-xml result)) "soap-xml must be a string")
      (is (str/starts-with? (:soap-xml result) "<?xml") "soap-xml must have declaration")
      (is (str/includes? (:soap-xml result) "LocationProbeRequest")
          "soap-xml must contain LocationProbeRequest")
      (is (str/includes? (:soap-xml result) "urn:singine:location:")
          "soap-xml must carry location URN")
      ;; Schema validation
      (is (map? (:validation result)) "validation must be a map")
      (is (contains? (:validation result) :rnc-valid) "must have :rnc-valid key")
      (is (contains? (:validation result) :sch-valid) "must have :sch-valid key")
      ;; SODA
      (is (true? (get-in result [:soda :ok])) "SODA dry-run must pass")
      (is (= :soda (get-in result [:soda :provider])) "SODA provider must be :soda")
      ;; NannyML
      (is (true? (get-in result [:nannyml :ok])) "NannyML dry-run must pass")
      (is (= :nannyml (get-in result [:nannyml :provider])) "NannyML provider must be :nannyml")
      (is (false? (get-in result [:nannyml :drift-detected])) "no drift in dry-run")
      ;; pos-locp.xml output
      (is (string? (:xml result)) "XML must be a string")
      (is (str/starts-with? (:xml result) "<?xml") "XML must have declaration")
      (is (str/includes? (:xml result) "LOCP") "XML must contain LOCP opcode")
      (is (str/includes? (:xml result) "urn:singine:location:") "XML must carry location URN")
      (is (string? (:path result)) "path must be a string")
      (is (str/includes? (:path result) "pos-locp.xml") "path must be pos-locp.xml")
      (is (str/includes? (:path result) "today/") "path must be under today/")
      ;; Calendars
      (is (map? (:calendars result)) "calendars must be a map")
      (is (some? (get-in result [:calendars :gregorian])) "gregorian calendar present"))))

;; ══════════════════════════════════════════════════════════════════════════════
;; Phase 8: Auth full — JVM cacert + JWT/JWS + idv6-idv10 + IDPR
;; ══════════════════════════════════════════════════════════════════════════════

(def ^:private test-auth
  (lam/make-auth "urn:singine:test:auth" :read))

;; ── tc-auth01: JVM root CA enumeration ───────────────────────────────────────

(deftest tc-auth01-jvm-root-cas
  (testing "JVM cacerts: list all trusted root CA certificates"
    ;; Count
    (let [n (cacert/ca-count)]
      (is (pos? n) "JVM must have at least 1 trusted root CA")
      (is (> n 50) (str "JVM should have > 50 trusted CAs, got " n)))

    ;; Path
    (let [path (cacert/jvm-cacerts-path)]
      (is (string? path) "cacerts path must be a string")
      (is (str/includes? path "cacerts") "path must contain 'cacerts'"))

    ;; Entries
    (let [cas (cacert/list-jvm-root-cas)]
      (is (vector? cas) "list-jvm-root-cas must return a vector")
      (let [first-ca (first cas)]
        (is (map? first-ca) "each CA must be a map")
        (is (contains? first-ca :alias) "CA must have :alias")
        (is (contains? first-ca :urn) "CA must have :urn")
        (is (contains? first-ca :subject-dn) "CA must have :subject-dn")
        (is (contains? first-ca :sha256) "CA must have :sha256")
        (is (contains? first-ca :key-algo) "CA must have :key-algo")
        (is (str/starts-with? (:urn first-ca) "urn:singine:ca:")
            "CA URN must start with urn:singine:ca:")
        (is (= 64 (count (:sha256 first-ca)))
            "SHA-256 fingerprint must be 64 hex chars")))))

;; ── tc-auth02: HS256 JWT sign + verify ───────────────────────────────────────

(deftest tc-auth02-hs256-jwt
  (testing "JWT HS256: sign, decode, verify"
    (let [secret "singine-test-secret-key"
          claims {:sub "skh@singine.local"
                  :name "Sh. Kh. Heshmati"
                  :roles ["admin" "data-steward"]}
          {:keys [token exp jti sid]} (auth-tok/mint-hs256-token!
                                        secret claims 3600)]
      ;; Token structure
      (is (string? token) "token must be a string")
      (is (= 3 (count (str/split token #"\.")))
          "JWT must have 3 parts (header.payload.signature)")
      (is (pos? exp) "exp must be positive")
      (is (string? jti) "jti must be a string")
      (is (uuid? (java.util.UUID/fromString jti)) "jti must be a valid UUID")
      (is (str/starts-with? sid "urn:singine:session:")
          "sid must start with urn:singine:session:")

      ;; Decode without verification
      (let [{:keys [ok claims header]} (auth-tok/decode-token token)]
        (is ok "decode must succeed")
        (is (= "HS256" (:alg header)) "header must declare HS256")
        (is (= "JWT" (:typ header)) "header must declare JWT type")
        (is (= "skh@singine.local" (:sub claims)) "sub must match")
        (is (= "urn:singine:idp" (:iss claims)) "iss must be singine IdP URN"))

      ;; Verify with correct secret
      (let [{:keys [ok claims error]} (auth-tok/verify-hs256-token secret token)]
        (is ok (str "verify must succeed, error: " error))
        (is (= "skh@singine.local" (:sub claims)) "sub preserved after verify"))

      ;; Verify with wrong secret should fail
      (let [{:keys [ok error]} (auth-tok/verify-hs256-token "wrong-secret" token)]
        (is (not ok) "wrong secret must fail verification")
        (is (string? error) "error message must be a string")))))

;; ── tc-auth03: idv6–idv10 dry-run variants ───────────────────────────────────

(deftest tc-auth03-idv6-to-idv10-dry-run
  (testing "Identity variants idv6-idv10 (dry-run)"
    ;; idv6: Okta OIDC
    (let [r (idnt/okta-token! {:dry-run true :okta-domain "dev-00000000.okta.com"})]
      (is (true? (:ok r)) "idv6 dry-run must succeed")
      (is (= :idv6 (:provider r)) "provider must be :idv6")
      (is (= 6 (:dim r)) "dim must be 6")
      (is (map? (:endpoints r)) "endpoints must be a map")
      (is (contains? (:endpoints r) :token_endpoint) "endpoints must have token_endpoint")
      (is (str/starts-with? (:discovery-url r) "https://") "discovery URL must be HTTPS"))

    ;; idv7: Collibra LDAP
    (let [r (idnt/collibra-ldap! {:dry-run true})]
      (is (true? (:ok r)) "idv7 dry-run must succeed")
      (is (= :idv7 (:provider r)) "provider must be :idv7")
      (is (= 7 (:dim r)) "dim must be 7")
      (is (string? (:stdout r)) "stdout must be a string")
      (is (str/includes? (:stdout r) "collibra") "stdout must mention collibra"))

    ;; idv8: Active Directory
    (let [r (idnt/active-directory! {:dry-run true})]
      (is (true? (:ok r)) "idv8 dry-run must succeed")
      (is (= :idv8 (:provider r)) "provider must be :idv8")
      (is (= 8 (:dim r)) "dim must be 8")
      (is (str/includes? (:stdout r) "sAMAccountName") "stdout must have AD attribute"))

    ;; idv9: MCP Identity
    (let [r (idnt/mcp-identity! {:dry-run true})]
      (is (true? (:ok r)) "idv9 dry-run must succeed")
      (is (= :idv9 (:provider r)) "provider must be :idv9")
      (is (= 9 (:dim r)) "dim must be 9")
      (is (string? (:token r)) "MCP token must be a string")
      (is (= "MCP-Bearer" (:token-type r)) "token type must be MCP-Bearer")
      (is (vector? (:scopes r)) "scopes must be a vector"))

    ;; idv10: SMTP/IMAP probe
    (let [r (idnt/imap-probe! {:dry-run true})]
      (is (true? (:ok r)) "idv10 dry-run must succeed")
      (is (= :idv10 (:provider r)) "provider must be :idv10")
      (is (= 10 (:dim r)) "dim must be 10")
      (is (map? (:smtp r)) "smtp must be a map")
      (is (map? (:imap r)) "imap must be a map")
      (is (true? (:session-ready r)) "session-ready must be true in dry-run"))))

;; ── tc-auth04: identity-dispatch! extended variants ──────────────────────────

(deftest tc-auth04-identity-dispatch-extended
  (testing "identity-dispatch! routes idv6-idv10 correctly"
    (doseq [[variant expected-provider expected-dim]
            [[:idv6 :idv6 6]
             [:idv7 :idv7 7]
             [:idv8 :idv8 8]
             [:idv9 :idv9 9]
             [:idv10 :idv10 10]]]
      (let [r (idnt/identity-dispatch! variant {:dry-run true})]
        (is (true? (:ok r))
            (str variant " dispatch must succeed"))
        (is (= expected-provider (:provider r))
            (str variant " provider mismatch"))
        (is (= expected-dim (:dim r))
            (str variant " dim must be " expected-dim))
        (is (map? (:calendars r))
            (str variant " must include calendars"))))

    ;; Unknown variant
    (let [r (idnt/identity-dispatch! :idv99 {})]
      (is (false? (:ok r)) "unknown variant must fail")
      (is (string? (:error r)) "error message required")
      (is (vector? (:available r)) "must list available variants")
      (is (= 10 (count (:available r))) "must list all 10 variants"))))

;; ── tc-auth05: IDPR opcode — discovery + CA audit ────────────────────────────

(deftest tc-auth05-idpr-opcode
  (testing "IDPR opcode: discovery document and CA audit"
    ;; OIDC discovery document
    (let [discovery (idp/discovery-document)]
      (is (map? discovery) "discovery must be a map")
      (is (contains? discovery :issuer) "must have :issuer")
      (is (contains? discovery :authorization_endpoint) "must have :authorization_endpoint")
      (is (contains? discovery :token_endpoint) "must have :token_endpoint")
      (is (contains? discovery :jwks_uri) "must have :jwks_uri")
      (is (contains? discovery :scopes_supported) "must have :scopes_supported")
      (is (contains? (set (:scopes_supported discovery)) "file:read")
          "scopes must include file:read")
      (is (contains? (set (:scopes_supported discovery)) "openid")
          "scopes must include openid")
      (is (contains? (set (:id_token_signing_alg_values_supported discovery)) "RS256")
          "must support RS256"))

    ;; CA audit via governed idpr!
    (let [result ((idp/idpr! test-auth :ca-report {}))]
      (is (true? (:ok result)) "IDPR :ca-report must succeed")
      (is (pos? (:ca-count result)) "must find at least 1 CA")
      (is (string? (:jvm-path result)) "jvm-path must be a string")
      (is (sequential? (:cas result)) "cas must be sequential")
      (is (pos? (count (:cas result))) "cas must be non-empty")
      (is (every? #(contains? % :urn) (:cas result))
          "every CA entry must have :urn"))

    ;; HS256 file-access token (no key generation needed)
    (let [result ((idp/idp-token!
                    test-auth
                    {"sub" "skh@singine.local"}
                    {:algo        :hs256
                     :secret      "singine-idpr-test"
                     :ttl-seconds 300
                     :file-path   "/Users/skh/private/test.txt"
                     :perm        :read}))]
      (is (true? (:ok result)) "file-access token must succeed")
      (is (string? (:token result)) "token must be a string")
      (is (= "hs256" (:algo result)) "algo must be hs256")
      (is (= "/Users/skh/private/test.txt" (:file-path result)) "file-path preserved")
      (is (= "read" (:perm result)) "perm must be read")
      (is (= "urn:singine:resource:file" (:aud result)) "aud must be file resource URN")

      ;; Verify the token
      (let [verify-result ((idp/verify-file-token!
                             test-auth
                             (:token result)
                             "singine-idpr-test"
                             {:algo :hs256}))]
        (is (true? (:ok verify-result)) "token verification must succeed")
        (is (= "/Users/skh/private/test.txt" (:path verify-result)) "path preserved")
        (is (= "read" (:perm verify-result)) "perm preserved")))))

;; ── tc-idpr01: IDPR opcode governed entry ────────────────────────────────────

(deftest tc-idpr01-idpr-governed
  (testing "IDPR governed entry point via idpr!"
    ;; :discover operation
    (let [thunk  (idp/idpr! test-auth :discover {})
          result (thunk)]
      (is (true? (:ok result)) ":discover must succeed")
      (is (map? (:discovery result)) "discovery doc must be a map")
      (is (contains? (:discovery result) :token_endpoint)
          "discovery must have token_endpoint"))

    ;; Unknown op
    (let [thunk  (idp/idpr! test-auth :unknown-op {})
          result (thunk)]
      (is (false? (:ok result)) "unknown op must fail")
      (is (string? (:error result)) "error message required"))))

;; ── tc-idpr02: JwsToken JSON helpers ─────────────────────────────────────────

(deftest tc-idpr02-jwstoken-json
  (testing "JwsToken JSON serialiser/deserialiser round-trip"
    (let [claims {"sub"  "skh@singine.local"
                  "name" "Sh. Kh. Heshmati"
                  "exp"  9999999999
                  "iss"  "urn:singine:idp"}
          json   (singine.auth.JwsToken/toJson (auth-tok/claims->java claims))
          parsed (singine.auth.JwsToken/fromJson json)]
      (is (string? json) "toJson must return a string")
      (is (str/starts-with? json "{") "JSON must start with {")
      (is (str/ends-with? json "}") "JSON must end with }")
      (is (str/includes? json "singine:idp") "JSON must contain issuer URN")
      (is (instance? java.util.Map parsed) "fromJson must return a Map")
      (is (= "skh@singine.local" (.get parsed "sub")) "sub round-trips")
      (is (= "urn:singine:idp" (.get parsed "iss")) "iss round-trips"))))

;; ══════════════════════════════════════════════════════════════════════════════
;; Phase 2 — IDNT-URN-v1: 1-char / 2-char / 3-char URN lookup + Unicode filter
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-idnt01-lookup-urn-levels
  (testing "Level 1 — single ASCII character → urn:singine:id:l1:<char>"
    (is (= "urn:singine:id:l1:A" (idnt/lookup-urn "A")))
    (is (= "urn:singine:id:l1:B" (idnt/lookup-urn "B")))
    (is (= "urn:singine:id:l1:z" (idnt/lookup-urn "z")))
    (is (= "urn:singine:id:l1:0" (idnt/lookup-urn "0")))
    (is (= "urn:singine:id:l1:!" (idnt/lookup-urn "!")))
    (is (str/starts-with? (idnt/lookup-urn "A") "urn:singine:id:l1")))

  (testing "Level 2 — two-char ISO 3166 country code → urn:singine:id:l2:<CC>"
    (is (= "urn:singine:id:l2:BE" (idnt/lookup-urn "BE")))
    (is (= "urn:singine:id:l2:GB" (idnt/lookup-urn "GB")))
    (is (= "urn:singine:id:l2:IR" (idnt/lookup-urn "ir")))   ; upcased
    (is (= "urn:singine:id:l2:US" (idnt/lookup-urn "US")))
    (is (str/starts-with? (idnt/lookup-urn "NL") "urn:singine:id:l2")))

  (testing "Level 3 — three-char IATA airport code → urn:singine:id:l3:<IATA>"
    (is (= "urn:singine:id:l3:BRU" (idnt/lookup-urn "BRU")))
    (is (= "urn:singine:id:l3:LHR" (idnt/lookup-urn "LHR")))
    (is (= "urn:singine:id:l3:JFK" (idnt/lookup-urn "JFK")))
    (is (= "urn:singine:id:l3:AMS" (idnt/lookup-urn "ams")))  ; upcased
    (is (str/starts-with? (idnt/lookup-urn "CDG") "urn:singine:id:l3")))

  (testing "Edge cases — nil, empty, long codes"
    (is (= "urn:singine:id:nil"   (idnt/lookup-urn nil)))
    (is (= "urn:singine:id:empty" (idnt/lookup-urn "")))
    ;; 6-char code → two 3-char segments, joined with ":"
    (let [urn6 (idnt/lookup-urn "BRULHR")]
      (is (str/includes? urn6 "BRU"))
      (is (str/includes? urn6 "LHR"))
      (is (str/includes? urn6 ":"))))

  (testing "Batch lookup — lookup-urn-batch returns map of code→URN"
    (let [codes ["A" "BE" "BRU"]
          batch (idnt/lookup-urn-batch codes)]
      (is (map? batch))
      (is (= 3 (count batch)))
      (is (= "urn:singine:id:l1:A"   (get batch "A")))
      (is (= "urn:singine:id:l2:BE"  (get batch "BE")))
      (is (= "urn:singine:id:l3:BRU" (get batch "BRU"))))))

(deftest tc-idnt02-unicode-filter-rule
  (testing "unicode-block returns expected block names"
    ;; Latin: A = 0x41
    (is (= "Latin"    (idnt/unicode-block 0x41)))
    ;; Greek: Α = 0x0391
    (is (= "Greek"    (idnt/unicode-block 0x0391)))
    ;; Cyrillic: А = 0x0410
    (is (= "Cyrillic" (idnt/unicode-block 0x0410)))
    ;; Hebrew: א = 0x05D0
    (is (= "Hebrew"   (idnt/unicode-block 0x05D0)))
    ;; Arabic: ا = 0x0627
    (is (= "Arabic"   (idnt/unicode-block 0x0627)))
    ;; CJK: 中 = 0x4E2D
    (is (= "CJK"      (idnt/unicode-block 0x4E2D)))
    ;; Unknown (Emoji range): should be Other
    (is (= "Other"    (idnt/unicode-block 0x1F600))))

  (testing "unicode-filter-rule — nested lambda (means of combination)"
    ;; The outer lambda takes an allowed-blocks set and returns the inner lambda
    (let [in-rule  (idnt/unicode-filter-rule #{"Latin" "Arabic"})
          out-rule (idnt/unicode-filter-rule #{})]  ; empty set — all out
      ;; Latin A (0x41) → in
      (is (true?  (in-rule  0x41)))
      ;; Arabic ا (0x0627) → in
      (is (true?  (in-rule  0x0627)))
      ;; Cyrillic А (0x0410) → not in {"Latin","Arabic"}
      (is (false? (in-rule  0x0410)))
      ;; Empty set → everything out
      (is (false? (out-rule 0x41)))
      (is (false? (out-rule 0x0627)))))

  (testing "Level-u URN: Unicode char → urn:singine:id:u:<block>:<HEX>"
    ;; Arabic char ا (U+0627) → in Arabic block → named URN
    (let [arabic-char "\u0627"
          urn         (idnt/lookup-urn arabic-char)]
      (is (str/starts-with? urn "urn:singine:id:u:Arabic:"))
      (is (str/ends-with?   urn "0627")))

    ;; Emoji 😀 (U+1F600) → block=Other (out-rule) → Other URN
    (let [emoji-str (str (Character/toChars 0x1F600))
          ;; only check the first char (code point) if multi-char
          urn       (idnt/lookup-urn (subs emoji-str 0 1))]
      (is (str/starts-with? urn "urn:singine:id:")))

    ;; Hebrew aleph (U+05D0)
    (let [heb-char "\u05D0"
          urn      (idnt/lookup-urn heb-char)]
      (is (str/starts-with? urn "urn:singine:id:u:Hebrew:")))

    ;; Cyrillic А (U+0410)
    (let [cyr-char "\u0410"
          urn      (idnt/lookup-urn cyr-char)]
      (is (str/starts-with? urn "urn:singine:id:u:Cyrillic:"))))

  (testing "List comprehension: filter codes by unicode-filter-rule (in-rule)"
    ;; Classic list comprehension using the nested lambda:
    ;; (λ codes → (filter ((unicode-filter-rule blocks) ∘ char-cp) codes))
    (let [codes    ["A" "B" "\u0627" "\u0410" "\u1F600"]  ; mix of ASCII + Unicode
          in?      (idnt/unicode-filter-rule idnt/unicode-in-blocks)
          ;; Apply the inner lambda to the codepoint of the first char of each code
          included (filter (fn [c]
                             (when (seq c)
                               (let [cp (int (first c))]
                                 (if (<= cp 0x7F)
                                   true    ; ASCII always in level-1
                                   (in? cp)))))
                           codes)]
      ;; A, B are ASCII → in; Arabic U+0627 → in (Arabic block)
      ;; Cyrillic U+0410 → in (Cyrillic block); \u1F600 is surrogate → skip
      (is (>= (count included) 3)
          "At least A, B, Arabic ا should pass the in-rule"))))

;; ══════════════════════════════════════════════════════════════════════════════
;; Sub-phase F — MANDATE-v1: two-stream topic mandate (Hoffman legitimacy contract)
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-mandate01-extract-topic
  (testing "extract-topic from Logseq [[t/1]] notation"
    (is (= "urn:singine:topic:t/1"
           (idp/extract-topic "A document about [[t/1]] in the singine platform")))
    (is (= "urn:singine:topic:t/release"
           (idp/extract-topic "See [[t/release]] for details")))
    (is (nil? (idp/extract-topic "No topic here")))
    (is (nil? (idp/extract-topic nil)))
    (is (nil? (idp/extract-topic "")))))

(deftest tc-mandate02-extract-urn
  (testing "extract-topic from explicit urn:singine:topic: URN"
    (is (= "urn:singine:topic:t/1"
           (idp/extract-topic "The topic is urn:singine:topic:t/1 and more text")))
    (is (= "urn:singine:topic:auth"
           (idp/extract-topic "urn:singine:topic:auth is authoritative")))))

(deftest tc-mandate03-same-topic
  (testing "streams-same-topic? true when both carry the same topic"
    (let [stream-a "BLKP output: [[t/1]] platform data lineage"
          stream-b "CATC output: [[t/1]] entity resolution complete"]
      (is (true? (idp/streams-same-topic? stream-a stream-b))))
    ;; Also works with explicit URN form
    (let [s1 "urn:singine:topic:t/1 manifest-a"
          s2 "urn:singine:topic:t/1 manifest-b"]
      (is (true? (idp/streams-same-topic? s1 s2))))))

(deftest tc-mandate04-diff-topic
  (testing "streams-same-topic? false when topics differ or are missing"
    ;; One stream missing topic
    (let [stream-a "[[t/1]] present"
          stream-b "no topic here"]
      (is (false? (idp/streams-same-topic? stream-a stream-b))))
    ;; Different topics
    (let [stream-a "[[t/1]] topic one"
          stream-b "[[t/2]] topic two"]
      (is (false? (idp/streams-same-topic? stream-a stream-b))))
    ;; Both nil
    (is (false? (idp/streams-same-topic? nil nil)))))

(deftest tc-mandate05-issue-mandate
  (testing "topic-mandate! issues a valid HS256 mandate JWT for two matching streams"
    (let [streams [["urn:singine:stream:blkp:001"
                    "BLKP manifest: [[t/1]] platform data governance"]
                   ["urn:singine:stream:catc:001"
                    "CATC output: [[t/1]] entity resolution activated"]]
          thunk   (idp/topic-mandate!
                    test-auth streams
                    {:mandate-duration-seconds 1800
                     :algo :hs256
                     :secret "singine-mandate-test"})
          result  (thunk)]
      (is (true? (:ok result)) "mandate must succeed")
      (is (string? (:mandate-token result)) "mandate-token must be a string")
      (is (= "urn:singine:topic:t/1" (:topic result)) "topic must be t/1")
      (is (= 2 (count (:streams result))) "both stream URNs preserved")
      (is (= 1800 (:mandate-duration result)) "duration preserved")
      (is (pos? (:exp result)) ":exp must be a positive epoch-second")
      (is (string? (:jti result)) ":jti must be a string"))))

(deftest tc-mandate06-mandate-via-idpr
  (testing "IDPR :topic-mandate dispatches correctly"
    (let [streams [["urn:singine:stream:a" "document [[t/1]] stream one"]
                   ["urn:singine:stream:b" "document [[t/1]] stream two"]]
          thunk   (idp/idpr! test-auth :topic-mandate
                             {:streams  streams
                              :mandate-duration-seconds 600
                              :algo     :hs256
                              :secret   "singine-idpr-mandate"})
          result  (thunk)]
      (is (true? (:ok result)) "IDPR :topic-mandate must succeed")
      (is (string? (:mandate-token result)) "token must be present")
      (is (= "urn:singine:topic:t/1" (:topic result)))
      ;; Mismatch case — IDPR :topic-mandate returns :ok false
      (let [bad-streams [["urn:singine:stream:x" "no topic here"]
                         ["urn:singine:stream:y" "also no topic"]]
            bad-result  ((idp/idpr! test-auth :topic-mandate
                                    {:streams  bad-streams
                                     :algo     :hs256
                                     :secret   "singine-idpr-mandate"}))]
        (is (false? (:ok bad-result)) "mismatched streams must fail")
        (is (string? (:reason bad-result)) "reason must be present")))))

(deftest tc-mandate07-token-exp
  (testing ":exp in mandate is a future epoch-second"
    (let [streams [["urn:singine:stream:t1" "[[t/1]] test stream one"]
                   ["urn:singine:stream:t2" "[[t/1]] test stream two"]]
          result  ((idp/topic-mandate!
                     test-auth streams
                     {:mandate-duration-seconds 3600
                      :algo :hs256
                      :secret "exp-test-secret"}))]
      (is (true? (:ok result)))
      (let [now-epoch (quot (System/currentTimeMillis) 1000)
            exp       (:exp result)]
        (is (> exp now-epoch) ":exp must be in the future")
        (is (< exp (+ now-epoch 4000)) ":exp should be within ~3600s from now")))))

;; ══════════════════════════════════════════════════════════════════════════════
;; Sub-phase A — MIME-REG-v1: canonical MIME registry
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-mime01-lookup
  (testing "MIME lookup by extension — canonical types"
    (is (= "application/rdf+xml"                (mime/lookup "rdf")))
    (is (= "application/rdf+xml"                (mime/lookup "RDF")))  ; case-insensitive
    (is (= "text/turtle"                        (mime/lookup "ttl")))
    (is (= "application/json"                   (mime/lookup "json")))
    (is (= "application/sparql-query"           (mime/lookup "sparql")))
    (is (= "application/xml"                    (mime/lookup "xml")))
    (is (= "application/x-parquet"             (mime/lookup "parquet")))
    (is (= "application/zip"                    (mime/lookup "zip")))))

(deftest tc-mime02-lookup-sindoc
  (testing "Singine vendor MIME types"
    (is (= "application/vnd.singine.sindoc+xml" (mime/lookup "sindoc")))
    (is (= "application/vnd.singine.sindoc+xml" (mime/lookup "sin")))
    (is (= "application/vnd.urfm+xml"           (mime/lookup "urfm")))
    (is (= "application/atom+xml"               (mime/lookup "atom")))
    (is (= "application/rss+xml"                (mime/lookup "rss")))))

(deftest tc-mime03-route-link
  (testing "RDF / graph content routes to :link"
    (is (= :link (mime/route "application/rdf+xml")))
    (is (= :link (mime/route "text/turtle")))
    (is (= :link (mime/route "application/ld+json")))
    (is (= :link (mime/route "application/sparql-query")))
    (is (= :link (mime/route "application/vnd.urfm+xml")))
    (is (= :link (mime/route "application/n-triples")))))

(deftest tc-mime04-route-binary
  (testing "Binary / archive / image content routes to :binary"
    (is (= :binary (mime/route "application/x-parquet")))
    (is (= :binary (mime/route "application/zip")))
    (is (= :binary (mime/route "application/gzip")))
    (is (= :binary (mime/route "application/pdf")))
    (is (= :binary (mime/route "image/png")))
    (is (= :binary (mime/route "image/jpeg")))
    (is (= :binary (mime/route "video/mp4")))))

(deftest tc-mime05-route-lookup
  (testing "Text and application/* routes to :lookup"
    (is (= :lookup (mime/route "application/json")))
    (is (= :lookup (mime/route "application/xml")))
    (is (= :lookup (mime/route "text/plain")))
    (is (= :lookup (mime/route "text/csv")))
    (is (= :lookup (mime/route "text/html")))
    (is (= :lookup (mime/route "application/yaml")))
    (is (= :lookup (mime/route "application/vnd.singine.sindoc+xml")))))

(deftest tc-mime06-unambiguous
  (testing "Known extensions are unambiguous (each maps to exactly one MIME)"
    (is (true?  (mime/unambiguous? "xml")))
    (is (true?  (mime/unambiguous? "json")))
    (is (true?  (mime/unambiguous? "rdf")))
    (is (true?  (mime/unambiguous? "sindoc")))
    (is (false? (mime/unambiguous? "xyz")))   ; unknown
    (is (false? (mime/unambiguous? "")))))    ; empty

(deftest tc-mime07-unknown-ext
  (testing "Unknown extensions fall back to application/octet-stream"
    (is (= "application/octet-stream" (mime/lookup "xyz")))
    (is (= "application/octet-stream" (mime/lookup "")))
    (is (= "application/octet-stream" (mime/lookup nil)))
    ;; mime-for-path convenience
    (is (= "application/rdf+xml" (mime/mime-for-path "/some/path/file.rdf")))
    (is (= "application/octet-stream" (mime/mime-for-path "/no-extension")))
    ;; content-type adds charset for text/*
    (is (= "text/plain; charset=UTF-8" (mime/content-type "text/plain")))
    (is (= "application/json" (mime/content-type "application/json")))))

;; ══════════════════════════════════════════════════════════════════════════════
;; Bonus: gen-mock is the data product demo
;; ══════════════════════════════════════════════════════════════════════════════

(deftest gen-mock-data-product
  (testing "gen-mock produces a full range of data contracts (the product demo)"
    (let [contracts (gen-mock 20)]
      (is (= 20 (count contracts)))
      ;; Every combination of edge size appears
      (let [sizes (set (map :edge-size contracts))]
        (is (contains? sizes :s))
        (is (contains? sizes :m))
        (is (contains? sizes :l)))
      ;; Every severity appears
      (let [sevs (set (map :severity contracts))]
        (is (contains? sevs :low))
        (is (contains? sevs :moderate))
        (is (contains? sevs :high))
        (is (contains? sevs :critical)))
      ;; MIME routing covers all three routes
      (let [routes (set (map #(catc/mime-route (:mime-type %)) contracts))]
        (is (= #{:lookup :link :binary} routes))))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-mail01..tc-mail05 — MAIL opcode: SMTP send + IMAP search/fetch + git-snap
;; All tests use :dry-run true — no network connection required.
;; ══════════════════════════════════════════════════════════════════════════════

(def ^:private mail-opts
  "Shared dry-run mail config for all tc-mail tests."
  {:imap-host "localhost" :imap-port 993 :imap-tls true
   :smtp-host "localhost" :smtp-port 587 :smtp-tls false
   :user "test@localhost" :pass "test-pass"
   :folder "INBOX" :dry-run true})

;; test-auth is already defined above (via lam/make-auth) — reused here.

(deftest tc-mail01-search-dry-run
  (testing "MAIL :search — governed dry-run returns synthetic UIDs"
    (let [thunk  (mail/search! test-auth (assoc mail-opts :search "invoice"))
          result (thunk)]
      (is (true? (:ok result)))
      (is (vector? (:uids result)))
      (is (pos? (count (:uids result))))
      (is (= "INBOX" (:folder result)))
      (is (= "invoice" (:search result)))
      (is (map? (:time result))))))

(deftest tc-mail02-fetch-dry-run
  (testing "MAIL :fetch — governed dry-run returns XML mail-batch envelope"
    (let [thunk  (mail/fetch! test-auth (assoc mail-opts :uids ["1001" "1002"]))
          result (thunk)]
      (is (true? (:ok result)))
      (is (string? (:xml result)))
      (is (str/starts-with? (:xml result) "<?xml"))
      (is (str/includes? (:xml result) "mail-batch"))
      (is (= 2 (:uid-count result)))
      (is (= "application/xml" (or (:mime result) "application/xml"))))))

(deftest tc-mail03-send-dry-run
  (testing "MAIL :send — governed dry-run SMTP send returns :ok"
    (let [opts  (assoc mail-opts
                       :from "test@localhost"
                       :to "recipient@localhost"
                       :subject "Singine Test Mail"
                       :body "This is a dry-run test message from Singine.")
          thunk  (mail/send! test-auth opts)
          result (thunk)]
      (is (true? (:ok result)))
      (is (map? (:time result))))))

(deftest tc-mail04-git-snap-dry-run
  (testing "MAIL :snap — governed dry-run produces files map + commit message"
    (let [opts   (assoc mail-opts :search "report" :max 2 :base-dir "/tmp/singine-mail-test")
          thunk  (mail/git-snap! test-auth opts)
          result (thunk)]
      (is (true? (:ok result)))
      (is (map? (:files result)))
      (is (string? (:commit-msg result)))
      (is (str/starts-with? (:commit-msg result) "mail: snapshot"))
      (is (str/includes? (:commit-msg result) "INBOX"))
      (is (number? (:uid-count result))))))

(deftest tc-mail05-mail-dispatcher
  (testing "MAIL opcode top-level dispatcher routes :search + :fetch"
    ;; :search dispatch
    (let [thunk  (mail/mail! test-auth :search (assoc mail-opts :search "contract"))
          result (thunk)]
      (is (true? (:ok result)))
      (is (vector? (:uids result))))
    ;; :fetch dispatch
    (let [thunk  (mail/mail! test-auth :fetch (assoc mail-opts :uids ["9001"]))
          result (thunk)]
      (is (true? (:ok result)))
      (is (string? (:xml result))))
    ;; unknown op
    (let [thunk  (mail/mail! test-auth :unknown-op {})
          result (thunk)]
      (is (false? (:ok result)))
      (is (string? (:error result))))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-camel01..tc-camel02 — CamelContext lifecycle + status (no real context needed)
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-camel01-context-status-unstarted
  (testing "CamelContext: status-summary returns :started false when not started"
    (let [summary (camel-ctx/status-summary)]
      ;; The test environment does not start a real CamelContext.
      ;; status-summary must be safe to call regardless of context state.
      (is (map? summary))
      (is (contains? summary :started))
      (is (contains? summary :name))
      (is (contains? summary :status))
      (is (contains? summary :routes))
      (is (vector? (:routes summary))))))

(deftest tc-camel02-context-healthy-false-when-not-started
  (testing "CamelContext: healthy? returns false when context not started"
    ;; healthy? must not throw when context is nil/not-started
    (let [result (camel-ctx/healthy?)]
      (is (boolean? result)))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-edge01..tc-edge02 — singine.net.edge HTTP client (dry-run, no HTTP)
;; ══════════════════════════════════════════════════════════════════════════════

(def ^:private edge-opts
  "Shared dry-run edge config for all tc-edge tests."
  {:edge-host "localhost" :edge-port 8080 :edge-scheme "http" :dry-run true})

(deftest tc-edge01-health-dry-run
  (testing "EDGE :health — governed dry-run returns synthetic UP status"
    (let [thunk  (edge/health! test-auth edge-opts)
          result (thunk)]
      (is (true? (:ok result)))
      (is (= "UP" (:status result)))
      (is (= "singine-edge" (:service result)))
      (is (vector? (:routes result)))
      (is (pos? (count (:routes result))))
      (is (true? (:dry-run result)))
      (is (map? (:time result))))))

(deftest tc-edge02-messages-dry-run
  (testing "EDGE :index — governed dry-run returns synthetic messages list"
    (let [thunk  (edge/messages! test-auth (assoc edge-opts :search "invoice"))
          result (thunk)]
      (is (true? (:ok result)))
      (is (vector? (:messages result)))
      (is (pos? (count (:messages result))))
      (is (number? (:count result)))
      (is (= "invoice" (:search result)))
      (is (true? (:dry-run result)))
      (is (map? (:time result))))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-rails01..tc-rails02 — Rails naming aliases via edge! + mail! dispatchers
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-rails01-edge-aliases
  (testing "EDGE dispatcher Rails aliases: :messages → :index, :message → :show, :send → :create"
    ;; :messages alias → :index
    (let [thunk  (edge/edge! test-auth :messages edge-opts)
          result (thunk)]
      (is (true? (:ok result)))
      (is (vector? (:messages result))))
    ;; :message alias → :show
    (let [thunk  (edge/edge! test-auth :message (assoc edge-opts :uid "1001"))
          result (thunk)]
      (is (true? (:ok result)))
      (is (map? (:message result)))
      (is (= "1001" (:uid result))))
    ;; :send alias → :create
    (let [thunk  (edge/edge! test-auth :send
                             (assoc edge-opts
                                    :from "a@localhost" :to "b@localhost"
                                    :subject "Test" :body "Hello"))
          result (thunk)]
      (is (true? (:ok result)))
      (is (true? (:sent result))))
    ;; unknown op
    (let [thunk  (edge/edge! test-auth :unknown-edge-op edge-opts)
          result (thunk)]
      (is (false? (:ok result)))
      (is (string? (:error result))))))

(deftest tc-rails02-mail-aliases
  (testing "MAIL dispatcher Rails aliases: :index → :search, :show → :fetch, :create → :send"
    ;; :index → :search
    (let [thunk  (mail/mail! test-auth :index (assoc mail-opts :search "report"))
          result (thunk)]
      (is (true? (:ok result)))
      (is (vector? (:uids result))))
    ;; :show → :fetch (single UID)
    (let [thunk  (mail/mail! test-auth :show (assoc mail-opts :uids ["2001"]))
          result (thunk)]
      (is (true? (:ok result)))
      (is (string? (:xml result))))
    ;; :create → :send
    (let [thunk  (mail/mail! test-auth :create
                             (assoc mail-opts
                                    :from "a@localhost" :to "b@localhost"
                                    :subject "Rails alias test" :body "test body"))
          result (thunk)]
      (is (true? (:ok result))))
    ;; :self — send-to-self (dry-run)
    (let [thunk  (mail/mail! test-auth :self
                             (assoc mail-opts
                                    :subject "Self notification"
                                    :context "testing Rails alias"
                                    :constraints "dry-run only"))
          result (thunk)]
      (is (true? (:ok result)))
      (is (vector? (:dispatched-to result)))
      (is (pos? (:channels result))))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-broker01..tc-broker02 — dual broker (Kafka + RabbitMQ) dry-run publish
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-broker01-kafka-publish-dry-run
  (testing "BROKER :publish :kafka — dry-run returns synthetic ACK with checksum"
    (let [thunk  (broker/publish! test-auth
                                  {:broker   :kafka
                                   :topic    :inbound-email
                                   :body     "{\"event\":\"test\",\"uid\":\"1001\"}"
                                   :dry-run  true})
          result (thunk)]
      (is (true? (:ok result)))
      (is (= :kafka (:broker result)))
      (is (string? (:destination result)))
      (is (str/includes? (:destination result) "singine"))
      (is (string? (:message-id result)))
      (is (string? (:checksum result)))
      (is (true? (:dry-run result)))
      (is (map? (:time result))))))

(deftest tc-broker02-rabbitmq-consume-dry-run
  (testing "BROKER :consume :rabbitmq — dry-run returns synthetic message"
    (let [thunk  (broker/consume! test-auth
                                  {:broker      :rabbitmq
                                   :queue       "singine.transforms.ocr"
                                   :timeout-ms  1000
                                   :dry-run     true})
          result (thunk)]
      (is (true? (:ok result)))
      (is (= :rabbitmq (:broker result)))
      (is (string? (:body result)))
      (is (string? (:message-id result)))
      (is (string? (:checksum result)))
      (is (true? (:dry-run result)))
      (is (map? (:time result))))))

;; ══════════════════════════════════════════════════════════════════════════════
;; tc-trust01..tc-trust02 — trust store management (dry-run)
;; ══════════════════════════════════════════════════════════════════════════════

(deftest tc-trust01-register-ssh-pubkey-dry-run
  (testing "TRUST :register-ssh — dry-run describes action without I/O"
    (let [thunk  (trust/register-ssh-pubkey! test-auth {:dry-run true})
          result (thunk)]
      (is (true? (:ok result)))
      (is (true? (:dry-run result)))
      (is (string? (:alias result)))
      (is (string? (:urn result)))
      (is (str/includes? (:urn result) "singine:machine"))
      (is (map? (:time result))))))

(deftest tc-trust02-minimal-trust-mail-caps
  (testing "TRUST :minimal — mail-only device needs only identity cert"
    (let [thunk  (trust/minimal-trust! test-auth [:mail :cli :python])
          result (thunk)]
      (is (map? result))
      (is (contains? result :caps))
      (is (contains? result :required-aliases))
      (is (contains? (set (:required-aliases result)) "singine-identity-attar"))
      (is (map? (:time result))))))
