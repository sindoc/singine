(ns singine.lang.mime
  "Canonical MIME type registry for the Singine platform.

   Provides a single source of truth for file extension → MIME type mapping,
   MIME type routing (:lookup | :link | :binary), and unambiguity checks.

   Design principles:
     · Pure data + pure functions — no imports, no Java, no side effects.
     · Every extension maps to exactly one MIME type (unambiguity rule).
     · Custom singine MIMEs use the vendor tree: application/vnd.singine.* and
       application/vnd.urfm+xml.
     · mime-route replaces the inline routing table in singine.pos.category/mime-route
       (category.clj retains its own copy for backward compat; this is the canonical source).
     · RDF/SPARQL/OWL MIME types always route to :link (semantic graph content).
     · Binary formats (images, archives, PDF, Parquet) route to :binary.
     · All other text/* and application/* route to :lookup.

   Route semantics:
     :lookup  — full-text indexable, Lucene, readable content
     :link    — RDF/graph content, triple store, SPARQL endpoint
     :binary  — opaque binary, archive, image, Parquet — pass-through only
     :unknown — unrecognised MIME type (should not route)")

;; ── Canonical extension → MIME map ───────────────────────────────────────────
;;
;; Keys are lowercase extensions without leading dot.
;; Values are IANA-registered MIME types (or singine vendor types).
;; One extension → one MIME type. No ambiguity.

(def extension->mime
  {"txt"      "text/plain"
   "text"     "text/plain"
   "csv"      "text/csv"
   "tsv"      "text/tab-separated-values"
   "html"     "text/html"
   "htm"      "text/html"
   "md"       "text/markdown"
   "markdown" "text/markdown"
   "xml"      "application/xml"
   "xsl"      "application/xslt+xml"
   "xslt"     "application/xslt+xml"
   "xsd"      "application/xml"
   "dtd"      "application/xml-dtd"
   "rdf"      "application/rdf+xml"
   "owl"      "application/owl+xml"
   "ttl"      "text/turtle"
   "n3"       "text/n3"
   "nt"       "application/n-triples"
   "nq"       "application/n-quads"
   "trig"     "application/trig"
   "jsonld"   "application/ld+json"
   "json"     "application/json"
   "yaml"     "application/yaml"
   "yml"      "application/yaml"
   "toml"     "application/toml"
   "sparql"   "application/sparql-query"
   "srx"      "application/sparql-results+xml"
   "srj"      "application/sparql-results+json"
   "parquet"  "application/x-parquet"
   "avro"     "application/avro"
   "orc"      "application/orc"
   "zip"      "application/zip"
   "tar"      "application/x-tar"
   "gz"       "application/gzip"
   "bz2"      "application/x-bzip2"
   "xz"       "application/x-xz"
   "pdf"      "application/pdf"
   "docx"     "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
   "xlsx"     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
   "pptx"     "application/vnd.openxmlformats-officedocument.presentationml.presentation"
   "png"      "image/png"
   "jpg"      "image/jpeg"
   "jpeg"     "image/jpeg"
   "gif"      "image/gif"
   "svg"      "image/svg+xml"
   "webp"     "image/webp"
   "mp4"      "video/mp4"
   "mp3"      "audio/mpeg"
   ;; Singine vendor MIME types
   "sindoc"   "application/vnd.singine.sindoc+xml"
   "sin"      "application/vnd.singine.sindoc+xml"
   "skh"      "application/vnd.singine.skh+xml"
   "urfm"     "application/vnd.urfm+xml"
   ;; Atom / RSS
   "atom"     "application/atom+xml"
   "rss"      "application/rss+xml"})

;; ── Reverse map: MIME → set of extensions ────────────────────────────────────

(def ^:private mime->ext-set
  (reduce-kv
    (fn [acc ext mime]
      (update acc mime (fnil conj #{}) ext))
    {}
    extension->mime))

;; ── Route table: MIME type → routing keyword ─────────────────────────────────

(def ^:private mime-route-table
  {;; Semantic / graph content → :link
   "application/rdf+xml"                :link
   "application/owl+xml"                :link
   "text/turtle"                        :link
   "text/n3"                            :link
   "application/n-triples"              :link
   "application/n-quads"                :link
   "application/trig"                   :link
   "application/ld+json"                :link
   "application/sparql-query"           :link
   "application/sparql-results+xml"     :link
   "application/sparql-results+json"    :link
   "application/vnd.urfm+xml"           :link
   ;; Binary / archive / image → :binary
   "application/x-parquet"              :binary
   "application/avro"                   :binary
   "application/orc"                    :binary
   "application/zip"                    :binary
   "application/x-tar"                  :binary
   "application/gzip"                   :binary
   "application/x-bzip2"                :binary
   "application/x-xz"                   :binary
   "application/pdf"                    :binary
   "application/vnd.openxmlformats-officedocument.wordprocessingml.document" :binary
   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"       :binary
   "application/vnd.openxmlformats-officedocument.presentationml.presentation" :binary
   "image/png"                          :binary
   "image/jpeg"                         :binary
   "image/gif"                          :binary
   "image/svg+xml"                      :binary
   "image/webp"                         :binary
   "video/mp4"                          :binary
   "audio/mpeg"                         :binary
   ;; Lookup (text / structured) → :lookup
   "text/plain"                         :lookup
   "text/csv"                           :lookup
   "text/tab-separated-values"          :lookup
   "text/html"                          :lookup
   "text/markdown"                      :lookup
   "application/xml"                    :lookup
   "application/xml-dtd"                :lookup
   "application/xslt+xml"               :lookup
   "application/json"                   :lookup
   "application/yaml"                   :lookup
   "application/toml"                   :lookup
   "application/atom+xml"               :lookup
   "application/rss+xml"                :lookup
   "application/vnd.singine.sindoc+xml" :lookup
   "application/vnd.singine.skh+xml"    :lookup})

;; ── Public API ───────────────────────────────────────────────────────────────

(defn lookup
  "Return the canonical MIME type for a file extension (without leading dot).
   Extension comparison is case-insensitive.
   Falls back to \\\"application/octet-stream\\\" for unknown extensions."
  [ext]
  (or (get extension->mime (clojure.string/lower-case (or ext "")))
      "application/octet-stream"))

(defn route
  "Classify a MIME type string into a routing keyword.
   Returns :lookup | :link | :binary | :unknown.

   :lookup  — full-text indexable (text/*, application/json, application/xml ...)
   :link    — RDF/graph content (application/rdf+xml, text/turtle, ...)
   :binary  — opaque binary (application/zip, image/png, application/x-parquet ...)
   :unknown — not recognised"
  [mime-type]
  (or (get mime-route-table (or mime-type ""))
      (cond
        (clojure.string/starts-with? (or mime-type "") "text/")
        :lookup
        (clojure.string/starts-with? (or mime-type "") "application/")
        :lookup
        :else :unknown)))

(defn unambiguous?
  "Returns true if the extension maps to exactly one MIME type in the registry.
   An extension is ambiguous if multiple entries (with different casings or aliases)
   would resolve it to different types — which cannot happen in this closed map."
  [ext]
  (boolean (get extension->mime (clojure.string/lower-case (or ext "")))))

(defn extensions-for
  "Return the set of extensions that map to the given MIME type.
   Returns an empty set if the MIME type is not in the registry."
  [mime-type]
  (get mime->ext-set (or mime-type "") #{}))

(defn mime-for-path
  "Return the MIME type for a file path by extracting the extension.
   E.g. (mime-for-path \\\"foo/bar.rdf\\\") → \\\"application/rdf+xml\\\"."
  [path]
  (let [dot-idx (clojure.string/last-index-of (or path "") ".")]
    (if (and dot-idx (> dot-idx 0))
      (lookup (subs path (inc dot-idx)))
      "application/octet-stream")))

(defn content-type
  "Return a Content-Type header value including charset for text types.
   E.g. (content-type \\\"text/plain\\\") → \\\"text/plain; charset=UTF-8\\\"."
  [mime-type]
  (let [m (or mime-type "application/octet-stream")]
    (if (clojure.string/starts-with? m "text/")
      (str m "; charset=UTF-8")
      m)))
