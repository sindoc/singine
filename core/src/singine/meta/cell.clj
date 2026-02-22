(ns singine.meta.cell
  "Meta Cell (MCEL opcode) — wire .meta/ in the current execution directory.

   Creates in the CWD (or supplied dir):
     .meta/
       cell.sindoc     — #lang sindoc, @London ISO 8601, #Tag <dir-name>, [[t/1]]
       manifest.json   — {cell, root-xml-ref, timestamp, calendars, topic}
       root-ref.txt    — relative path back to .meta/0-stem/0-cell/root.xml

   #Tag is replaced by the CWD directory name (e.g. 'today' for /Users/skh/ws/today).

   Non-destructive: does not overwrite existing files.
   Uses Europe/London for all timestamps."
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [singine.meta.root    :as root]
            [clojure.data.json    :as json]
            [clojure.java.io      :as io]
            [clojure.string       :as str])
  (:import [java.time ZonedDateTime ZoneId]
           [java.time.format DateTimeFormatter]
           [java.nio.file Path Paths Files]
           [java.io File]))

;; ── London timestamp ─────────────────────────────────────────────────────────

(defn- london-iso
  "Return current Europe/London time as ISO 8601 offset string."
  []
  (.format (ZonedDateTime/now (ZoneId/of "Europe/London"))
           DateTimeFormatter/ISO_OFFSET_DATE_TIME))

;; ── Root-ref: relative path from cwd/.meta/ back to workspace root.xml ───────

(defn- root-ref-path
  "Compute a relative path from cwd-meta-dir to the workspace root.xml.
   Falls back to the absolute path if relative resolution fails."
  [^Path cwd-meta-dir]
  (let [ws-root (root/find-workspace-root)]
    (if ws-root
      (let [root-xml (.resolve ws-root ".meta/0-stem/0-cell/root.xml")]
        (try
          (str (.relativize cwd-meta-dir root-xml))
          (catch Exception _
            (str root-xml))))
      "../../.meta/0-stem/0-cell/root.xml")))

;; ── Cell sindoc content ──────────────────────────────────────────────────────

(defn- cell-sindoc
  "Generate the cell.sindoc content for a directory named dir-name."
  [dir-name iso-ts]
  (str "#lang sindoc\n"
       "#tag " dir-name "\n"
       "@London " iso-ts "\n"
       "--\n"
       "[[t/1]]\n"
       "urn:singine:topic:t/1\n"
       "\n"
       "Meta cell for: " dir-name "\n"
       "Wired by: singine MCEL\n"
       "</>"))

;; ── write-if-absent: non-destructive file write ───────────────────────────────

(defn- write-if-absent!
  "Write content to path only if the file does not exist.
   Returns {:wrote true :path p} or {:wrote false :path p}."
  [^Path p content]
  (let [f (.toFile p)]
    (if (.exists f)
      {:wrote false :path (str p)}
      (do
        (io/make-parents f)
        (spit f content)
        {:wrote true :path (str p)}))))

;; ── wire-cwd! — governed entry point ─────────────────────────────────────────

(defn wire-cwd!
  "Governed entry point for MCEL opcode.
   Creates .meta/ structure in exec-dir (default: current working directory).
   Non-destructive — will not overwrite existing files.

   Returns a zero-arg thunk per govern contract.

   Result map:
     {:ok :exec-dir :dir-name :wrote [:cell-sindoc :manifest-json :root-ref-txt]
      :calendars :time}"
  ([auth]
   (wire-cwd! auth (System/getProperty "user.dir")))
  ([auth exec-dir]
   (lam/govern auth
     (fn [t]
       (let [exec-path  (Paths/get exec-dir (into-array String []))
             dir-name   (.getFileName exec-path)
             dir-name   (if dir-name (str dir-name) "singine")
             meta-dir   (.resolve exec-path ".meta")
             iso-ts     (london-iso)
             cal        (cal/london-triple)
             ws-root    (root/find-workspace-root)

             ;; cell.sindoc
             sindoc-path (.resolve meta-dir "cell.sindoc")
             sindoc-result (write-if-absent! sindoc-path (cell-sindoc dir-name iso-ts))

             ;; manifest.json
             manifest-path (.resolve meta-dir "manifest.json")
             manifest-content
             (json/write-str
               {:cell          dir-name
                :root-xml-ref  (root-ref-path meta-dir)
                :timestamp     iso-ts
                :calendars     {:gregorian (select-keys (:gregorian cal) [:year :month :day :iso])
                                :persian   (select-keys (:persian cal)   [:year :month :day])
                                :chinese   (select-keys (:chinese cal)   [:sexagenary :animal])}
                :topic         "[[t/1]]"
                :urn           "urn:singine:topic:t/1"
                :generator     "singine.meta.cell/wire-cwd!"
                :lang          "#lang sindoc"})
             manifest-result (write-if-absent! manifest-path manifest-content)

             ;; root-ref.txt
             root-ref-path-file (.resolve meta-dir "root-ref.txt")
             root-ref-content  (str (root-ref-path meta-dir) "\n")
             root-ref-result   (write-if-absent! root-ref-path-file root-ref-content)]

         {:ok          true
          :exec-dir    exec-dir
          :dir-name    dir-name
          :wrote       {:cell-sindoc   sindoc-result
                        :manifest-json manifest-result
                        :root-ref-txt  root-ref-result}
          :calendars   cal
          :time        (select-keys t [:iso :path])})))))
