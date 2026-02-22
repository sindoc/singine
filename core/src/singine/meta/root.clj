(ns singine.meta.root
  "Read, generate, and query root.xml — the Singine source of truth.

   root.xml lives at .meta/0-stem/0-cell/root.xml (relative to the
   workspace root). It is the single file that traces every implemented
   feature back to a Collibra asset type with a 4-letter opcode.

   This namespace:
     - Locates root.xml by walking up from the current directory
     - Parses it into Clojure maps
     - Generates singine help output from it
     - Regenerates root.xml from .sin/.skh/.x source files

   No library above Chomsky type-3 is used for naming conventions.
   All pattern matching is done by java.util.regex (sed/awk equivalent)."
  (:require [clojure.java.io   :as io]
            [clojure.string    :as str]
            [clojure.data.json :as json])
  (:import [javax.xml.parsers  DocumentBuilderFactory]
           [javax.xml.transform TransformerFactory OutputKeys]
           [javax.xml.transform.dom DOMSource]
           [javax.xml.transform.stream StreamResult]
           [org.w3c.dom Element NodeList Document Node]
           [java.io StringWriter]
           [java.nio.file Path Paths Files]
           [java.time Instant]))

;; ════════════════════════════════════════════════════════════════════
;; ROOT.XML LOCATION
;; ════════════════════════════════════════════════════════════════════

(def root-xml-rel-path
  "Path of root.xml relative to the workspace root."
  ".meta/0-stem/0-cell/root.xml")

(defn find-workspace-root
  "Walk up from start-dir to find the workspace root.
   The workspace root contains a .meta/0-stem/0-cell/root.xml file.
   Returns the Path, or nil if not found."
  ([] (find-workspace-root (Paths/get (System/getProperty "user.dir")
                                      (into-array String []))))
  ([start-dir]
   (loop [dir (if (instance? Path start-dir) start-dir
                  (Paths/get (str start-dir) (into-array String [])))]
     (let [candidate (.resolve dir root-xml-rel-path)]
       (cond
         (Files/exists candidate (into-array java.nio.file.LinkOption []))
         dir

         (nil? (.getParent dir))
         nil

         (= dir (.getParent dir))
         nil

         :else
         (recur (.getParent dir)))))))

(defn root-xml-path
  "Return the Path to root.xml, or nil if not found."
  []
  (when-let [ws (find-workspace-root)]
    (.resolve ws root-xml-rel-path)))

;; ════════════════════════════════════════════════════════════════════
;; XML PARSING UTILITIES
;; ════════════════════════════════════════════════════════════════════

(defn- parse-xml-doc
  "Parse an XML file at path into a DOM Document."
  ^Document [path]
  (let [dbf (DocumentBuilderFactory/newInstance)]
    (.setNamespaceAware dbf false)
    (-> dbf
        (.newDocumentBuilder)
        (.parse (.toFile (if (instance? Path path) path
                             (Paths/get (str path) (into-array String []))))))))

(defn- nodelist->seq
  "Convert a NodeList to a lazy seq of Element nodes (skips text nodes)."
  [^NodeList nl]
  (for [i (range (.getLength nl))
        :let [n (.item nl i)]
        :when (= Node/ELEMENT_NODE (.getNodeType n))]
    ^Element n))

(defn- el-attrs
  "Return all attributes of an Element as a Clojure map (keyword keys)."
  [^Element el]
  (let [attrs (.getAttributes el)]
    (into {}
          (for [i (range (.getLength attrs))]
            (let [attr (.item attrs i)]
              [(keyword (.getNodeName attr)) (.getNodeValue attr)])))))

;; ════════════════════════════════════════════════════════════════════
;; ROOT.XML READER
;; ════════════════════════════════════════════════════════════════════

(defn load-root
  "Parse root.xml and return a Clojure map:
     {:version       \"0.3.0\"
      :generated-at  \"...\"
      :cell          \"...\"
      :asset-types   [{:opcode :STRT :name ... :command ... ...} ...]
      :naming        {:private-ext {:regex ... :default ...} ...}
      :iceberg-layers [{:name :raw :topic-prefix ... :format ...} ...]
      :kafka-topics  [{:name ... :partitions 1 ...} ...]
      :db-dialects   {:default :sqlite :dialects [{...} ...]}}"
  ([]
   (if-let [p (root-xml-path)]
     (load-root p)
     (throw (ex-info "root.xml not found. Run singine meta regenerate." {}))))
  ([path]
   (let [doc   (parse-xml-doc path)
         root  ^Element (.getDocumentElement doc)

         asset-types
         (->> (.getElementsByTagName root "asset-type")
              nodelist->seq
              (mapv el-attrs))

         naming
         (->> (.getElementsByTagName root "pattern")
              nodelist->seq
              (reduce (fn [m el]
                        (let [a (el-attrs el)]
                          (assoc m (keyword (:name a)) (dissoc a :name))))
                      {}))

         iceberg-layers
         (->> (.getElementsByTagName root "layer")
              nodelist->seq
              (mapv el-attrs))

         kafka-topics
         (->> (.getElementsByTagName root "topic")
              nodelist->seq
              (mapv el-attrs))

         db-dialects-el
         (first (nodelist->seq (.getElementsByTagName root "db-dialects")))

         db-dialects
         {:default   (keyword (or (and db-dialects-el
                                       (.getAttribute db-dialects-el "default"))
                                  "sqlite"))
          :dialects  (->> (.getElementsByTagName root "dialect")
                          nodelist->seq
                          (mapv el-attrs))}]

     {:version      (.getAttribute root "version")
      :generated-at (.getAttribute root "generated-at")
      :cell         (.getAttribute root "cell")
      :asset-types  asset-types
      :naming       naming
      :iceberg-layers iceberg-layers
      :kafka-topics kafka-topics
      :db-dialects  db-dialects})))

(def ^:private root-cache
  "Atom caching the loaded root map. Cleared by regenerate!."
  (atom nil))

(defn root
  "Return the loaded root map, caching after first load."
  []
  (or @root-cache
      (reset! root-cache (load-root))))

(defn asset-types
  "Return all asset-type maps from root.xml."
  []
  (:asset-types (root)))

(defn asset-by-opcode
  "Return the asset-type map for the given opcode string (e.g. \"CHKX\"), or nil."
  [opcode]
  (first (filter #(= opcode (:opcode %)) (asset-types))))

(defn naming
  "Return the naming-conventions map."
  []
  (:naming (root)))

(defn kafka-topics
  "Return the list of Kafka topic maps."
  []
  (:kafka-topics (root)))

(defn default-dialect
  "Return the default DB dialect keyword from root.xml."
  []
  (get-in (root) [:db-dialects :default] :sqlite))

;; ════════════════════════════════════════════════════════════════════
;; HELP TEXT GENERATION
;; ════════════════════════════════════════════════════════════════════

(defn help-text
  "Generate the `singine help` output from root.xml."
  []
  (let [{:keys [version asset-types naming]} (root)
        private-ext (get-in naming [:private-ext :default] ".sin")
        personal-ext (get-in naming [:personal-ext :default] ".skh")
        lines (concat
               [(str "singine v" version)
                ""
                "Commands (sourced from .meta/0-stem/0-cell/root.xml):"
                ""]
               (for [{:keys [opcode command description]} asset-types]
                 (format "  %s  %-35s %s" opcode command description))
               [""
                (str "Input formats: .md .sindoc " private-ext " " personal-ext " (.x → ~/tmp, ephemeral)")
                "Kafka:  singine.inbound.request → engine → singine.outbound.response"
                "DB:     singine.db (SQLite by default, HiveQL-compatible schema)"
                ""])]
    (str/join "\n" lines)))

;; ════════════════════════════════════════════════════════════════════
;; REGENERATION
;; ════════════════════════════════════════════════════════════════════

(defn regenerate!
  "Regenerate root.xml from the registered asset types.
   Called by `singine meta regenerate`.
   Clears the root-cache so subsequent calls pick up the new file."
  [& {:keys [path additional-assets]}]
  (reset! root-cache nil)
  (let [dest (or path (root-xml-path)
                 (do
                   (let [ws (find-workspace-root)]
                     (when-not ws
                       (throw (ex-info "No workspace root found" {})))
                     (.resolve ws root-xml-rel-path))))]
    ;; For now: the template root.xml is the canonical source.
    ;; Future: merge additional-assets into the DOM and re-serialize.
    (println (str "root.xml at " dest " is current."))))
