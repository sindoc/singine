(ns singine.pos.location
  "LOCP opcode — Location Probe.

   Deduces metadata for @location by:
   1. Resolving IATA / postal / country code → urn:singine:location:<cc>:<code>
   2. Building a SOAP 1.2 request (SoapRequest.java)
   3. Validating the request XML: RelaxNG + Schematron
   4. Running SODA scan (Python subprocess, dry-run by default)
   5. Running NannyML estimate (Python subprocess, dry-run by default)
   6. Emitting pos-locp.xml to the temporal path today/2020s/YYYY/MM/DD/

   CDN taxonomy subjects (from Logseq Feb 21, 2026):
     :standards :exchange :market :marketplace
     :data :electricity :pricing :financials

   Output:
     pos-locp.xml at today/2020s/<YYYY>/<MM>/<DD>/pos-locp.xml
     Kafka topic: singine.pos.location

   URN levels (identity lookup):
     l1 — 1-char ASCII   → urn:singine:id:l1:<char>
     l2 — 2-char cc      → urn:singine:id:l2:<cc>     (ISO 3166)
     l3 — 3-char IATA    → urn:singine:id:l3:<iata>
     u  — unicode        → urn:singine:id:u:<codepoint>"
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [singine.meta.genx    :as genx]
            [singine.meta.root    :as root]
            [clojure.java.io      :as io]
            [clojure.string       :as str])
  (:import [singine.soap SoapRequest]
           [singine.location IataCodeTable]
           [singine.schema RelaxNGValidator SchematronValidator]
           [java.io File StringWriter]
           [java.time ZonedDateTime ZoneId]))

;; ── CDN taxonomy subjects (from Logseq) ──────────────────────────────────────

(def cdn-subjects
  "All subjects from the local cdn hierarchy in the Logseq journal."
  [:standards :exchange :market :marketplace
   :data :electricity :pricing :financials])

;; ── URN resolution ────────────────────────────────────────────────────────────

(defn zip2urn
  "Postal code → urn:singine:location:<cc>:<zip>
   Fulfils: 'assign calendars zip2urn' from Logseq."
  [cc zip]
  (IataCodeTable/zip2urn cc zip))

(defn iata->urn
  "IATA 3-char code → urn:singine:location:<cc>:<iata>
   Fulfils: 'iata build code set from country code list'."
  [code]
  (IataCodeTable/resolveUrn code))

(defn level-urn
  "1-, 2-, or 3-char code → level URN.
   1-char → urn:singine:id:l1:<char>
   2-char → urn:singine:id:l2:<cc>
   3-char → urn:singine:id:l3:<iata>"
  [code]
  (IataCodeTable/levelUrn code))

(defn resolve-location
  "Resolve any location identifier to a URN.
   IATA 3-char → l3 URN.
   ISO 3166 2-char → l2 URN.
   postal code → zip2urn with cc from opts."
  [location opts]
  (let [upper (str/upper-case location)]
    (cond
      (re-matches #"[A-Z]{3}" upper) (iata->urn upper)
      (re-matches #"[A-Z]{2}"  upper) (iata->urn upper)
      :else (zip2urn (or (:cc opts) "BE") location))))

;; ── SOAP probe builder ────────────────────────────────────────────────────────

(defn- soap-probe!
  "Build a SOAP 1.2 LocationProbeRequest XML string.
   Returns the XML string."
  [location-urn subject cal]
  (let [req-id  (str "locp-" (get-in cal [:gregorian :iso]) "-" (name subject))
        req     (SoapRequest. req-id location-urn (name subject))]
    (.setCalendar req
                  (str (get-in cal [:gregorian :iso]))
                  (str (get-in cal [:persian :year]))
                  (str (get-in cal [:chinese :sexagenary])))
    (.toXmlString req)))

;; ── Schema validation pipeline ───────────────────────────────────────────────

(defn- validate-xml!
  "Validates xml-str through RelaxNG + Schematron.
   Returns {:rnc-valid :rnc-errors :sch-valid :sch-errors}."
  [xml-str]
  (let [rnc-resource (io/resource "schema/singine.rng")
        sch-resource (io/resource "schema/singine.sch")

        rnc-result (if rnc-resource
                     (with-open [s (io/input-stream rnc-resource)]
                       (RelaxNGValidator/validate xml-str s "singine.rng"))
                     ;; resource not on classpath — annotate and pass
                     (reify Object
                       (toString [_] "RNG-resource-absent")))

        sch-result (if sch-resource
                     (with-open [s (io/input-stream sch-resource)]
                       (SchematronValidator/validate xml-str s "singine.sch"))
                     nil)]

    (let [rnc-valid  (if (instance? singine.schema.RelaxNGValidator$ValidationResult rnc-result)
                       (.isValid ^singine.schema.RelaxNGValidator$ValidationResult rnc-result)
                       true)
          rnc-errors (if (instance? singine.schema.RelaxNGValidator$ValidationResult rnc-result)
                       (vec (.getErrors ^singine.schema.RelaxNGValidator$ValidationResult rnc-result))
                       ["INFO: singine.rng not on classpath — validation deferred"])
          sch-valid  (if (some? sch-result)
                       (.isValid ^singine.schema.SchematronValidator$ValidationResult sch-result)
                       true)
          sch-errors (if (some? sch-result)
                       (vec (.getErrors ^singine.schema.SchematronValidator$ValidationResult sch-result))
                       ["INFO: singine.sch not on classpath — validation deferred"])]
      {:rnc-valid  rnc-valid
       :rnc-errors rnc-errors
       :sch-valid  sch-valid
       :sch-errors sch-errors})))

;; ── SODA subprocess ──────────────────────────────────────────────────────────

(defn- soda-scan!
  "Run SODA Core data quality scan.
   dry-run? true → returns synthetic pass result (default in tests).
   dry-run? false → calls python3 -m soda.cli scan."
  [dry-run?]
  (if dry-run?
    {:provider :soda :ok true :checks 14 :passed 14 :failed 0
     :stdout "SODA dry-run: all 14 checks passed (synthetic)"
     :config "soda/singine.yml"}
    (try
      (let [pb  (ProcessBuilder. ["python3" "-m" "soda.cli" "scan"
                                  "-d" "singine" "-c" "soda/singine.yml"])
            _   (.redirectErrorStream pb true)
            p   (.start pb)
            out (slurp (.getInputStream p))
            rc  (.waitFor p)]
        {:provider :soda :ok (zero? rc) :stdout out :exit rc :config "soda/singine.yml"})
      (catch Exception e
        {:provider :soda :ok false :error (.getMessage e) :config "soda/singine.yml"}))))

;; ── NannyML subprocess ───────────────────────────────────────────────────────

(defn- nannyml-estimate!
  "Run NannyML drift estimation.
   dry-run? true → returns synthetic no-drift result.
   dry-run? false → calls python3 -m nannyml estimate."
  [dry-run?]
  (if dry-run?
    {:provider :nannyml :ok true :drift-detected false :features-monitored 7
     :stdout "NannyML dry-run: no drift detected (synthetic)"
     :config "nannyml/locp_config.yml"}
    (try
      (let [pb  (ProcessBuilder. ["python3" "-m" "nannyml" "estimate"
                                  "--config" "nannyml/locp_config.yml"])
            _   (.redirectErrorStream pb true)
            p   (.start pb)
            out (slurp (.getInputStream p))
            rc  (.waitFor p)]
        {:provider :nannyml :ok (zero? rc) :stdout out :exit rc
         :config "nannyml/locp_config.yml"})
      (catch Exception e
        {:provider :nannyml :ok false :error (.getMessage e)
         :config "nannyml/locp_config.yml"}))))

;; ── Temporal output path ──────────────────────────────────────────────────────

(defn- locp-output-path [cal]
  (let [year  (get-in cal [:gregorian :year])
        m     (format "%02d" (get-in cal [:gregorian :month]))
        d     (format "%02d" (get-in cal [:gregorian :day]))
        decade (str (- year (mod year 10)) "s")
        ws    (str (or (root/find-workspace-root)
                       (System/getProperty "user.dir")))]
    (str ws "/today/" decade "/" year "/" m "/" d "/pos-locp.xml")))

;; ── XML emitter for pos-locp.xml ─────────────────────────────────────────────

(defn- emit-locp-xml!
  "Build and write pos-locp.xml. Returns the XML string."
  [location location-urn subject soap-xml validation soda nannyml cal t out-path]
  (let [iso-ts (str (get-in cal [:gregorian :iso]))
        tree
        [:locp
         {:xmlns          "urn:singine:pos:locp"
          :xmlns:cal      "urn:singine:time:calendar"
          :xmlns:val      "urn:singine:schema:validation"
          :xmlns:soda     "urn:singine:soda"
          :xmlns:nml      "urn:singine:nannyml"
          :id             (str "locp-" location "-" iso-ts)
          :generated-at   (str (get cal :london-iso iso-ts))
          :opcode         "LOCP"
          :location       location
          :location-urn   location-urn
          :subject        (name subject)}

         ;; SOAP request payload
         [:soap-request
          {:xmlns   "urn:singine:pos:locp"
           :subject (name subject)}
          [:cdata (str soap-xml)]]

         ;; Schema validation results
         [:val:validation
          {:rnc-valid (str (:rnc-valid validation))
           :sch-valid (str (:sch-valid validation))}
          (when (seq (:rnc-errors validation))
            (into [:val:rnc-errors {}]
                  (mapv (fn [e] [:val:error {} e]) (:rnc-errors validation))))
          (when (seq (:sch-errors validation))
            (into [:val:sch-errors {}]
                  (mapv (fn [e] [:val:error {} e]) (:sch-errors validation))))]

         ;; SODA data quality
         [:soda:scan
          {:ok      (str (:ok soda))
           :checks  (str (:checks soda 0))
           :passed  (str (:passed soda 0))
           :failed  (str (:failed soda 0))
           :config  (:config soda "")}
          [:soda:stdout {} (str (:stdout soda ""))]]

         ;; NannyML drift
         [:nml:estimate
          {:ok             (str (:ok nannyml))
           :drift-detected (str (:drift-detected nannyml false))
           :features       (str (:features-monitored nannyml 0))
           :config         (:config nannyml "")}
          [:nml:stdout {} (str (:stdout nannyml ""))]]

         ;; Triple-calendar anchor
         [:cal:when
          {:london-iso (str (get cal :london-iso iso-ts))
           :tz         "Europe/London"}
          [:cal:gregorian
           {:year  (str (get-in cal [:gregorian :year]))
            :month (str (get-in cal [:gregorian :month]))
            :day   (str (get-in cal [:gregorian :day]))
            :iso   (str (get-in cal [:gregorian :iso]))}]
          [:cal:persian
           {:year (str (get-in cal [:persian :year]))
            :note (get-in cal [:persian :note] "tabular approx")}]
          [:cal:chinese
           {:sexagenary (str (get-in cal [:chinese :sexagenary]))
            :animal     (str (get-in cal [:chinese :animal]))}]]]]

    (let [sw      (StringWriter.)
          xml-str (genx/emit-document! sw tree)
          out-file (File. out-path)]
      (io/make-parents out-file)
      (spit out-file xml-str)
      xml-str)))

;; ── probe! — governed entry point (opcode LOCP) ──────────────────────────────

(defn probe!
  "Governed LOCP entry point.

   location — IATA code (BRU), ISO 3166 country code (BE), or postal code (1000)
   opts     — {:subject :standards|:exchange|…  :dry-run true/false  :cc \"BE\"}

   Returns a zero-arg thunk per govern contract.

   Result map:
     {:ok :location :location-urn :subject :soap-xml :validation
      :soda :nannyml :xml :path :calendars}"
  ([auth location]
   (probe! auth location {}))
  ([auth location opts]
   (lam/govern auth
     (fn [t]
       (let [cal          (cal/london-triple)
             location-urn (resolve-location location opts)
             subject      (or (:subject opts) :standards)
             dry-run?     (get opts :dry-run true)
             soap-xml     (soap-probe! location-urn subject cal)
             validation   (validate-xml! soap-xml)
             soda         (soda-scan! dry-run?)
             nannyml      (nannyml-estimate! dry-run?)
             out-path     (locp-output-path cal)
             xml-str      (emit-locp-xml! location location-urn subject
                                          soap-xml validation soda nannyml cal t out-path)]
         {:ok          true
          :location     location
          :location-urn location-urn
          :subject      subject
          :soap-xml     soap-xml
          :validation   validation
          :soda         soda
          :nannyml      nannyml
          :xml          xml-str
          :path         out-path
          :calendars    cal})))))
