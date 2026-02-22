(ns singine.pos.git-op
  "Git Push (GITP opcode) — deploy algorithms from the algorithm registry.

   Algorithm registry (canonical):
     UnionFind       — Disjoint set forest (entity resolution)
     MarkovKernel    — Row-stochastic matrix (Hoffman 6-tuple)
     NashEquilibrium — Game-theory solver (unicode->context)
     SortAlgorithm   — Comparison sort
     SearchAlgorithm — Binary/linear search

   Repo type detection:
     :github           — github.com URLs
     :bitbucket        — bitbucket.org URLs
     :bitbucket-lutino — lutino.io URLs (Bitbucket Server)

   Entry point: push-algorithm! [auth {:algorithm-class :repo-url :branch :work-dir}]
   Returns a zero-arg thunk per govern contract.

   Uses java.lang.ProcessBuilder — no external deps.
   Triple-calendar timestamp in every push result."
  (:require [singine.pos.lambda   :as lam]
            [singine.pos.calendar :as cal]
            [clojure.string       :as str])
  (:import [java.lang ProcessBuilder]
           [java.io BufferedReader InputStreamReader]))

;; ── Algorithm registry ───────────────────────────────────────────────────────

(def algorithm-registry
  "Map of algorithm class name → description."
  {"UnionFind"       "Disjoint set forest — entity resolution via find/union"
   "MarkovKernel"    "Row-stochastic matrix — Hoffman 6-tuple perception/decision/action"
   "NashEquilibrium" "Game-theory solver — Nash equilibrium over payoff matrix"
   "SortAlgorithm"   "Comparison sort — generic ordering over governed sequences"
   "SearchAlgorithm" "Binary/linear search — governed lookup in ordered collections"})

(defn list-algorithms
  "Return the algorithm registry as a sorted vector of {:name :description} maps."
  []
  (mapv (fn [[k v]] {:name k :description v})
        (sort-by key algorithm-registry)))

(defn algorithm-known?
  "True if the algorithm class is in the registry."
  [algorithm-class]
  (contains? algorithm-registry algorithm-class))

;; ── Repo type detection ──────────────────────────────────────────────────────

(defn repo-type
  "Detect the repository type from a URL string.
   Returns :github, :bitbucket-lutino, :bitbucket, or :unknown."
  [repo-url]
  (cond
    (str/includes? (or repo-url "") "lutino.io")       :bitbucket-lutino
    (str/includes? (or repo-url "") "github.com")      :github
    (str/includes? (or repo-url "") "bitbucket.org")   :bitbucket
    :else                                               :unknown))

;; ── ProcessBuilder helpers ───────────────────────────────────────────────────

(defn- run-git!
  "Run a git command via ProcessBuilder in work-dir.
   Returns {:ok :exit-code :stdout :stderr}."
  [work-dir & git-args]
  (let [cmd     (into ["git" "-C" work-dir] git-args)
        pb      (ProcessBuilder. ^java.util.List cmd)
        _       (.redirectErrorStream pb false)
        proc    (.start pb)
        stdout  (with-open [r (BufferedReader. (InputStreamReader. (.getInputStream proc)))]
                  (str/join "\n" (line-seq r)))
        stderr  (with-open [r (BufferedReader. (InputStreamReader. (.getErrorStream proc)))]
                  (str/join "\n" (line-seq r)))
        exit    (.waitFor proc)]
    {:ok        (zero? exit)
     :exit-code exit
     :stdout    stdout
     :stderr    (when-not (str/blank? stderr) stderr)}))

;; ── Commit message ───────────────────────────────────────────────────────────

(defn- commit-message
  "Build a commit message for algorithm deployment with triple-calendar timestamp."
  [algorithm-class cal]
  (let [g   (:gregorian cal)
        iso (:london-iso cal)]
    (str "singine GITP: deploy " algorithm-class
         " at " (:iso g)
         " [" (:sexagenary (:chinese cal)) " " (:animal (:chinese cal)) "]"
         " [" (:year (:persian cal)) "/" (:month (:persian cal)) "/" (:day (:persian cal)) " AP]")))

;; ── push-algorithm! — governed entry point ────────────────────────────────────

(defn push-algorithm!
  "Governed entry point for GITP opcode.
   Selects an algorithm from the registry, commits, and pushes.

   opts map:
     :algorithm-class  — name from algorithm-registry (required)
     :repo-url         — remote URL (optional; used for type detection)
     :branch           — branch to push to (default: 'main')
     :work-dir         — local git repo path (default: current dir)
     :dry-run          — if true, build commit msg but do not git push

   Returns a zero-arg thunk per govern contract.

   Result map:
     {:ok :algorithm-class :repo-type :branch :commit-msg
      :git-add :git-commit :git-push :calendars :time}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [algo     (get opts :algorithm-class "UnionFind")
            repo-url (get opts :repo-url "")
            branch   (get opts :branch "main")
            work-dir (get opts :work-dir (System/getProperty "user.dir"))
            dry-run  (get opts :dry-run false)
            rtype    (repo-type repo-url)
            cal      (cal/london-triple)
            msg      (commit-message algo cal)
            desc     (get algorithm-registry algo "Unknown algorithm")]

        (if-not (algorithm-known? algo)
          {:ok             false
           :error          (str "Unknown algorithm: " algo)
           :available      (list-algorithms)}

          (let [;; git add -A
                add-result  (run-git! work-dir "add" "-A")
                ;; git commit -m "..."
                commit-result (run-git! work-dir "commit" "-m" msg)
                ;; git push origin <branch> (skip if dry-run or no repo-url)
                push-result
                (if (or dry-run (str/blank? repo-url))
                  {:ok true :stdout "dry-run or no repo-url — push skipped" :exit-code 0}
                  (run-git! work-dir "push" "origin" branch))]

            {:ok              (and (:ok add-result) (:ok commit-result) (:ok push-result))
             :algorithm-class algo
             :description     desc
             :repo-type       rtype
             :repo-url        repo-url
             :branch          branch
             :commit-msg      msg
             :dry-run         dry-run
             :git-add         add-result
             :git-commit      commit-result
             :git-push        push-result
             :calendars       cal
             :time            (select-keys t [:iso :path])}))))))
