(ns singine.pos.exec
  "exec.clj — governed boot pipeline for exec.rkt / .sindoc / .sgn documents.

   Boot sequence (mirrors proto/x.sgn):
     1. $ timestamp self     → lam/now → SingineTime record
     2. $ authorize self     → make-auth → govern
     3. $ read logseq today  → read Logseq journal for today from kernel graph
     4. $ create xml ROOT    → genx/emit-document! → exec.xml

   The canonical input is /Users/skh/ws/today/exec.rkt (a .sindoc format file).
   It is parsed via SindocParser and each block is dispatched through the
   singine.lang.dispatch multi-lang router.

   Output is written to: today/2020s/2026/02/21/exec.xml
   (temporal path pattern from pos-contact.xml)

   Directory constant: SINGINE_LOGSEQ_GRAPH env var → kernel graph path
   Fallback: /Users/skh/ws/logseq/singine/kernel"
  (:require [singine.pos.lambda         :as lam]
            [singine.pos.calendar       :as cal]
            [singine.pos.block-processor :as bp]
            [singine.pos.category       :as catc]
            [singine.meta.cell          :as cell]
            [singine.meta.genx          :as genx]
            [singine.sindoc.parser      :as sp]
            [singine.meta.root          :as root]
            [clojure.java.io            :as io]
            [clojure.string             :as str])
  (:import [java.io StringWriter File]
           [java.time LocalDate ZoneId ZonedDateTime]
           [java.time.format DateTimeFormatter]
           [java.nio.file Paths Files Path]))

;; ── Logseq kernel path ────────────────────────────────────────────────────────

(defn kernel-path
  "Resolve the Logseq kernel graph path.
   Reads SINGINE_LOGSEQ_GRAPH env or defaults to /Users/skh/ws/logseq/singine/kernel."
  []
  (or (System/getenv "SINGINE_LOGSEQ_GRAPH")
      "/Users/skh/ws/logseq/singine/kernel"))

(defn today-journal-path
  "Return the path to today's Logseq journal file.
   Pattern: <kernel>/journals/<YYYY_MM_DD>.md"
  []
  (let [zdt    (ZonedDateTime/now (ZoneId/of "Europe/London"))
        y      (.getYear zdt)
        m      (format "%02d" (.getMonthValue zdt))
        d      (format "%02d" (.getDayOfMonth zdt))
        fname  (str y "_" m "_" d ".md")]
    (str (kernel-path) "/journals/" fname)))

(defn read-journal
  "Read today's Logseq journal. Returns content string or nil if not found."
  []
  (let [path (today-journal-path)
        f    (File. path)]
    (when (.exists f)
      (slurp f))))

;; ── Temporal output path ──────────────────────────────────────────────────────

(defn exec-output-path
  "Return the temporal output path for exec.xml.
   Pattern: today/2020s/<year>/<MM>/<dd>/exec.xml"
  [ws-root]
  (let [zdt  (ZonedDateTime/now (ZoneId/of "Europe/London"))
        year (.getYear zdt)
        m    (format "%02d" (.getMonthValue zdt))
        d    (format "%02d" (.getDayOfMonth zdt))
        decade (str (- year (mod year 10)) "s")]
    (str ws-root "/today/" decade "/" year "/" m "/" d "/exec.xml")))

;; ── Block dispatcher (multi-lang router) ─────────────────────────────────────

(defn- dispatch-lang
  "Dispatch a block by its detected lang.
   Returns :racket, :singine, :sindoc, or :unknown."
  [block-text]
  (cond
    (str/includes? block-text "#lang racket")  :racket
    (str/includes? block-text "#lang singine") :singine
    (str/includes? block-text "#lang sindoc")  :sindoc
    :else                                       :unknown))

(defn- route-block!
  "Route a single document block through the appropriate handler.
   Returns {:block-n :lang :result}"
  [block-map]
  (let [text (or (first (:children block-map)) "")
        n    (get-in block-map [:attrs :n] "0")
        lang (dispatch-lang text)]
    {:block-n n
     :lang    lang
     :text    (subs text 0 (min 80 (count text)))}))

;; ── Boot sequence ─────────────────────────────────────────────────────────────

(defn boot!
  "Governed boot pipeline for exec.rkt / any .sindoc document.

   Steps:
     1. timestamp self  — captures SingineTime
     2. authorize self  — make-auth with open token (dev)
     3. parse document  — SindocParser → document->map → blocks
     4. process blocks  — BLKP: convert2 + get-url per block
     5. activate CATC   — Category C over processed blocks
     6. wire .meta/     — MCEL: cell.sindoc + manifest.json + root-ref.txt
     7. emit XML        — genx: exec.xml at temporal path

   doc-path: path to .sindoc / .rkt / .sgn file (default: exec.rkt from today/)
   Returns a zero-arg thunk per govern contract."
  ([auth]
   (boot! auth nil))
  ([auth doc-path]
   (lam/govern auth
     (fn [t]
       (let [;; Resolve document path
             doc-file  (or doc-path
                           (str (System/getProperty "user.dir") "/exec.rkt"))
             doc-exists (.exists (File. doc-file))

             ;; Parse document (or use synthetic content for boot)
             doc-content
             (if doc-exists
               (slurp doc-file)
               "#lang singine\nsingine exec boot\n--\n</>")

             ;; Read today's Logseq journal
             journal   (read-journal)

             ;; Parse + extract blocks
             doc-map   (sp/document->map (sp/parse-string doc-content))
             blocks    (vec (bp/extract-lines doc-map))

             ;; Route blocks (multi-lang dispatch)
             routed    (mapv route-block! blocks)

             ;; BLKP: process blocks (unicode->context pipeline)
             blkp-result (bp/process-blocks-str doc-content)

             ;; CATC: activate Category C
             catc-auth   (lam/make-auth (:agent auth) :connect)
             catc-thunk  (catc/activate! catc-auth
                                         (mapv (fn [b] {:block-n (:block-n b)
                                                        :contexts []})
                                               blocks))
             catc-result (catc-thunk)

             ;; MCEL: wire .meta/ in exec dir
             exec-dir    (.getParent (File. doc-file))
             mcel-auth   (lam/make-auth (:agent auth) :write)
             mcel-thunk  (cell/wire-cwd! mcel-auth (or exec-dir (System/getProperty "user.dir")))
             mcel-result (mcel-thunk)

             ;; Calendar + temporal path
             cal         (cal/london-triple)
             ws-root     (str (or (root/find-workspace-root) (System/getProperty "user.dir")))
             out-path    (exec-output-path ws-root)

             ;; Build XML tree for exec.xml
             xml-tree    [:singine-exec
                          {:xmlns        "urn:singine:1.0"
                           :generator    "singine.pos.exec/boot!"
                           :source       doc-file
                           :generated-at (:iso t)
                           :dim          (str (:dim blkp-result))}
                          [:boot-sequence {}
                           [:step {:id "1" :name "timestamp-self" :status "done"}]
                           [:step {:id "2" :name "authorize-self" :status "done"}]
                           [:step {:id "3" :name "read-logseq-today"
                                   :status (if journal "done" "no-journal")
                                   :path   (today-journal-path)}]
                           [:step {:id "4" :name "create-xml-root" :status "done"}]]
                          [:blocks {:count (str (count blocks))}
                           (into [:block-routes {}]
                                 (map (fn [r]
                                        [:block {:n    (:block-n r)
                                                 :lang (name (:lang r))}])
                                      routed))]
                          [:calendars {}
                           [:gregorian {:year  (str (get-in cal [:gregorian :year]))
                                        :month (str (get-in cal [:gregorian :month]))
                                        :day   (str (get-in cal [:gregorian :day]))}]
                           [:persian   {:year  (str (get-in cal [:persian :year]))
                                        :note  (get-in cal [:persian :note] "")}]
                           [:chinese   {:sexagenary (get-in cal [:chinese :sexagenary])
                                        :animal     (get-in cal [:chinese :animal])}]]]

             ;; Emit XML
             sw          (StringWriter.)
             xml-str     (genx/emit-document! sw xml-tree)

             ;; Write exec.xml (ensure directories exist)
             _           (when xml-str
                           (let [out-file (File. out-path)]
                             (io/make-parents out-file)
                             (spit out-file xml-str)))]

         {:ok          true
          :doc-path    doc-file
          :doc-exists  doc-exists
          :blocks      (count blocks)
          :routed      routed
          :blkp        (select-keys blkp-result [:block-count :dim])
          :catc        (select-keys catc-result [:ok :dim :log-ready])
          :mcel        (select-keys mcel-result [:ok :wrote])
          :journal     (when journal (subs journal 0 (min 80 (count journal))))
          :xml-path    (when xml-str out-path)
          :calendars   cal
          :time        (select-keys t [:iso :path])})))))

;; ── CLI entry ─────────────────────────────────────────────────────────────────

(defn -main
  "Boot singine from exec.rkt. Accepts optional doc-path arg."
  [& args]
  (let [doc-path  (first args)
        auth      (lam/make-auth "urn:singine:pos:exec" :anonymous-function)
        thunk     (boot! auth doc-path)
        result    (thunk)]
    (println result)))
