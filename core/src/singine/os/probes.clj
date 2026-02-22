(ns singine.os.probes
  "The 12 canonical OS probes for file extension conflict detection.
   Each probe tests one dimension: toolchain, editor, MIME, build, VCS, linker, magic.
   Probes are defined with the defprobe macro and registered in probe-registry."
  (:require [clojure.string :as str]))

(def probe-registry
  "Atom: map of probe-id (int) → probe map. Populated by defprobe."
  (atom {}))

(defmacro defprobe
  "Define a named probe and register it.
   Keys: :id (int), :dimension (keyword), :cmd (string template),
         :severity (fn [out err exit-code] → :none|:low|:moderate|:severe),
         :finding  (fn [out err exit-code] → string)"
  [probe-name & {:keys [id dimension cmd severity finding]}]
  `(do
     (def ~probe-name
       {:id          ~id
        :name        ~(str probe-name)
        :dimension   ~dimension
        :command-tpl ~cmd
        :severity-fn ~severity
        :finding-fn  ~finding})
     (swap! probe-registry assoc ~id ~probe-name)
     ~probe-name))

(defn interpolate-command
  "Replace {ext} with ext (e.g. '.xyz') and {ext-bare} with the bare
   extension (e.g. 'xyz') in a command template."
  [cmd-template ^String ext]
  (let [bare (if (str/starts-with? ext ".") (subs ext 1) ext)]
    (-> cmd-template
        (str/replace "{ext}" ext)
        (str/replace "{ext-bare}" bare))))

;; Define all 12 probes using defprobe:

(defprobe sdk-static-lib
  :id        1
  :dimension :toolchain
  :cmd       "ls /Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/lib/*.{ext-bare} 2>/dev/null | head -10"
  :severity  (fn [out _ _] (if (str/blank? out) :none :severe))
  :finding   (fn [out _ _]
               (if (str/blank? out)
                 "No SDK static libraries with this extension."
                 (str "SDK libraries found:\n" (str/trim out)))))

(defprobe ar-man-page
  :id        2
  :dimension :toolchain
  :cmd       "man ar 2>/dev/null | head -30"
  :severity  (fn [_ _ _] :none)
  :finding   (fn [_ _ _] "Reference only: ar man page captured."))

(defprobe ar-reject-test
  :id        3
  :dimension :toolchain
  :cmd       "echo \"test\" > /tmp/sample.{ext} && ar t /tmp/sample.{ext} 2>&1; rm -f /tmp/sample.{ext}"
  :severity  (fn [out _ _]
               (cond
                 (re-find #"(?i)Inappropriate|not.*archive|ARMAG|malformed" out) :moderate
                 (re-find #"(?i)error|cannot" out) :low
                 :else :none))
  :finding   (fn [out _ _]
               (if (re-find #"(?i)Inappropriate|not.*archive|ARMAG" out)
                 "ar treats this extension as a potential archive format."
                 "ar correctly rejects plain-text content with this extension.")))

(defprobe vim-filetype
  :id        4
  :dimension :editor
  :cmd       "grep -n '\\.{ext-bare}' /usr/share/vim/vim91/filetype.vim 2>/dev/null | head -20"
  :severity  (fn [out _ _] (if (str/blank? out) :none :moderate))
  :finding   (fn [out _ _]
               (if (str/blank? out)
                 "No Vim filetype rule for this extension."
                 (str "Vim filetype rules found:\n" (str/trim out)))))

(defprobe vim-asm-mapping
  :id        5
  :dimension :editor
  :cmd       "grep -r '\\.{ext-bare}' /usr/share/vim/vim91/filetype.vim 2>/dev/null | grep -i 'asm\\|assem' | head -10"
  :severity  (fn [out _ _] (if (str/blank? out) :none :severe))
  :finding   (fn [out _ _]
               (if (str/blank? out)
                 "No Vim assembly mapping for this extension."
                 (str "Extension mapped to assembly in Vim:\n" (str/trim out)))))

(defprobe mime-type
  :id        6
  :dimension :mime
  :cmd       "cat /etc/mime.types 2>/dev/null | grep '\\.{ext-bare}' | head -10 || echo \"no /etc/mime.types\""
  :severity  (fn [out _ _]
               (cond
                 (re-find #"no /etc/mime.types" out) :none
                 (str/blank? out)                     :none
                 :else                                :moderate))
  :finding   (fn [out _ _]
               (cond
                 (re-find #"no /etc/mime.types" out) "MIME database unavailable on this OS."
                 (str/blank? out)                     "No registered MIME type for this extension."
                 :else                                (str "Registered MIME type: " (str/trim out)))))

(defprobe spotlight-uttype
  :id        7
  :dimension :os-registry
  :cmd       "echo '' > /tmp/probe.{ext} && mdls -name kMDItemContentType /tmp/probe.{ext} 2>/dev/null | head -5; rm -f /tmp/probe.{ext}"
  :severity  (fn [out _ _]
               (cond
                 (or (str/blank? out)
                     (re-find #"(?i)null|could not|No such" out)) :none
                 :else :moderate))
  :finding   (fn [out _ _]
               (if (or (str/blank? out)
                       (re-find #"(?i)null|could not|No such" out))
                 "No Spotlight UTType registered for this extension."
                 (str "Spotlight UTType: " (str/trim out)))))

(defprobe make-suffix
  :id        8
  :dimension :build
  :cmd       "make --print-data-base 2>/dev/null | grep '\\.{ext-bare}' | head -20"
  :severity  (fn [out _ _] (if (str/blank? out) :none :moderate))
  :finding   (fn [out _ _]
               (if (str/blank? out)
                 "No GNU Make suffix rule for this extension."
                 (str "Make suffix rules:\n" (str/trim out)))))

(defprobe gitignore-c
  :id        9
  :dimension :vcs
  :cmd       "curl -s --max-time 5 https://raw.githubusercontent.com/github/gitignore/main/C.gitignore 2>/dev/null | grep '\\.{ext-bare}' | head -10 || echo \"\""
  :severity  (fn [out _ _] (if (str/blank? out) :none :low))
  :finding   (fn [out _ _]
               (if (str/blank? out)
                 "Not found in GitHub C.gitignore."
                 (str "Found in C.gitignore: " (str/trim out)))))

(defprobe ld-recognition
  :id        10
  :dimension :linker
  :cmd       "ld --help 2>&1 | grep '\\.{ext-bare}' | head -10"
  :severity  (fn [out _ _] (if (str/blank? out) :none :severe))
  :finding   (fn [out _ _]
               (if (str/blank? out)
                 "Linker does not recognise this extension."
                 (str "Linker recognises extension:\n" (str/trim out)))))

(defprobe file-magic-empty
  :id        11
  :dimension :magic
  :cmd       "file /tmp/test_plain.{ext} 2>/dev/null"
  :severity  (fn [out _ _]
               (cond
                 (re-find #"(?i)No such"  out)                   :none
                 (re-find #"(?i)assembler|archive|elf|exec" out) :severe
                 :else                                            :none))
  :finding   (fn [out _ _]
               (str "file(1) on non-existent path: " (str/trim out))))

(defprobe file-magic-content
  :id        12
  :dimension :magic
  :cmd       "echo \"hello world\" > /tmp/test_plain.{ext} && file /tmp/test_plain.{ext}; rm -f /tmp/test_plain.{ext}"
  :severity  (fn [out _ _]
               (cond
                 (re-find #"(?i)assembler|archive|elf|exec" out) :severe
                 (re-find #"ASCII|text"  out)                    :none
                 :else                                            :low))
  :finding   (fn [out _ _]
               (str "file(1) with plain-text content: " (str/trim out))))

(def canonical-probes
  "All 12 probes in id order. Derived from probe-registry at load time."
  (mapv (fn [id] (get @probe-registry id))
        (sort (keys @probe-registry))))

(defn probe-by-id [id] (get @probe-registry id))
