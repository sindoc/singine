(ns singine.lang.dispatch
  "The #lang dispatcher for singine documents.
   Opcode: LANG   URN: urn:singine:asset:LANG

   Rule (applied to every file entering the pipeline):
     1. Read the first line.
     2. If it matches #lang <tokens>, parse tokens.
     3. Route to each runtime in order (multi-lang: all evaluated).
     4. Collect results as a Clojure seq.
     5. Emit as XML (<?lang token?> processing instruction preserved).

   Supported tokens (from lang-registry in root.xml):
     racket    → singine.lang.racket/evaluate!
     sindoc    → singine.lang.singine/evaluate!
     xml       → singine.lang.xml/evaluate!
     multi     → all tokens evaluated in sequence
     clojure   → singine.lang.clojure/evaluate!
     sparql    → singine.lang.sparql/evaluate!

   Multi-lang (#lang a, b, c, singine):
     Each comma-separated token is evaluated against the same document body.
     Results are collected as {:token result} maps.

   XML preservation:
     Every #lang declaration is preserved as a processing instruction
     in the generated XML: <?lang racket?>
     This means the whole document is always XML-translatable."
  (:require [clojure.string :as str]))

;; ── lang line parser ─────────────────────────────────────────────────────────

(defn parse-lang-line
  "Parse a #lang declaration line.
   Returns {:tokens [\"racket\"] :multi? false} or
           {:tokens [\"a\" \"b\" \"c\" \"singine\"] :multi? true}
   Returns nil if not a #lang line."
  [^String line]
  (let [trimmed (str/trim line)]
    (when (str/starts-with? trimmed "#lang")
      (let [rest    (str/trim (subs trimmed 5))
            tokens  (->> (str/split rest #"[,\s]+")
                         (map str/trim)
                         (remove empty?))]
        {:tokens tokens
         :multi? (> (count tokens) 1)}))))

;; ── runtime registry ─────────────────────────────────────────────────────────
;; Each entry: token → (fn [body opts] -> result)
;; Stubs return a map describing what the real handler would do.

(def ^:private runtimes
  {"racket"
   (fn [body opts]
     {:runtime :racket
      :handler "singine.lang.racket/evaluate!"
      :body-length (count body)
      :pi "<?lang racket?>"
      :note "Racket subprocess or GraalVM. Full #lang racket semantics."
      :opts opts})

   "sindoc"
   (fn [body opts]
     {:runtime :sindoc
      :handler "singine.lang.singine/evaluate!"
      :body-length (count body)
      :pi "<?lang singine?>"
      :note "Native sindoc parser → XML. Schema: singine.dtd."
      :opts opts})

   "xml"
   (fn [body opts]
     {:runtime :xml
      :handler "singine.lang.xml/evaluate!"
      :body-length (count body)
      :pi "<?lang xml?>"
      :note "Validate against singine.dtd + singine.rnc."
      :opts opts})

   "clojure"
   (fn [body opts]
     {:runtime :clojure
      :handler "singine.lang.clojure/evaluate!"
      :body-length (count body)
      :pi "<?lang clojure?>"
      :note "Clojure expression evaluated on JVM. Result is Clojure data."
      :opts opts})

   "sparql"
   (fn [body opts]
     {:runtime :sparql
      :handler "singine.lang.sparql/evaluate!"
      :body-length (count body)
      :pi "<?lang sparql?>"
      :note "SPARQL query → Jena ARQ → result bindings."
      :opts opts})})

(defn- default-runtime [token]
  (fn [body opts]
    {:runtime :unknown
     :token   token
     :body-length (count body)
     :pi (str "<?lang " token "?>")
     :note (str "No handler registered for #lang " token)
     :opts opts}))

;; ── route! ───────────────────────────────────────────────────────────────────

(defn route!
  "Route a document body to the correct runtime(s) based on lang-tokens.

   Arguments:
     tokens — seq of lang token strings (from parse-lang-line)
     body   — the document body (string, after the #lang header)
     opts   — arbitrary map passed to the runtime handler

   Returns:
     Single token  → result map
     Multiple tokens → {:multi true :results {:token result ...}}"
  [tokens body & [opts]]
  (if (= 1 (count tokens))
    (let [token   (first tokens)
          handler (get runtimes token (default-runtime token))]
      (handler body (or opts {})))
    {:multi   true
     :tokens  tokens
     :results (into {}
                    (map (fn [token]
                           (let [h (get runtimes token (default-runtime token))]
                             [token (h body (or opts {}))]))
                         tokens))}))

(defn dispatch-file!
  "Dispatch a full file (string) through the #lang router.
   Reads the first line for the #lang declaration.
   Returns {:lang-info :body :result} or {:error :no-lang} if no #lang."
  [^String content & [opts]]
  (let [lines    (str/split-lines content)
        first-ln (first lines)
        lang-info (when first-ln (parse-lang-line first-ln))]
    (if lang-info
      (let [body (str/join "\n" (rest lines))]
        {:lang-info lang-info
         :body      body
         :result    (route! (:tokens lang-info) body opts)})
      {:error   :no-lang
       :first-line first-ln
       :note    "No #lang declaration found. File treated as plain text."})))
