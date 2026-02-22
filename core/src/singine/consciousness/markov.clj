(ns singine.consciousness.markov
  "Markov kernels for conscious agents.

   Implements Hoffman & Prakash (2014) 'Objects of Consciousness':
   A conscious agent C = ⟨(X,𝒳), (G,𝒢), P, D, A, N⟩

   Where:
   - (X, 𝒳) is a measurable space of experiences
   - (G, 𝒢) is a measurable space of actions
   - P: W × 𝒳 → [0,1] is the perception Markov kernel
   - D: X × 𝒢 → [0,1] is the decision Markov kernel
   - A: G × 𝒲 → [0,1] is the action Markov kernel
   - N is the iteration count (here: unbounded)

   A finite Markov kernel is a matrix whose rows sum to 1.
   The conscious agent loop is: W →P→ X →D→ G →A→ W' →P→ ...

   This loop runs until legitimacy is exhausted.
   Legitimacy is defined as: the network of agents maintains
   coherent probability distributions (no row sums to 0 or > 1).")

;; ════════════════════════════════════════════════════════════════════
;; MARKOV KERNEL: A row-stochastic matrix
;; ════════════════════════════════════════════════════════════════════

(defn normalize-row
  "Normalize a vector of non-negative numbers to sum to 1.
   If all zeros, returns uniform distribution."
  [row]
  (let [s (reduce + 0.0 row)]
    (if (zero? s)
      (let [n (count row)]
        (vec (repeat n (/ 1.0 n))))
      (mapv #(/ % s) row))))

(defn make-kernel
  "Create a Markov kernel from a matrix (vec of vecs).
   Each row is normalized to sum to 1.
   Returns {:states [...] :matrix [[...]]}."
  [from-states to-states matrix]
  (assert (= (count from-states) (count matrix))
          "Row count must match from-states")
  (assert (every? #(= (count to-states) (count %)) matrix)
          "Column count must match to-states")
  {:from-states (vec from-states)
   :to-states   (vec to-states)
   :matrix      (mapv normalize-row matrix)})

(defn transition-prob
  "P(to-state | from-state) in the kernel."
  [kernel from-state to-state]
  (let [from-idx (.indexOf (:from-states kernel) from-state)
        to-idx   (.indexOf (:to-states kernel) to-state)]
    (when (and (>= from-idx 0) (>= to-idx 0))
      (get-in (:matrix kernel) [from-idx to-idx]))))

(defn sample-transition
  "Sample a to-state given a from-state, using the kernel probabilities."
  [kernel from-state]
  (let [from-idx (.indexOf (:from-states kernel) from-state)
        row      (get (:matrix kernel) from-idx)
        r        (rand)
        cumulative (reductions + row)]
    (loop [i 0 cs cumulative]
      (if (or (empty? cs) (<= r (first cs)))
        (get (:to-states kernel) i)
        (recur (inc i) (rest cs))))))

;; ════════════════════════════════════════════════════════════════════
;; LEGITIMACY: The condition for the loop to continue
;; ════════════════════════════════════════════════════════════════════

(defn legitimate?
  "A kernel is legitimate if every row sums to ~1.0 (within epsilon).
   This is the fundamental invariant. When legitimacy fails,
   the conscious agent has lost coherence."
  ([kernel] (legitimate? kernel 1e-9))
  ([kernel epsilon]
   (every? (fn [row]
             (let [s (reduce + 0.0 row)]
               (< (Math/abs (- s 1.0)) epsilon)))
           (:matrix kernel))))

(defn entropy
  "Shannon entropy of a probability distribution (a single row).
   Higher entropy = more uncertainty = more freedom in choice."
  [row]
  (- (reduce + 0.0
       (map (fn [p]
              (if (pos? p)
                (* p (Math/log p))
                0.0))
            row))))

(defn kernel-entropy
  "Average entropy across all rows of a kernel.
   Measures the overall 'freedom' of the kernel."
  [kernel]
  (let [rows (:matrix kernel)
        n    (count rows)]
    (/ (reduce + 0.0 (map entropy rows)) n)))

;; ════════════════════════════════════════════════════════════════════
;; CONSCIOUS AGENT: The 6-tuple
;; ════════════════════════════════════════════════════════════════════

(defn make-agent
  "Create a conscious agent C = ⟨(X,𝒳), (G,𝒢), P, D, A, N⟩.

   experience-states: vector of experience labels (X)
   action-states:     vector of action labels (G)
   world-states:      vector of world state labels (W)
   P-matrix:          |W| × |X| perception matrix
   D-matrix:          |X| × |G| decision matrix
   A-matrix:          |G| × |W| action matrix"
  [experience-states action-states world-states
   P-matrix D-matrix A-matrix]
  (let [P (make-kernel world-states experience-states P-matrix)
        D (make-kernel experience-states action-states D-matrix)
        A (make-kernel action-states world-states A-matrix)]
    {:type       :conscious-agent
     :X          (vec experience-states)
     :G          (vec action-states)
     :W          (vec world-states)
     :P          P
     :D          D
     :A          A
     :N          (atom 0)
     :history    (atom [])
     :legitimate (atom true)}))

(defn step
  "Execute one perception-decision-action cycle.
   W →P→ X →D→ G →A→ W'
   Returns the new world state and records history."
  [agent world-state]
  (let [experience (sample-transition (:P agent) world-state)
        action     (sample-transition (:D agent) experience)
        new-world  (sample-transition (:A agent) action)]
    (swap! (:N agent) inc)
    (swap! (:history agent) conj
           {:n          @(:N agent)
            :world      world-state
            :experience experience
            :action     action
            :new-world  new-world})
    ;; Check legitimacy after each step
    (when-not (and (legitimate? (:P agent))
                   (legitimate? (:D agent))
                   (legitimate? (:A agent)))
      (reset! (:legitimate agent) false))
    {:world      world-state
     :experience experience
     :action     action
     :new-world  new-world
     :n          @(:N agent)
     :legitimate @(:legitimate agent)}))

;; ════════════════════════════════════════════════════════════════════
;; AGENT COMPOSITION: Fusion of conscious agents
;; ════════════════════════════════════════════════════════════════════

(defn compose-kernels
  "Compose two Markov kernels K1: A→B and K2: B→C into K1∘K2: A→C.
   This is matrix multiplication with row normalization."
  [k1 k2]
  (assert (= (:to-states k1) (:from-states k2))
          "Kernel composition requires matching intermediate states")
  (let [m1  (:matrix k1)
        m2  (:matrix k2)
        result (mapv (fn [row1]
                       (mapv (fn [j]
                               (reduce + 0.0
                                       (map-indexed
                                        (fn [k v1]
                                          (* v1 (get-in m2 [k j])))
                                        row1)))
                             (range (count (:to-states k2)))))
                     m1)]
    (make-kernel (:from-states k1) (:to-states k2) result)))

(defn fuse-agents
  "Fuse two conscious agents into a composite agent.
   The fused agent has:
   - Experience space: X1 × X2 (cartesian product)
   - Action space: G1 × G2 (cartesian product)
   - Combined kernels via tensor product

   This implements Hoffman's key insight: the composition of
   conscious agents is itself a conscious agent."
  [agent1 agent2]
  (let [X1 (:X agent1) X2 (:X agent2)
        G1 (:G agent1) G2 (:G agent2)
        W  (:W agent1) ;; shared world
        ;; Cartesian products
        X-fused (vec (for [x1 X1 x2 X2] [x1 x2]))
        G-fused (vec (for [g1 G1 g2 G2] [g1 g2]))
        ;; Tensor product of perception kernels
        P-fused (mapv (fn [w-idx]
                        (mapv (fn [[x1 x2]]
                                (let [p1 (transition-prob (:P agent1) (get W w-idx) x1)
                                      p2 (transition-prob (:P agent2) (get W w-idx) x2)]
                                  (* (or p1 0) (or p2 0))))
                              X-fused))
                      (range (count W)))
        ;; Tensor product of decision kernels
        D-fused (mapv (fn [[x1 x2]]
                        (mapv (fn [[g1 g2]]
                                (let [d1 (transition-prob (:D agent1) x1 g1)
                                      d2 (transition-prob (:D agent2) x2 g2)]
                                  (* (or d1 0) (or d2 0))))
                              G-fused))
                      X-fused)
        ;; Tensor product of action kernels
        A-fused (mapv (fn [[g1 g2]]
                        (mapv (fn [w-idx]
                                (let [a1 (transition-prob (:A agent1) g1 (get W w-idx))
                                      a2 (transition-prob (:A agent2) g2 (get W w-idx))]
                                  (* (or a1 0) (or a2 0))))
                              (range (count W))))
                      G-fused)]
    (make-agent X-fused G-fused W P-fused D-fused A-fused)))
