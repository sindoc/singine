(ns singine.pos.tc-suite-test
  "POS test suite — tc01…tc20 + tc-id01…tc-id05 + tc-form01.

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
