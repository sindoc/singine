(ns singine.sindoc.parser
  "Clojure bridge to the Java SindocParser.

   The parser is data-driven: its behaviour is configured by .sindoc files
   in the .meta hierarchy. Two paths are consulted:

     1. <workspace-root>/.meta/sindoc.sindoc  — root grammar definition
     2. <project-root>/.meta/parser.sindoc    — project-level overrides

   The Java layer (singine.sindoc.{MetaLoader,SindocParser,SindocDocument})
   handles all file I/O and DOM construction.  This namespace provides:

     - resolve-meta-roots    — locate workspace + project .meta directories
     - make-loader           — instantiate a MetaLoader from resolved paths
     - make-parser           — instantiate a SindocParser from a MetaLoader
     - parse-file            — parse a .sindoc file, return SindocDocument
     - parse-string          — parse a .sindoc string, return SindocDocument
     - to-xml-string         — serialize SindocDocument to XML string
     - document->map         — convert SindocDocument DOM to Clojure map

   The Clojure layer owns path resolution and data transformation.
   The Java layer owns line scanning and DOM construction."
  (:require [clojure.java.io :as io]
            [clojure.string  :as str])
  (:import [singine.sindoc MetaLoader SindocParser SindocDocument]
           [java.nio.file Path Paths]
           [org.w3c.dom Element Node NodeList]))

;; ════════════════════════════════════════════════════════════════════
;; PATH RESOLUTION
;; ════════════════════════════════════════════════════════════════════

(defn- as-path ^Path [x]
  (cond
    (instance? Path x) x
    (instance? java.io.File x) (.toPath ^java.io.File x)
    :else (Paths/get (str x) (into-array String []))))

(defn resolve-meta-roots
  "Walk up the directory tree from `start-dir` to find .meta directories.
   Returns a map:
     {:workspace-root Path   — deepest ancestor with .meta/sindoc.sindoc
      :project-root   Path}  — deepest ancestor with .meta/parser.sindoc

   If only one level is found, both keys point to the same path.
   If neither is found, defaults to the current working directory."
  ([] (resolve-meta-roots (Paths/get (System/getProperty "user.dir")
                                     (into-array String []))))
  ([start-dir]
   (let [start (as-path start-dir)]
     (loop [dir      start
            ws-root  nil
            proj-root nil]
       (let [meta-dir (.resolve dir ".meta")]
         (let [ws   (if (.toFile (.resolve meta-dir "sindoc.sindoc")) ws-root dir)
               proj (if (.toFile (.resolve meta-dir "parser.sindoc"))
                      (if (.exists (.toFile (.resolve meta-dir "parser.sindoc"))) dir proj-root)
                      proj-root)
               ws*  (if (.exists (.toFile (.resolve meta-dir "sindoc.sindoc"))) dir ws-root)
               parent (.getParent dir)]
           (if (or (nil? parent) (= dir parent))
             ;; Reached filesystem root
             {:workspace-root (or ws* start)
              :project-root   (or proj start)}
             (recur parent ws* proj))))))))

;; ════════════════════════════════════════════════════════════════════
;; FACTORY FUNCTIONS
;; ════════════════════════════════════════════════════════════════════

(defn make-loader
  "Create a MetaLoader.

   Options (keyword args):
     :workspace-root  Path|String  — directory containing .meta/sindoc.sindoc
     :project-root    Path|String  — directory containing .meta/parser.sindoc

   If not supplied, roots are resolved by walking up from cwd."
  [& {:keys [workspace-root project-root]}]
  (let [{:keys [workspace-root project-root] :as roots}
        (if (or workspace-root project-root)
          {:workspace-root (as-path (or workspace-root project-root))
           :project-root   (as-path (or project-root workspace-root))}
          (resolve-meta-roots))]
    (MetaLoader. workspace-root project-root)))

(defn make-parser
  "Create a SindocParser from a MetaLoader.
   If no loader is supplied, one is created with default meta root resolution."
  ([]          (SindocParser. (make-loader)))
  ([loader]    (SindocParser. loader))
  ([loader & _] (SindocParser. loader)))

;; ════════════════════════════════════════════════════════════════════
;; PARSING
;; ════════════════════════════════════════════════════════════════════

(defn parse-file
  "Parse a .sindoc file at `path`. Returns a SindocDocument.

   Options:
     :parser    — a SindocParser instance (created if not provided)
     :hint      — source-file hint string"
  [path & {:keys [parser hint]}]
  (let [p  (or parser (make-parser))
        ph (as-path path)]
    (.parse p ph hint)))

(defn parse-string
  "Parse .sindoc content from a string. Returns a SindocDocument.

   Options:
     :parser — a SindocParser instance (created if not provided)
     :hint   — source-file hint string (shown in source-file attribute)"
  [content & {:keys [parser hint]}]
  (let [p (or parser (make-parser))]
    (.parseString p content (or hint "<string>"))))

;; ════════════════════════════════════════════════════════════════════
;; SERIALIZATION
;; ════════════════════════════════════════════════════════════════════

(defn to-xml-string
  "Serialize a SindocDocument to an indented XML string."
  ^String [^SindocDocument doc]
  (.toXmlString doc))

;; ════════════════════════════════════════════════════════════════════
;; DOM → CLOJURE MAP CONVERSION
;; ════════════════════════════════════════════════════════════════════

(declare node->map)

(defn- nodelist->vec [^NodeList nl]
  (mapv node->map
        (for [i (range (.getLength nl))]
          (.item nl i))))

(defn- attrs->map [^Element el]
  (let [attrs (.getAttributes el)]
    (into {}
          (for [i (range (.getLength attrs))]
            (let [attr (.item attrs i)]
              [(keyword (.getNodeName attr)) (.getNodeValue attr)])))))

(defn node->map
  "Convert a DOM Node to a Clojure map:
     {:tag :element-name  :attrs {:key val ...}  :children [...]  :text \"...\"}

   Text nodes are returned as plain strings.
   Comment nodes are skipped (nil)."
  [^Node node]
  (condp = (.getNodeType node)
    Node/ELEMENT_NODE
    (let [el       ^Element node
          children (nodelist->vec (.getChildNodes el))
          content  (filterv some? children)]
      {:tag      (keyword (.getTagName el))
       :attrs    (attrs->map el)
       :children content})

    Node/TEXT_NODE
    (let [text (str/trim (.getNodeValue node))]
      (when-not (str/blank? text) text))

    nil)) ; skip comments, processing instructions, etc.

(defn document->map
  "Convert a SindocDocument to a nested Clojure map.
   Useful for further processing in Clojure without DOM walking."
  [^SindocDocument doc]
  (node->map (.getRoot doc)))
