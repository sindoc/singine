(ns singine.pos.block-processor
  "Block Processor — opcode BLKP.

   For each block in a .sindoc / .rkt / .sgn document:
     block text → convert2 (code points) → get-url (unicode->context) → {json, xml}

   Output: ZIP archive containing blocks.xml, blocks.json, manifest.txt
   XML root element: <singine-repo> (matches root.xml canonical root)
   ZIP written to: <dim-dir>/exec-blocks.zip (dim-dir = proto/c, cc, or ccc)

   Logseq block alignment:
     Each {:tag :line :attrs {:n N} :children [text]} from document->map = one block.

   The history itself (shell commands as numbered lines) is a valid block stream
   — feeds naturally into this processor as test input."
  (:require [singine.pos.lambda      :as lam]
            [singine.pos.unicode-time :as ut]
            [singine.pos.calendar    :as cal]
            [singine.sindoc.parser   :as sp]
            [singine.meta.genx       :as genx]
            [clojure.data.json       :as json]
            [clojure.string          :as str]
            [clojure.java.io         :as io])
  (:import [java.util.zip ZipOutputStream ZipEntry]
           [java.io ByteArrayOutputStream StringWriter]))

;; ── extract-lines: recursively find all :line nodes in a document tree ──────

(defn extract-lines
  "Walk a document->map tree and collect all {:tag :line ...} nodes.
   Handles the nested :body / :section structure from SindocParser."
  [node]
  (cond
    (nil? node) []
    (map? node)
    (if (= :line (:tag node))
      [node]
      (mapcat extract-lines (:children node)))
    (sequential? node)
    (mapcat extract-lines node)
    :else []))

;; ── convert2: text → code point sequence ────────────────────────────────────

(defn convert2
  "Extract Unicode code points from text as a vector of ints.
   Equivalent to: str.codePoints().toArray()"
  [^String text]
  (if (str/blank? text)
    []
    (vec (.toArray (.codePoints text)))))

;; ── get-url: code points → context maps (Nash equilibrium) ──────────────────

(defn get-url
  "Map a sequence of code points through unicode->context (Nash equilibrium).
   Deduplicates code points first (distinct blocks only).
   Returns a vector of context maps: {:block :country :tz :relative-date :speakers ...}"
  [code-points]
  (mapv ut/unicode->context (distinct code-points)))

;; ── process-block: one Logseq block → enriched map ──────────────────────────

(defn process-block
  "Process a single block map (from document->map).
   Returns {:block-n :text :code-points :contexts :json :xml-tree}"
  [block-map]
  (let [text    (or (first (:children block-map)) "")
        n       (get-in block-map [:attrs :n] "0")
        cps     (convert2 text)
        urls    (get-url cps)
        ctx-j   (mapv #(-> %
                           (dissoc :relative-date)
                           (update :block str)
                           (update :langs vec)) urls)
        xml-tree [:block {:n n}
                  (into [:contexts]
                        (map (fn [ctx]
                               [:context {:country (or (:country ctx) "??")
                                          :tz      (or (:tz ctx) "UTC")
                                          :block   (str (:block ctx))
                                          :date    (str (:relative-date ctx))
                                          :speakers (str (or (:speakers ctx) 0))}])
                             urls))]]
    {:block-n      n
     :text         text
     :code-points  cps
     :contexts     urls
     :json         (json/write-str {:block-n n :text text :contexts ctx-j})
     :xml-tree     xml-tree}))

;; ── to-zip!: package XML + JSON + manifest into a ZIP byte array ─────────────

(defn to-zip!
  "Package xml-str, json-str, and manifest-str into a ZIP.
   Returns a byte array."
  [xml-str json-str manifest-str]
  (let [baos (ByteArrayOutputStream.)
        zos  (ZipOutputStream. baos)]
    (doseq [[name content] [["blocks.xml"    xml-str]
                             ["blocks.json"   json-str]
                             ["manifest.txt"  manifest-str]]]
      (let [bytes (.getBytes ^String content "UTF-8")]
        (.putNextEntry zos (ZipEntry. name))
        (.write zos bytes 0 (count bytes))
        (.closeEntry zos)))
    (.close zos)
    (.toByteArray baos)))

;; ── dim-dir: edge size → proto/c, proto/cc, or proto/ccc ────────────────────

(defn dim-dir
  "Map pivot-dimension count to a proto/ subdirectory.
   dim=1 → proto/c, dim=2 → proto/cc, dim=3+ → proto/ccc"
  [dim ws-root]
  (let [sub (cond (= dim 1) "c"
                  (= dim 2) "cc"
                  :else      "ccc")]
    (str ws-root "/proto/" sub)))

;; ── process-blocks-str: process a sindoc string directly ────────────────────

(defn process-blocks-str
  "Process a .sindoc-format string (not a file path).
   Used in tests with mock content.
   Returns {:xml :json :zip-bytes :block-count :dim}"
  [^String sindoc-content]
  (let [doc-map  (sp/document->map (sp/parse-string sindoc-content))
        blocks   (vec (extract-lines doc-map))
        processed (mapv process-block blocks)
        ;; XML
        xml-tree [:singine-repo {:xmlns "urn:singine:1.0" :generator "singine.pos.block-processor"}
                  (into [:blocks {:count (str (count processed))}]
                        (map :xml-tree processed))]
        sw       (StringWriter.)
        xml-str  (genx/emit-document! sw xml-tree)
        ;; JSON — sanitize contexts: convert LocalDate to string, drop unserializable fields
        sanitize-ctx (fn [ctx]
                       (-> ctx
                           (update :relative-date str)
                           (update :block str)
                           (update :langs vec)
                           (dissoc :code-point :char-str)))
        json-str (json/write-str {:blocks (mapv (fn [b]
                                                  {:block-n  (:block-n b)
                                                   :text     (:text b)
                                                   :contexts (mapv sanitize-ctx (:contexts b))})
                                                processed)})
        ;; Manifest
        cal      (cal/london-triple)
        manifest (str "singine BLKP\n"
                      "blocks: " (count processed) "\n"
                      "timestamp: " (get-in cal [:london-iso]) "\n"
                      "topic: [[t/1]]\n"
                      "urn: urn:singine:topic:t/1\n")
        dim      (count (distinct (mapcat #(mapv :block (:contexts %)) processed)))
        zip-bytes (to-zip! (or xml-str "") json-str manifest)]
    {:xml        (or xml-str "")
     :json       json-str
     :manifest   manifest
     :zip-bytes  zip-bytes
     :block-count (count processed)
     :dim        (max 1 dim)}))

;; ── process-blocks!: governed entry point (opcode BLKP) ─────────────────────

(defn process-blocks!
  "Governed entry point for BLKP opcode.
   Parses sindoc-path, processes each block, emits ZIP.
   Returns a zero-arg thunk."
  [auth sindoc-path]
  (lam/govern auth
    (fn [t]
      (let [doc-map   (sp/document->map (sp/parse-file sindoc-path))
            blocks    (vec (extract-lines doc-map))
            processed (mapv process-block blocks)
            ;; Build XML tree with singine-repo root
            xml-tree  [:singine-repo
                       {:xmlns         "urn:singine:1.0"
                        :generator     "singine.pos.block-processor"
                        :source        sindoc-path
                        :generated-at  (:iso t)}
                       (into [:blocks {:count (str (count processed))}]
                             (map :xml-tree processed))]
            sw        (StringWriter.)
            xml-str   (genx/emit-document! sw xml-tree)
            sanitize-ctx (fn [ctx]
                           (-> ctx
                               (update :relative-date str)
                               (update :block str)
                               (update :langs vec)
                               (dissoc :code-point :char-str)))
            json-str  (json/write-str
                        {:source sindoc-path
                         :time   (select-keys t [:iso :path])
                         :blocks (mapv (fn [b]
                                         {:block-n  (:block-n b)
                                          :text     (:text b)
                                          :contexts (mapv sanitize-ctx (:contexts b))})
                                       processed)})
            cal        (cal/london-triple)
            manifest   (str/join "\n"
                         ["singine BLKP"
                          (str "source: " sindoc-path)
                          (str "blocks: " (count processed))
                          (str "timestamp: " (:london-iso cal))
                          (str "path: " (:path t))
                          "topic: [[t/1]]"
                          "urn: urn:singine:topic:t/1"])
            dim        (count (distinct (mapcat #(mapv :block (:contexts %)) processed)))
            zip-bytes  (to-zip! (or xml-str "") json-str manifest)]
        {:ok          true
         :source      sindoc-path
         :block-count (count processed)
         :dim         (max 1 dim)
         :xml         (or xml-str "")
         :zip-bytes   zip-bytes
         :time        (select-keys t [:iso :path])}))))
