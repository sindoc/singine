(ns singine.pos.form
  "Form emitter (FORM opcode) — governed form via policy p + template t.

   A singine:pos form wraps a contact record (from template t) inside
   two meta-elements:

     <p:policy>   — the active terms of reference (from the condition system)
     <t:template> — back-reference to the source template (pos-contact.xml)

   The form is governed: every emission is wrapped in (cons auth λ(t)).
   Time context: london-triple (Gregorian + Persian + Chinese + London ISO 8601).

   Output path (temporal hierarchy):
     today/2020s/<YYYY>/<MM>/<DD>/pos-form.xml

   Namespaces in the form:
     xmlns       = urn:singine:pos:form
     xmlns:p     = urn:singine:pos:policy
     xmlns:t     = urn:singine:pos:template
     xmlns:g     = urn:singine:governed
     xmlns:cal   = urn:singine:time:calendar

   Contact data (from Telegram screenshot 2026-02-21):
     Sina Heshmati / SinDoc
     @surenkierkegaard
     +32 476 55 14 38 (BE, Europe/Brussels)"
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [singine.meta.genx    :as genx]
            [singine.meta.root    :as root]
            [clojure.java.io      :as io]
            [clojure.string       :as str])
  (:import [java.io StringWriter File]
           [java.time ZonedDateTime ZoneId]
           [java.time.format DateTimeFormatter]
           [java.nio.file Paths]))

;; ── Default policy map ────────────────────────────────────────────────────────

(def default-policy
  "Standard 5-term policy for the @surenkierkegaard form.
   Covers: lineage (tor01), mime (tor02), signed (tor05), auth (tor06), calendar (tor07)."
  {:id           "p-surenkierkegaard"
   :predicate    "is-signed"
   :contract-ref "urn:singine:pos:form:surenkierkegaard"
   :agent        "@surenkierkegaard"
   :activity     "write"
   :terms-active 5
   :terms
   [{:id "tor01" :name "data-lineage-verified"      :satisfied true}
    {:id "tor02" :name "mime-type-registered"        :satisfied true}
    {:id "tor05" :name "contract-signed"             :satisfied true :at "@surenkierkegaard"}
    {:id "tor06" :name "auth-token-valid"            :satisfied true}
    {:id "tor07" :name "calendar-timestamp-present"  :satisfied true}]})

;; ── Default contact data (from screenshot) ───────────────────────────────────

(def default-contact
  {:canonical   "Sina Heshmati"
   :alias       "SinDoc"
   :username    "@surenkierkegaard"
   :platform    "telegram"
   :phone       "+32 476 55 14 38"
   :cc          "BE"
   :tz          "Europe/Brussels"
   :module      "sindoc"
   :status      "online"
   :captured    "2026-02-21"})

;; ── Default template reference ────────────────────────────────────────────────

(def default-template-src
  "today/2020s/2026/02/21/pos-contact.xml")

;; ── Temporal output path ──────────────────────────────────────────────────────

(defn- form-output-path
  "Return the temporal output path for pos-form.xml.
   Pattern: <ws-root>/today/2020s/<YYYY>/<MM>/<DD>/pos-form.xml"
  []
  (let [zdt    (ZonedDateTime/now (ZoneId/of "Europe/London"))
        year   (.getYear zdt)
        m      (format "%02d" (.getMonthValue zdt))
        d      (format "%02d" (.getDayOfMonth zdt))
        decade (str (- year (mod year 10)) "s")
        ws     (str (or (root/find-workspace-root) (System/getProperty "user.dir")))]
    (str ws "/today/" decade "/" year "/" m "/" d "/pos-form.xml")))

;; ── Hiccup tree builder ───────────────────────────────────────────────────────

(defn- term-el
  "Build a <p:term> hiccup element."
  [{:keys [id name satisfied at]}]
  (let [attrs (cond-> {:id id :name name :satisfied (str satisfied)}
                (some? at) (assoc :at at))]
    [:p:term attrs]))

(defn- build-form-tree
  "Build the hiccup tree for pos-form.xml.

   policy-map : map with :id :predicate :contract-ref :agent :activity :terms-active :terms
   template-src: path string for <t:template src=...>
   contact    : map with :canonical :alias :username :phone :cc :tz :module :status
   cal        : london-triple map
   iso-ts     : ISO 8601 string for generated-at"
  [policy-map template-src contact cal iso-ts]
  (let [terms (or (:terms policy-map) (:terms default-policy))]
    [:form
     {:xmlns        "urn:singine:pos:form"
      :xmlns:p      "urn:singine:pos:policy"
      :xmlns:t      "urn:singine:pos:template"
      :xmlns:g      "urn:singine:governed"
      :xmlns:cal    "urn:singine:time:calendar"
      :id           (str "form-" (str/replace (or (:agent policy-map) "@surenkierkegaard") #"@" "") "-"
                         (get-in cal [:gregorian :iso] "2026-02-21"))
      :generated-at iso-ts
      :agent        (or (:agent policy-map) "@surenkierkegaard")
      :opcode       "FORM"}

     ;; ── template reference (t) ────────────────────────────────────────────
     [:t:template
      {:src       (or template-src default-template-src)
       :version   "0.1"
       :schema    "urn:singine:pos:contact"
       :generator "singine.meta.genx/emit-document!"}]

     ;; ── policy (p) ───────────────────────────────────────────────────────
     (into
       [:p:policy
        {:id           (or (:id policy-map) (:id default-policy))
         :predicate    (or (:predicate policy-map) "is-signed")
         :contract-ref (or (:contract-ref policy-map) (:contract-ref default-policy))
         :agent        (or (:agent policy-map) "@surenkierkegaard")
         :activity     (or (:activity policy-map) "write")
         :terms-active (str (or (:terms-active policy-map) 5))}]
       (mapv term-el terms))

     ;; ── contact payload (from template) ─────────────────────────────────
     [:contact {}
      [:name     {:canonical (or (:canonical contact) "Sina Heshmati")
                  :alias     (or (:alias contact) "SinDoc")}]
      [:username {:platform  (or (:platform contact) "telegram")}
       (or (:username contact) "@surenkierkegaard")]
      [:phone    {:cc (or (:cc contact) "BE")
                  :tz (or (:tz contact) "Europe/Brussels")}
       (or (:phone contact) "+32 476 55 14 38")]
      [:module   {} (or (:module contact) "sindoc")]
      [:status   {} (or (:status contact) "online")]]

     ;; ── governed lambda: (cons auth (λ(t) (form p t (london-triple)))) ──
     [:g:lambda {:args "f e f d g" :governed "true"}
      [:g:auth {}
       [:g:agent    {:ref (or (:agent policy-map) "@surenkierkegaard")}]
       [:g:activity {:type "write" :proto "form-submission"}]
       [:g:token    {:eval "runtime"}]]
      [:g:body {}
       [:cdata "(cons auth (λ(t) (form p t (london-triple))))"]]]

     ;; ── temporal context: triple-calendar, London anchor ─────────────────
     [:cal:when
      {:london-iso (or (:london-iso cal) iso-ts)
       :tz         "Europe/London"}
      [:cal:gregorian
       {:year  (str (get-in cal [:gregorian :year]))
        :month (str (get-in cal [:gregorian :month]))
        :day   (str (get-in cal [:gregorian :day]))
        :iso   (str (get-in cal [:gregorian :iso]))}]
      [:cal:persian
       {:year  (str (get-in cal [:persian :year]))
        :note  (get-in cal [:persian :note] "tabular approximation")}]
      [:cal:chinese
       {:sexagenary (str (get-in cal [:chinese :sexagenary]))
        :animal     (str (get-in cal [:chinese :animal]))}]]]))

;; ── emit-form! — governed entry point (opcode FORM) ──────────────────────────

(defn emit-form!
  "Governed entry point for FORM opcode.
   Creates pos-form.xml at the temporal path today/2020s/YYYY/MM/DD/.

   policy-map  — policy descriptor; nil → default-policy
   template-src — path to source template; nil → default-template-src
   contact     — contact data map; nil → default-contact (from screenshot)

   Returns a zero-arg thunk per govern contract.

   Result map:
     {:ok :xml :path :calendars :time}"
  ([auth]
   (emit-form! auth nil nil))
  ([auth policy-map template-src]
   (emit-form! auth policy-map template-src nil))
  ([auth policy-map template-src contact]
   (lam/govern auth
     (fn [t]
       (let [policy   (or policy-map default-policy)
             tmpl-src (or template-src default-template-src)
             ctct     (or contact default-contact)
             cal      (cal/london-triple)
             iso-ts   (or (:london-iso cal) (:iso t))
             tree     (build-form-tree policy tmpl-src ctct cal iso-ts)
             sw       (StringWriter.)
             xml-str  (genx/emit-document! sw tree)
             out-path (form-output-path)
             out-file (File. out-path)]
         (io/make-parents out-file)
         (spit out-file xml-str)
         {:ok       true
          :xml      xml-str
          :path     out-path
          :policy   (select-keys policy [:id :predicate :terms-active])
          :template tmpl-src
          :contact  (select-keys ctct [:canonical :alias :username])
          :calendars cal
          :time     (select-keys t [:iso :path])})))))
