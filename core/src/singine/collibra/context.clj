(ns singine.collibra.context
  "Context as a new Collibra Business Asset type.

   In the Collibra metamodel, Business Assets represent governed data concepts.
   Context is the disambiguation frame that determines which meaning applies
   to a term — exactly like Wikipedia disambiguation pages.

   'Bank' → Bank (finance) | Bank (geography) | Bank (aviation) | ...

   The context asset type captures:
   - The set of possible meanings (disambiguation set)
   - The active meaning in current context
   - The transition probabilities between contexts (context-switching)
   - The Markov kernel over contexts (how likely is reinterpretation)

   This aligns with Hoffman's framework: the perception kernel P
   IS a context — it determines how the world becomes experience.
   Different agents perceive different contexts of the same world state.

   Collibra Operating Model placement:
   Community → Domain → Context (under Business Asset)
   Context has relations to:
   - Data Asset (what data the context disambiguates)
   - Technology Asset (what system provides the context)
   - Governance Asset (what policy governs context transitions)")

;; ════════════════════════════════════════════════════════════════════
;; CONTEXT ASSET TYPE DEFINITION
;; ════════════════════════════════════════════════════════════════════

(def context-asset-type
  "The Context asset type as it would appear in Collibra's metamodel."
  {:asset-type-id   "singine:context"
   :name            "Context"
   :parent-type     "Business Asset"
   :description     "A disambiguation frame determining which meaning applies to a concept"
   :icon            \u2630  ;; ☰ trigram for heaven — ordered context

   :attributes
   [{:name "Disambiguation Set"
     :type :multi-value-list
     :description "All possible meanings this context can resolve to"
     :example ["Bank (finance)" "Bank (geography)" "Bank (aviation)"]}

    {:name "Active Meaning"
     :type :single-value
     :description "The currently selected meaning in this context"
     :example "Bank (finance)"}

    {:name "Context Source"
     :type :single-value
     :description "What provides this context: user, system, inference, or convention"
     :allowed-values ["user-specified" "system-inferred" "convention" "hybrid"]}

    {:name "Transition Kernel"
     :type :complex
     :description "Markov kernel over the disambiguation set — P(meaning_j | meaning_i)"
     :example "Row-stochastic matrix over meanings"}

    {:name "Wikipedia Reference"
     :type :url
     :description "The Wikipedia disambiguation page for this concept"
     :example "https://en.wikipedia.org/wiki/Bank_(disambiguation)"}

    {:name "Entropy"
     :type :numeric
     :description "Shannon entropy of the context's transition kernel — higher = more ambiguous"
     :unit "nats"}

    {:name "Stability"
     :type :numeric
     :description "How likely the context is to remain stable (1 - max off-diagonal probability)"
     :range [0.0 1.0]}]

   :relations
   [{:name "disambiguates"
     :target-type "Data Asset"
     :description "The data concept this context disambiguates"}

    {:name "provided-by"
     :target-type "Technology Asset"
     :description "The system that determines or provides this context"}

    {:name "governed-by"
     :target-type "Governance Asset"
     :description "The policy governing how this context may transition"}

    {:name "subsumes"
     :target-type "Context"
     :description "This context is a specialization of another context"}

    {:name "conflicts-with"
     :target-type "Context"
     :description "Two contexts that cannot be simultaneously active"}]

   :status-workflow
   ["Candidate" "Accepted" "Active" "Deprecated" "Rejected"]})

;; ════════════════════════════════════════════════════════════════════
;; CONTEXT INSTANCES
;; ════════════════════════════════════════════════════════════════════

(defn make-context
  "Create a context instance with a disambiguation set and transition kernel."
  [name disambiguation-set & {:keys [source wp-page kernel]
                               :or   {source :convention
                                       wp-page nil
                                       kernel nil}}]
  (let [n (count disambiguation-set)
        ;; Default kernel: slight preference for staying in current meaning
        default-kernel (vec (for [i (range n)]
                              (vec (for [j (range n)]
                                     (if (= i j) 0.7
                                       (/ 0.3 (dec n)))))))]
    {:type               :context
     :name               name
     :disambiguation-set (vec disambiguation-set)
     :active-meaning     (first disambiguation-set)
     :source             source
     :wp-page            wp-page
     :kernel             (or kernel default-kernel)
     :created-at         (System/currentTimeMillis)
     :status             "Active"}))

(defn context-entropy
  "Shannon entropy of the context's transition kernel.
   Measures ambiguity: higher entropy = more contextual freedom."
  [ctx]
  (let [rows (:kernel ctx)]
    (/ (reduce + 0.0
         (map (fn [row]
                (- (reduce + 0.0
                     (map (fn [p]
                            (if (pos? p) (* p (Math/log p)) 0.0))
                          row))))
              rows))
       (count rows))))

(defn context-stability
  "How likely the context is to stay in its current meaning.
   Returns the average diagonal probability."
  [ctx]
  (let [rows (:kernel ctx)
        n    (count rows)]
    (/ (reduce + 0.0 (map-indexed (fn [i row] (nth row i)) rows)) n)))

(defn switch-context
  "Transition the context to a new active meaning based on the kernel."
  [ctx]
  (let [meanings (:disambiguation-set ctx)
        idx      (.indexOf meanings (:active-meaning ctx))
        row      (get (:kernel ctx) idx)
        r        (rand)
        cumul    (reductions + row)
        new-idx  (count (take-while #(> r %) cumul))]
    (assoc ctx :active-meaning (get meanings (min new-idx (dec (count meanings)))))))

;; ════════════════════════════════════════════════════════════════════
;; CANONICAL CONTEXTS (examples aligned with Wikipedia disambiguation)
;; ════════════════════════════════════════════════════════════════════

(def canonical-contexts
  "Well-known disambiguation contexts, each mapping to a WP page."
  [(make-context "Consciousness"
                 ["Consciousness (philosophy of mind)"
                  "Consciousness (neuroscience)"
                  "Consciousness (psychology)"
                  "Consciousness (spiritual)"
                  "Consciousness (artificial intelligence)"]
                 :wp-page "https://en.wikipedia.org/wiki/Consciousness_(disambiguation)")

   (make-context "Perception"
                 ["Perception (psychology)"
                  "Perception (philosophy)"
                  "Perception (Hoffman - Markov kernel)"
                  "Perception (computer vision)"
                  "Perception (social)"]
                 :wp-page "https://en.wikipedia.org/wiki/Perception_(disambiguation)")

   (make-context "Agent"
                 ["Agent (philosophy)"
                  "Agent (software)"
                  "Agent (conscious - Hoffman)"
                  "Agent (economics)"
                  "Agent (law)"]
                 :wp-page "https://en.wikipedia.org/wiki/Agent_(disambiguation)")

   (make-context "Decision"
                 ["Decision (logic)"
                  "Decision (psychology)"
                  "Decision (Hoffman - Markov kernel)"
                  "Decision (law)"
                  "Decision (game theory)"]
                 :wp-page "https://en.wikipedia.org/wiki/Decision_(disambiguation)")

   (make-context "Memory"
                 ["Memory (cognitive)"
                  "Memory (Avicenna - al-ḥāfiẓa)"
                  "Memory (computer)"
                  "Memory (cultural)"
                  "Memory (episodic)"]
                 :wp-page "https://en.wikipedia.org/wiki/Memory_(disambiguation)")

   (make-context "Soul"
                 ["Soul (Aristotle - psyche)"
                  "Soul (Avicenna - nafs)"
                  "Soul (theology)"
                  "Soul (music)"
                  "Soul (Hoffman - conscious agent)"]
                 :wp-page "https://en.wikipedia.org/wiki/Soul_(disambiguation)")])
