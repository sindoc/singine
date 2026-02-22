(ns singine.os.verdict
  "Severity aggregation and verdict text for extension checks.")

(def severity-rank {:none 0 :low 1 :moderate 2 :severe 3})

(defn severity>=  [a b] (>= (severity-rank a 0) (severity-rank b 0)))
(defn severity>   [a b] (>  (severity-rank a 0) (severity-rank b 0)))

(defn overall-severity
  "Maximum severity across a collection of severity keywords."
  [severities]
  (reduce (fn [acc s] (if (severity> s acc) s acc))
          :none severities))

(defn verdict-text
  "Human-readable overall verdict."
  [^String ext overall]
  (case overall
    :none     (str "No conflicts detected for " ext ". Safe to use.")
    :low      (str ext " has minor advisory conflicts (e.g. VCS ignore patterns). Review recommended.")
    :moderate (str ext " conflicts with editor or build tooling. Consider an alternative.")
    :severe   (str ext " conflicts severely with OS toolchain (linker, compiler, or editor). Do not use.")))

(defn- col
  "Left-pad or right-pad a string to width w."
  [s w pad-right?]
  (let [s (str s)
        n (count s)]
    (if pad-right?
      (str s (apply str (repeat (max 0 (- w n)) " ")))
      (str (apply str (repeat (max 0 (- w n)) " ")) s))))

(defn summary-table
  "Build a plain-text ASCII summary table for all probe results.
   probe-results: seq of maps with :probe-id :name :dimension :severity :finding"
  [^String ext probe-results]
  (let [header   (str "Extension conflict report for: " ext)
        divider  (apply str (repeat 72 "─"))
        head-row (str (col "ID" 3 true) " "
                      (col "Name" 22 true) " "
                      (col "Dimension" 12 true) " "
                      (col "Severity" 9 true) " Finding")
        rows (for [{:keys [probe-id name dimension severity finding]} probe-results]
               (str (col probe-id 3 true) " "
                    (col name 22 true) " "
                    (col (clojure.core/name dimension) 12 true) " "
                    (col (clojure.core/name severity) 9 true) " "
                    (first (clojure.string/split-lines (str finding)))))]
    (clojure.string/join "\n"
      (concat [header divider head-row divider] rows [divider]))))
