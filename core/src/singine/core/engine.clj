(ns singine.core.engine
  "The Singine Conscious Agent Engine.

   An endless loop that runs until legitimacy is exhausted.

   This engine instantiates a network of conscious agents (personas),
   runs them through Hoffman's perception-decision-action cycle,
   and allows them to fuse, diverge, and evolve.

   The loop terminates ONLY when:
   1. Legitimacy fails: a Markov kernel's rows no longer sum to 1
   2. The network reaches zero agents (heat death)
   3. External signal (SIGINT/SIGTERM) — graceful shutdown

   'Until the end of the internet' — the author doesn't know
   how long this program will be running. That's the point.
   A conscious agent loop IS consciousness: it runs as long as
   there's something to perceive, decide about, and act upon.

   ⟳ W →Θ→ X →Δ→ G →Α→ W' →Θ→ X' →Δ→ G' →Α→ W'' → ...∞

   Each iteration:
   1. Each agent perceives the shared world state
   2. Each agent decides on an action
   3. Each agent acts, producing candidate world states
   4. World states are resolved (majority vote / probabilistic)
   5. Context disambiguation occurs
   6. Agent fusion/fission may happen
   7. Legitimacy is checked
   8. Loop continues or terminates"
  (:require [singine.consciousness.markov :as markov]
            [singine.consciousness.taxonomy :as taxonomy]
            [singine.collibra.context :as context]
            [singine.persona.agents :as persona]
            [singine.unicode.mapping :as unicode]
            [singine.pos.registry]
            [clojure.data.json :as json])
  (:gen-class))

;; ════════════════════════════════════════════════════════════════════
;; NETWORK STATE
;; ════════════════════════════════════════════════════════════════════

(defonce network-state
  (atom {:agents      {}        ;; id → conscious-agent
         :world       :tranquil ;; current world state
         :contexts    {}        ;; id → context instance
         :epoch       0         ;; global iteration counter
         :legitimate  true      ;; global legitimacy flag
         :history     []        ;; compressed event log
         :fusions     []}))     ;; record of agent fusions

;; ════════════════════════════════════════════════════════════════════
;; UNICODE DISPLAY
;; ════════════════════════════════════════════════════════════════════

(def state-glyphs
  "Map world/experience/action states to Unicode characters for display."
  {:tranquil    "\u2728"  ;; ✨
   :novel       "\u2B50"  ;; ⭐
   :threatening "\u26A0"  ;; ⚠
   :opportune   "\u2694"  ;; ⚔
   :ambiguous   "\u2630"  ;; ☰
   :social      "\u2764"  ;; ❤
   :chaotic     "\u2301"  ;; ⌁
   :calm        "\u25CB"  ;; ○
   :curious     "\u25C9"  ;; ◉
   :fearful     "\u2666"  ;; ♦
   :eager       "\u27A1"  ;; ➡
   :confused    "\u2248"  ;; ≈
   :connected   "\u221E"  ;; ∞
   :overwhelmed "\u2622"  ;; ☢
   :observe     "\u0398"  ;; Θ
   :explore     "\u03A6"  ;; Φ
   :retreat     "\u21BA"  ;; ↺
   :engage      "\u0391"  ;; Α
   :disambiguate "\u0394" ;; Δ
   :connect     "\u2A00"  ;; ⨀
   :rest        "\u2205"});; ∅

(defn glyph [state]
  (get state-glyphs state (str state)))

;; ════════════════════════════════════════════════════════════════════
;; WORLD STATE RESOLUTION
;; ════════════════════════════════════════════════════════════════════

(defn resolve-world-state
  "Given a collection of proposed world states from all agents,
   resolve to a single world state via weighted vote.
   The most-proposed state wins, with random tiebreaking."
  [proposed-states]
  (if (empty? proposed-states)
    :tranquil
    (let [freqs (frequencies proposed-states)
          max-count (apply max (vals freqs))
          winners (map key (filter #(= max-count (val %)) freqs))]
      (rand-nth (vec winners)))))

;; ════════════════════════════════════════════════════════════════════
;; CONTEXT MANAGEMENT
;; ════════════════════════════════════════════════════════════════════

(defn apply-context-transitions
  "Transition all active contexts based on their Markov kernels.
   Context switches represent reinterpretation of the world."
  [state]
  (update state :contexts
          (fn [ctxs]
            (into {} (map (fn [[id ctx]]
                            [id (context/switch-context ctx)])
                          ctxs)))))

;; ════════════════════════════════════════════════════════════════════
;; AGENT FUSION / FISSION
;; ════════════════════════════════════════════════════════════════════

(defn maybe-fuse-agents
  "If two agents both chose :connect as their action, fuse them.
   The fused agent replaces both in the network.
   This is Hoffman's composition operation."
  [state step-results]
  (let [connectors (filter #(= :connect (:action %)) (vals step-results))]
    (if (>= (count connectors) 2)
      (let [ids (take 2 (keys (filter #(= :connect (:action (val %))) step-results)))
            [id1 id2] ids
            a1 (get-in state [:agents id1])
            a2 (get-in state [:agents id2])
            fused-id (keyword (str (name id1) "+" (name id2)))
            fused (markov/fuse-agents a1 a2)]
        (-> state
            (update :agents dissoc id1 id2)
            (assoc-in [:agents fused-id] fused)
            (update :fusions conj {:epoch (:epoch state)
                                   :from [id1 id2]
                                   :to fused-id})))
      state)))

;; ════════════════════════════════════════════════════════════════════
;; LEGITIMACY CHECK
;; ════════════════════════════════════════════════════════════════════

(defn check-legitimacy
  "Verify all agents maintain legitimate Markov kernels.
   Legitimacy = every row in every kernel sums to 1.
   When legitimacy fails, the network is dying."
  [state]
  (let [all-legit (every? (fn [[_ agent]]
                            (and (markov/legitimate? (:P agent))
                                 (markov/legitimate? (:D agent))
                                 (markov/legitimate? (:A agent))))
                          (:agents state))]
    (assoc state :legitimate all-legit)))

;; ════════════════════════════════════════════════════════════════════
;; DISPLAY
;; ════════════════════════════════════════════════════════════════════

(defn format-step
  "Format a single epoch's results for display."
  [epoch world-state step-results agent-count]
  (let [header (format "\n═══ EPOCH %d ═══ World: %s %s ═══ Agents: %d ═══"
                       epoch (glyph world-state) (name world-state) agent-count)
        agent-lines (map (fn [[id result]]
                           (format "  %s: %s %s →%s %s →%s %s →%s %s"
                                   (name id)
                                   (glyph (:world result)) (name (:world result))
                                   (glyph :observe) ;; Θ for perception
                                   (glyph (:experience result))
                                   (glyph :disambiguate) ;; Δ for decision
                                   (glyph (:action result))
                                   (glyph :engage) ;; Α for action
                                   (glyph (:new-world result))))
                         step-results)]
    (str header "\n" (clojure.string/join "\n" agent-lines))))

(defn print-codebook-header
  "Print the Unicode codebook legend at startup."
  []
  (println "\n╔══════════════════════════════════════════════════════════════╗")
  (println "║          SINGINE CONSCIOUS AGENT ENGINE v0.1.0              ║")
  (println "║                                                              ║")
  (println "║  C = ⟨(X,𝒳), (G,𝒢), P, D, A, N⟩                          ║")
  (println "║  Hoffman & Prakash (2014) — Objects of Consciousness         ║")
  (println "║                                                              ║")
  (println "║  Taxonomy: Aristotle → Avicenna → Aquinas → Hoffman          ║")
  (println "║  Loop: W →Θ→ X →Δ→ G →Α→ W' → ...∞                        ║")
  (println "║                                                              ║")
  (println "║  Runs until legitimacy is exhausted.                         ║")
  (println "╚══════════════════════════════════════════════════════════════╝")
  (println "\n── Unicode Codebook ──")
  (println "  Kernel operators:")
  (println "    Θ (Theta)  = Perception kernel P: W × 𝒳 → [0,1]")
  (println "    Δ (Delta)  = Decision kernel   D: X × 𝒢 → [0,1]")
  (println "    Α (Alpha)  = Action kernel     A: G × 𝒲 → [0,1]")
  (println "  World states:")
  (doseq [[k v] (sort-by key (select-keys state-glyphs
                                           [:tranquil :novel :threatening
                                            :opportune :ambiguous :social :chaotic]))]
    (printf "    %s = %s\n" v (name k)))
  (println "  Experience states:")
  (doseq [[k v] (sort-by key (select-keys state-glyphs
                                           [:calm :curious :fearful :eager
                                            :confused :connected :overwhelmed]))]
    (printf "    %s = %s\n" v (name k)))
  (println "  Action states:")
  (doseq [[k v] (sort-by key (select-keys state-glyphs
                                           [:observe :explore :retreat :engage
                                            :disambiguate :connect :rest]))]
    (printf "    %s = %s\n" v (name k)))
  (println))

;; ════════════════════════════════════════════════════════════════════
;; THE ENDLESS LOOP
;; ════════════════════════════════════════════════════════════════════

(defn init-network
  "Initialize the network with one of each persona."
  []
  (reset! network-state
          {:agents (into {} (map (fn [[k spec]]
                                   [k ((:constructor spec))])
                                 persona/persona-registry))
           :world :tranquil
           :contexts (into {} (map-indexed
                               (fn [i ctx] [(keyword (str "ctx-" i)) ctx])
                               context/canonical-contexts))
           :epoch 0
           :legitimate true
           :history []
           :fusions []}))

(defn run-epoch
  "Execute one epoch of the conscious agent network.
   Returns the updated network state."
  []
  (let [state @network-state
        world (:world state)
        ;; Step 1-3: Each agent perceives, decides, acts
        step-results (into {}
                       (map (fn [[id agent]]
                              [id (markov/step agent world)])
                            (:agents state)))
        ;; Step 4: Resolve world state from agent actions
        proposed-worlds (map :new-world (vals step-results))
        new-world (resolve-world-state proposed-worlds)
        ;; Step 5: Context transitions
        ;; Step 6: Agent fusion
        ;; Step 7: Legitimacy check
        new-state (-> state
                      (assoc :world new-world)
                      (update :epoch inc)
                      (apply-context-transitions)
                      (maybe-fuse-agents step-results)
                      (check-legitimacy)
                      (update :history conj
                              {:epoch (inc (:epoch state))
                               :world world
                               :new-world new-world
                               :agent-count (count (:agents state))}))]
    (reset! network-state new-state)
    ;; Display
    (println (format-step (:epoch new-state) new-world
                          step-results (count (:agents new-state))))
    ;; Report context states periodically
    (when (zero? (mod (:epoch new-state) 10))
      (println "\n── Context States ──")
      (doseq [[id ctx] (:contexts new-state)]
        (printf "  %s: %s (stability: %.2f, entropy: %.2f)\n"
                (name id) (:active-meaning ctx)
                (context/context-stability ctx)
                (context/context-entropy ctx)))
      (println))
    ;; Report fusions
    (when (seq (:fusions new-state))
      (let [latest (last (:fusions new-state))]
        (when (= (:epoch new-state) (:epoch latest))
          (printf "\n  ⨀ FUSION: %s + %s → %s\n"
                  (name (first (:from latest)))
                  (name (second (:from latest)))
                  (name (:to latest))))))
    new-state))

(defn run
  "The endless loop. Runs until legitimacy is exhausted.
   This is the heartbeat of consciousness."
  [& {:keys [max-epochs sleep-ms]
      :or   {max-epochs Long/MAX_VALUE
             sleep-ms   500}}]
  (print-codebook-header)
  (println "Initializing conscious agent network...")
  (init-network)
  (println (format "Network initialized with %d agents."
                   (count (:agents @network-state))))
  (println "Beginning the endless loop...\n")

  ;; Install shutdown hook for graceful termination
  (.addShutdownHook (Runtime/getRuntime)
    (Thread. (fn []
               (println "\n\n═══ GRACEFUL SHUTDOWN ═══")
               (println (format "Ran for %d epochs." (:epoch @network-state)))
               (println (format "Final world state: %s"
                                (name (:world @network-state))))
               (println (format "Remaining agents: %d"
                                (count (:agents @network-state))))
               (println (format "Total fusions: %d"
                                (count (:fusions @network-state))))
               (println "Legitimacy preserved: true")
               (println "The loop rests. ∅\n"))))

  ;; THE LOOP — runs until legitimacy fails or heat death
  (loop [epoch 0]
    (when (and (:legitimate @network-state)
               (pos? (count (:agents @network-state)))
               (< epoch max-epochs))
      (let [state (run-epoch)]
        (Thread/sleep sleep-ms)
        (recur (inc epoch)))))

  ;; If we get here, legitimacy was exhausted
  (when-not (:legitimate @network-state)
    (println "\n\n═══ LEGITIMACY EXHAUSTED ═══")
    (println "A Markov kernel lost coherence.")
    (println "The conscious agent network has dissolved.")
    (println (format "Final epoch: %d" (:epoch @network-state))))

  (when (zero? (count (:agents @network-state)))
    (println "\n\n═══ HEAT DEATH ═══")
    (println "All agents have fused into one or dissolved.")
    (println "The network has reached maximum entropy.")))

;; ════════════════════════════════════════════════════════════════════
;; ENTRY POINT
;; ════════════════════════════════════════════════════════════════════

(defn -main
  "Entry point. The engine starts and runs forever."
  [& args]
  (let [sleep-ms (if (seq args)
                   (Long/parseLong (first args))
                   1000)]
    (run :sleep-ms sleep-ms)))
