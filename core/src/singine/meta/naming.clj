(ns singine.meta.naming
  "Naming convention checks for singine files and identifiers.

   All conventions are expressed as regex patterns (Chomsky type-3 — no
   grammar layers above regular languages). The patterns are loaded from
   root.xml so they are configurable without code changes.

   The sed/awk equivalents are documented alongside each function so the
   logic is always auditable at shell level."
  (:require [singine.meta.root :as root]
            [clojure.string    :as str])
  (:import [java.util.regex Pattern]))

;; ════════════════════════════════════════════════════════════════════
;; PATTERN CACHE
;; ════════════════════════════════════════════════════════════════════

(defn- pattern-for
  "Return the compiled java.util.regex.Pattern for a naming convention.
   Reads from root.xml naming map, falls back to built-in defaults."
  [convention-name]
  (let [naming (root/naming)
        entry  (get naming (keyword convention-name))
        regex  (or (:regex entry) (:value entry)
                   (case (keyword convention-name)
                     :private-ext  "\\.[a-z]{3}$"
                     :personal-ext "\\.[a-z]{2,4}$"
                     :temp-ext     "\\.x$"
                     :public-ext   "\\.sindoc$"
                     :opcode       "[A-Z]{4}"
                     :cell-dir     "(^|/)\\.(meta)($|/)"
                     nil))]
    (when regex (Pattern/compile regex))))

;; ════════════════════════════════════════════════════════════════════
;; CORE MATCHING
;; ════════════════════════════════════════════════════════════════════

(defn matches-convention?
  "Return true if filename matches the named convention.

   sed equivalent:
     echo '<filename>' | sed -n '/<regex>/p'

   Example:
     (matches-convention? :private-ext \"myfile.sin\")  → true
     (matches-convention? :opcode      \"CHKX\")         → true"
  [convention-name ^String s]
  (when-let [p (pattern-for convention-name)]
    (boolean (re-find p s))))

(defn convention-regex
  "Return the raw regex string for a convention (for display / sed use).

   awk equivalent:
     echo '<opcode>:<name>' | awk -F: '{print $1}' | grep -P '<regex>'

   Example:
     (convention-regex :opcode)  → \"[A-Z]{4}\""
  [convention-name]
  (let [naming (root/naming)
        entry  (get naming (keyword convention-name))]
    (or (:regex entry) (:value entry))))

;; ════════════════════════════════════════════════════════════════════
;; FILE TYPE DETECTION
;; ════════════════════════════════════════════════════════════════════

(defn file-type
  "Detect the singine file type of a filename.
   Returns one of: :sindoc :sin :skh :temp :markdown :unknown.

   Detection order:
     1. .x extension           → :temp   (always local, goes to ~/tmp)
     2. #lang line in content   → :sindoc (any .sin/.skh with #lang is sindoc)
     3. .sindoc extension       → :sindoc
     4. private-ext pattern     → :sin
     5. personal-ext pattern    → :skh
     6. .md extension           → :markdown
     7. otherwise               → :unknown"
  ([filename]
   (cond
     (matches-convention? :temp-ext filename)    :temp
     (matches-convention? :public-ext filename)  :sindoc
     (matches-convention? :private-ext filename) :sin
     (matches-convention? :personal-ext filename):skh
     (str/ends-with? filename ".md")             :markdown
     :else                                        :unknown))
  ([filename first-line]
   ;; If the first line is a #lang directive, it is always sindoc-family
   (if (and first-line (str/starts-with? (str/trim first-line) "#lang"))
     :sindoc
     (file-type filename))))

(defn temp-path
  "Return the ~/tmp path for a temp (.x) file, creating ~/tmp if needed.
   The .x file is never stored in its original location; it is moved here."
  [filename]
  (let [home (System/getProperty "user.home")
        tmp  (str home "/tmp")]
    (java.io.File. tmp (.getName (java.io.File. filename)))))

;; ════════════════════════════════════════════════════════════════════
;; OPCODE UTILITIES
;; ════════════════════════════════════════════════════════════════════

(defn valid-opcode?
  "True if s is a valid 4-letter uppercase opcode.

   awk equivalent:
     echo 'CHKX' | awk '/^[A-Z]{4}$/{print \"valid\"}'

   Example:
     (valid-opcode? \"CHKX\")  → true
     (valid-opcode? \"chkx\")  → false"
  [^String s]
  (matches-convention? :opcode s))

(defn extract-opcode
  "Extract the opcode from a string of the form 'OPCD:Name...' or just 'OPCD'.
   Returns the 4-letter opcode string, or nil.

   awk equivalent:
     echo 'CHKX:ExtensionCheck' | awk -F: '{print $1}'"
  [^String s]
  (when s
    (let [candidate (first (str/split s #":"))]
      (when (valid-opcode? candidate) candidate))))
