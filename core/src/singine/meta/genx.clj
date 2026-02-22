(ns singine.meta.genx
  "Tim Bray genx principle implemented over javax.xml.stream.XMLStreamWriter.

   Design
   ──────
   · As few element types as possible — attributes carry data, elements carry structure.
   · Every call is a named lambda (anonymous function) composed via govern.
   · Exceptions surface at JVM level only — Clojure/Racket callers see clean values.
   · The emitter is stateless: (emit! writer tree) → writer (side-effecting, not pure).
   · The tree is a vector: [:tag {:attr val} child1 child2 ...]
     — identical to Clojure's hiccup convention, so it composes with existing data.

   root.xml generation
   ───────────────────
   (regenerate! ws-root readme-text) reads the workspace root directory name,
   the README content from .meta/ (or fallback), and re-emits root.xml with
   the minimum number of XMLStreamWriter calls — one per structural node.

   Exceptions
   ──────────
   All javax.xml.stream.XMLStreamException are caught here and rethrown as
   ex-info maps with :cause, :stage, and :path keys. Racket/Clojure callers
   never see raw Java exceptions from this namespace."
  (:require [clojure.java.io  :as io]
            [clojure.string   :as str])
  (:import [javax.xml.stream
            XMLOutputFactory XMLStreamWriter]
           [java.io StringWriter File FileWriter]
           [java.time Instant]))

;; ── low-level emitter ────────────────────────────────────────────────────────

(defn- write-start!
  [^XMLStreamWriter w tag attrs]
  (try
    (.writeStartElement w (name tag))
    (doseq [[k v] attrs]
      (.writeAttribute w (name k) (str v)))
    w
    (catch Exception e
      (throw (ex-info "genx write-start! failed"
                      {:cause (.getMessage e) :stage :start :tag tag})))))

(defn- write-end!   [^XMLStreamWriter w] (.writeEndElement w) w)
(defn- write-chars! [^XMLStreamWriter w ^String s]
  (when (seq s) (.writeCharacters w s)) w)
(defn- write-cdata! [^XMLStreamWriter w ^String s]
  (when (seq s) (.writeCData w s)) w)
(defn- write-comment! [^XMLStreamWriter w ^String s]
  (.writeComment w (str " " s " ")) w)
(defn- write-pi! [^XMLStreamWriter w ^String target ^String data]
  (.writeProcessingInstruction w target data) w)

;; ── tree emitter ─────────────────────────────────────────────────────────────

(declare emit!)

(defn- emit-children! [w children]
  (doseq [child children]
    (cond
      (nil? child)    nil
      (string? child) (write-chars! w child)
      (vector? child) (emit! w child)
      (map? child)    nil                    ;; attrs already consumed
      :else           (write-chars! w (str child))))
  w)

(defn emit!
  "Emit a hiccup-style tree to XMLStreamWriter w.

   Forms:
     [:tag]
     [:tag {:attr val}]
     [:tag {:attr val} \"text\"]
     [:tag {:attr val} [:child] [:child]]
     [:!-- \"comment text\"]
     [:?pi \"target\" \"data\"]
     [:cdata \"raw text\"]

   Returns w."
  [^XMLStreamWriter w node]
  (cond
    (not (vector? node)) (write-chars! w (str node))
    (= :!-- (first node)) (write-comment! w (second node))
    (= :?pi (first node)) (write-pi! w (second node) (nth node 2 ""))
    (= :cdata (first node)) (write-cdata! w (second node))
    :else
    (let [[tag & rest]  node
          attrs         (if (map? (first rest)) (first rest) {})
          children      (if (map? (first rest)) (next rest) rest)]
      (write-start! w tag attrs)
      (emit-children! w children)
      (write-end! w)
      w)))

;; ── document wrapper ─────────────────────────────────────────────────────────

(defn emit-document!
  "Emit a complete XML document (with XML declaration) to writer out.
   tree is the root hiccup node.
   Returns the serialised string if out is a StringWriter, else nil."
  [out tree & {:keys [encoding indent?]
               :or   {encoding "UTF-8" indent? true}}]
  (let [factory (doto (XMLOutputFactory/newInstance))
        sw      (if (instance? StringWriter out) out nil)
        w       (if sw
                  (.createXMLStreamWriter factory sw)
                  (.createXMLStreamWriter factory out encoding))]
    (try
      (.writeStartDocument w encoding "1.0")
      (.writeCharacters w "\n")
      (emit! w tree)
      (.writeEndDocument w)
      (.flush w)
      (when sw (.toString sw))
      (catch Exception e
        (throw (ex-info "genx emit-document! failed"
                        {:cause (.getMessage e) :stage :document})))
      (finally (.close w)))))

;; ── root.xml tree builder ────────────────────────────────────────────────────

(defn- asset-el [a]
  [:asset-type (merge {:opcode (:opcode a) :name (:name a)
                       :handler (or (:handler a) "TODO")
                       :urn (str "urn:singine:asset:" (:opcode a))}
                      (select-keys a [:command :kafka-topic :collibra-domain
                                      :status :description]))])

(defn- snap-stage-el [{:keys [order name handler input-type output-type description]}]
  [:snap-stage {:order order :name name :handler handler
                :input-type input-type :output-type output-type
                :description (or description "")}])

(defn build-root-tree
  "Build the hiccup tree for root.xml.

   Arguments:
     dir-name   — name of the parent directory (the git repo name)
     readme     — string content of .meta/sindoc.sindoc or README
     opts       — map of optional overrides:
                    :version :generated-at :git-remote
                    :extra-assets (seq of asset maps)
                    :extra-snap-stages (seq of stage maps)"
  [dir-name readme & {:keys [version generated-at git-remote
                             extra-assets extra-snap-stages]
                      :or   {version      "0.4.0"
                             generated-at (str (Instant/now))
                             git-remote   "https://github.com/sindoc/singine"}}]
  [:singine-repo
   {:xmlns          "urn:singine:1.0"
    :version        version
    :generated-at   generated-at
    :cell           ".meta/0-stem/0-cell"
    :generator      "singine.meta.genx/regenerate!"
    :urn            "urn:sindoc:singine"
    :git-remote     git-remote}

   [:!-- "root.xml — generated by singine.meta.genx — do not hand-edit"]

   [:repo-info {:dir-name dir-name :readme-path ".meta/sindoc.sindoc"}
    [:title dir-name]
    [:readme [:cdata readme]]
    [:description "singine: OCR pipeline, RDF, SPARQL+NL, Kafka, sinedge edge agents."]]

   [:lang-registry
    [:lang {:id "lang-racket"  :token "racket"  :runtime "racket"
            :handler-ns "singine.lang.racket"   :xml-pi "lang racket"
            :description "#lang racket — Racket runtime via subprocess or GraalVM"}]
    [:lang {:id "lang-singine" :token "sindoc"  :runtime "clojure"
            :handler-ns "singine.lang.singine"  :xml-pi "lang singine"
            :description "#lang sindoc — native Singine document runtime"}]
    [:lang {:id "lang-xml"     :token "xml"     :runtime "javax.xml"
            :handler-ns "singine.lang.xml"      :xml-pi "lang xml"
            :description "#lang xml — validate against singine.dtd"}]
    [:lang {:id "lang-multi"   :token "multi"   :runtime "multi"
            :handler-ns "singine.lang.multi"    :xml-pi "lang multi"
            :description "#lang a,b,c,singine — evaluate each lang in sequence"}]
    [:lang {:id "lang-sparql"  :token "sparql"  :runtime "jena-arq"
            :handler-ns "singine.lang.sparql"   :xml-pi "lang sparql"
            :description "#lang sparql — SPARQL via Jena ARQ"}]]

   ;; core assets
   (asset-el {:opcode "SNAP" :name "SnapProcess"
              :command "singine snap"
              :kafka-topic "singine.inbound.snap"
              :handler "singine.sinedge.snap/process!"
              :collibra-domain "singine.Snap" :status "active"
              :description "Snapshot pipeline: OCR → index → RDF → NL→SPARQL→API."})
   (asset-el {:opcode "SNGE" :name "SinedgeEngine"
              :command "singine edge engine"
              :kafka-topic "singine.inbound.request"
              :handler "singine.sinedge.engine/start!"
              :collibra-domain "singine.Edge" :status "active"
              :description "sinedge-engine: governed lambda executor."})
   (asset-el {:opcode "SNAG" :name "SinedgeAgent"
              :command "singine edge agent"
              :kafka-topic "singine.inbound.request"
              :handler "singine.sinedge.agent/start!"
              :collibra-domain "singine.Edge" :status "active"
              :description "sinedge-agent: NL→SPARQL→MCP interface."})
   (asset-el {:opcode "LANG" :name "LangDispatch"
              :command "singine lang"
              :handler "singine.lang.dispatch/route!"
              :collibra-domain "singine.Lang" :status "active"
              :description "#lang dispatcher: racket/singine/xml/multi."})

   ;; POS opcodes: BLKP CATC MCEL GITP IDNT
   (asset-el {:opcode "BLKP" :name "BlockProcessor"
              :command "singine pos blkp"
              :kafka-topic "singine.pos.blocks"
              :handler "singine.pos.block-processor/process-blocks!"
              :collibra-domain "singine.POS" :status "active"
              :description "Block processor: getUrl(convert2(unicode)) per .sindoc block → JSON + XML + ZIP."})
   (asset-el {:opcode "CATC" :name "CategoryC"
              :command "singine pos catc"
              :kafka-topic "singine.pos.category"
              :handler "singine.pos.category/activate!"
              :collibra-domain "singine.POS" :status "active"
              :description "Category C: objects + subjects → PredicateFactory predicates."})
   (asset-el {:opcode "MCEL" :name "MetaCell"
              :command "singine pos mcel"
              :kafka-topic "singine.meta.cell"
              :handler "singine.meta.cell/wire-cwd!"
              :collibra-domain "singine.Meta" :status "active"
              :description "Meta cell: .meta/cell.sindoc + manifest.json + root-ref.txt in CWD."})
   (asset-el {:opcode "GITP" :name "GitPush"
              :command "singine pos gitp"
              :kafka-topic "singine.vcs.push"
              :handler "singine.pos.git-op/push-algorithm!"
              :collibra-domain "singine.VCS" :status "active"
              :description "Git algorithm deploy: cherry-pick from algorithm-registry, commit, push."})
   (asset-el {:opcode "IDNT" :name "Identity"
              :command "singine pos idnt"
              :kafka-topic "singine.pos.identity"
              :handler "singine.pos.identity/authenticate!"
              :collibra-domain "singine.POS" :status "active"
              :description "Identity: Kerberos(idv1), OpenLDAP(idv2), OIDC(idv3), SAML(idv4), PAM/NSS(idv5)."})
   (asset-el {:opcode "FORM" :name "FormEmitter"
              :command "singine pos form"
              :kafka-topic "singine.pos.form"
              :handler "singine.pos.form/emit-form!"
              :collibra-domain "singine.POS" :status "active"
              :description "Form emitter: governed form via policy p + template t. Wraps contact record in p:policy + t:template + london-triple."})
   (asset-el {:opcode "LOCP" :name "LocationProbe"
              :command "singine pos locp"
              :kafka-topic "singine.pos.location"
              :handler "singine.pos.location/probe!"
              :collibra-domain "singine.POS" :status "active"
              :description "Location probe: IATA/postal→URN, SOAP 1.2 request, RelaxNG+Schematron validation, SODA scan, NannyML drift."})

   ;; extra assets (caller-supplied)
   (into [:snap-pipeline {:opcode "SNAP" :urn "urn:singine:snap:pipeline"}]
         (concat
           [(snap-stage-el {:order "1" :name "ingest"     :handler "singine.sinedge.snap/ingest!"
                            :input-type "file|stream|base64" :output-type "bytes"})
            (snap-stage-el {:order "2" :name "preprocess" :handler "singine.sinedge.snap/preprocess!"
                            :input-type "bytes" :output-type "image/png"})
            (snap-stage-el {:order "3" :name "ocr"        :handler "singine.sinedge.snap/ocr!"
                            :input-type "image/png" :output-type "text/plain"})
            (snap-stage-el {:order "4" :name "extract"    :handler "singine.sinedge.snap/extract!"
                            :input-type "text/plain" :output-type "application/x-tika-parsed"})
            (snap-stage-el {:order "5" :name "index"      :handler "singine.sinedge.snap/index!"
                            :input-type "application/x-tika-parsed" :output-type "lucene/index"})
            (snap-stage-el {:order "6" :name "triple"     :handler "singine.sinedge.snap/triple!"
                            :input-type "application/x-tika-parsed" :output-type "application/rdf+xml"})
            (snap-stage-el {:order "7" :name "nl-query"   :handler "singine.sinedge.agent/nl-to-sparql"
                            :input-type "text/natural-language" :output-type "application/sparql-query"})
            (snap-stage-el {:order "8" :name "dispatch"   :handler "singine.sinedge.agent/sparql-to-api"
                            :input-type "application/sparql-query" :output-type "application/json"})]
           (map snap-stage-el (or extra-snap-stages []))))])

;; ── regenerate! ─────────────────────────────────────────────────────────────

(defn regenerate!
  "Regenerate root.xml at dest-path.

   Steps (genx principle — minimum calls):
     1. Read parent dir name from dest-path (or ws-root)
     2. Read README from .meta/sindoc.sindoc or .meta/README
     3. Build hiccup tree via build-root-tree
     4. Emit via XMLStreamWriter to dest-path

   Exceptions are ex-info maps; callers need not import any Java type."
  [dest-path & opts]
  (try
    (let [dest   (io/file dest-path)
          _      (io/make-parents dest)
          ws     (.getParentFile (.getParentFile (.getParentFile dest))) ;; up from .meta/0-stem/0-cell/
          dir-nm (.getName ws)
          readme-f (or (let [f (io/file ws ".meta/sindoc.sindoc")]
                         (when (.exists f) f))
                       (let [f (io/file ws ".meta/README")]
                         (when (.exists f) f))
                       (let [f (io/file ws "README.md")]
                         (when (.exists f) f)))
          readme (if readme-f (slurp readme-f) (str "# " dir-nm))
          tree   (apply build-root-tree dir-nm readme opts)]
      (with-open [fw (FileWriter. dest)]
        (emit-document! fw tree))
      {:ok true :path (str dest) :dir dir-nm})
    (catch clojure.lang.ExceptionInfo e
      (throw e))
    (catch Exception e
      (throw (ex-info "regenerate! failed"
                      {:cause (.getMessage e) :path dest-path})))))
