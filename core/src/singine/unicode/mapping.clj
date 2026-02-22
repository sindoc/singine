(ns singine.unicode.mapping
  "Unicode character mapping to consciousness concepts.

   Each Unicode character is mapped to a concept from the taxonomy of consciousness,
   aligned with Wikipedia disambiguation semantics and Collibra reference data.

   The ordering follows the Great Chain of Being:
   Mineral → Vegetative → Animal → Rational → Intellectual → Divine

   Within each level, characters map to faculties as identified by
   Aristotle (De Anima), Avicenna (Kitāb al-Nafs), Aquinas (Summa),
   and Hoffman (Conscious Agents, 2014).

   Wikipedia disambiguation principle: each concept maps to a WP article
   or disambiguation page, capturing the CONTEXT of the term.
   Context itself is a Collibra Business Asset type.")

;; ════════════════════════════════════════════════════════════════════
;; LAYER 0: MARKOV KERNEL OPERATORS (Hoffman's 6-tuple formalism)
;; C = ⟨(X,𝒳), (G,𝒢), P, D, A, N⟩
;; ════════════════════════════════════════════════════════════════════

(def markov-kernel-symbols
  "The six components of a conscious agent mapped to Unicode operators.
   These are the atoms of the system — everything composes from here."
  {;; Measurable space of experiences — what is perceived
   ;; WP: https://en.wikipedia.org/wiki/Qualia
   \u2B50 {:code "U+2B50" :name "STAR"
           :concept :experience-space :hoffman-symbol 'X
           :wp "Qualia" :wp-disambig "Qualia_(philosophy)"
           :collibra-type "Business Asset"
           :description "Set of possible conscious experiences (X, 𝒳)"}

   ;; Measurable space of actions — what can be done
   ;; WP: https://en.wikipedia.org/wiki/Agency_(philosophy)
   \u2694 {:code "U+2694" :name "CROSSED SWORDS"
           :concept :action-space :hoffman-symbol 'G
           :wp "Agency_(philosophy)" :wp-disambig "Agency_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Set of possible actions (G, 𝒢)"}

   ;; Perception kernel P: W × 𝒳 → [0,1]
   ;; WP: https://en.wikipedia.org/wiki/Perception
   \u0398 {:code "U+0398" :name "GREEK CAPITAL THETA"
           :concept :perception-kernel :hoffman-symbol 'P
           :wp "Perception" :wp-disambig "Perception_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Markov kernel mapping world states to experiences"}

   ;; Decision kernel D: X × 𝒢 → [0,1]
   ;; WP: https://en.wikipedia.org/wiki/Decision-making
   \u0394 {:code "U+0394" :name "GREEK CAPITAL DELTA"
           :concept :decision-kernel :hoffman-symbol 'D
           :wp "Decision-making" :wp-disambig "Decision_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Markov kernel mapping experiences to actions"}

   ;; Action kernel A: G × 𝒲 → [0,1]
   ;; WP: https://en.wikipedia.org/wiki/Action_(philosophy)
   \u0391 {:code "U+0391" :name "GREEK CAPITAL ALPHA"
           :concept :action-kernel :hoffman-symbol 'A
           :wp "Action_(philosophy)" :wp-disambig "Action_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Markov kernel mapping actions to world state changes"}

   ;; World state space — the shared interface
   ;; WP: https://en.wikipedia.org/wiki/World_(philosophy)
   \u2641 {:code "U+2641" :name "EARTH"
           :concept :world-space :hoffman-symbol 'W
           :wp "World_(philosophy)" :wp-disambig "World_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Measurable space of world states (W, 𝒲)"}

   ;; Iteration counter — discrete time
   ;; WP: https://en.wikipedia.org/wiki/Discrete_time
   \u221E {:code "U+221E" :name "INFINITY"
           :concept :iteration :hoffman-symbol 'N
           :wp "Infinity" :wp-disambig "Infinity_(disambiguation)"
           :collibra-type "Technology Asset"
           :description "Positive integer, unbounded iteration counter"}})

;; ════════════════════════════════════════════════════════════════════
;; LAYER 1: ARISTOTLE'S DE ANIMA — Soul Faculties
;; The foundation taxonomy (~350 BCE)
;; ════════════════════════════════════════════════════════════════════

(def aristotle-faculties
  "Aristotle's tripartite soul with sub-faculties.
   Each maps to a Unicode char and Wikipedia article."
  {;; ── NUTRITIVE SOUL (threptikon) ──────────────────────
   ;; Present in: plants, animals, humans
   \u2698 {:code "U+2698" :name "FLOWER"
           :concept :nutritive-soul :thinker :aristotle
           :wp "Vegetative_soul" :wp-disambig "Soul_(disambiguation)"
           :collibra-type "Business Asset"
           :faculties [:growth :nutrition :reproduction]
           :description "Threptikon — the vegetative principle"}

   \u2191 {:code "U+2191" :name "UPWARDS ARROW"
           :concept :growth :thinker :aristotle :parent :nutritive-soul
           :wp "Growth" :wp-disambig "Growth_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Auxēsis — capacity for increase"}

   \u2B59 {:code "U+2B59" :name "HEAVY CIRCLE"
           :concept :nutrition :thinker :aristotle :parent :nutritive-soul
           :wp "Nutrition" :wp-disambig "Nutrition_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Threptikon — capacity for nourishment"}

   \u2606 {:code "U+2606" :name "WHITE STAR"
           :concept :reproduction :thinker :aristotle :parent :nutritive-soul
           :wp "Reproduction" :wp-disambig "Reproduction_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Genesis — capacity to generate another like itself"}

   ;; ── SENSITIVE SOUL (aisthētikon) ─────────────────────
   ;; Present in: animals, humans
   \u2660 {:code "U+2660" :name "BLACK SPADE SUIT"
           :concept :sensitive-soul :thinker :aristotle
           :wp "Sensitive_soul" :wp-disambig "Sensitivity_(disambiguation)"
           :collibra-type "Business Asset"
           :faculties [:sight :hearing :smell :taste :touch
                       :common-sense :imagination :desire :locomotion]
           :description "Aisthētikon — the animal principle"}

   ;; Five external senses
   \u25C9 {:code "U+25C9" :name "FISHEYE"
           :concept :sight :thinker :aristotle :parent :sensitive-soul
           :wp "Visual_perception" :wp-disambig "Sight_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Opsis — sight, perception of colour"}

   \u266B {:code "U+266B" :name "BEAMED EIGHTH NOTES"
           :concept :hearing :thinker :aristotle :parent :sensitive-soul
           :wp "Hearing" :wp-disambig "Hearing_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Akoē — hearing, perception of sound"}

   \u2740 {:code "U+2740" :name "WHITE FLORETTE"
           :concept :smell :thinker :aristotle :parent :sensitive-soul
           :wp "Olfaction" :wp-disambig "Smell_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Osphrēsis — smell, perception of odour"}

   \u2615 {:code "U+2615" :name "HOT BEVERAGE"
           :concept :taste :thinker :aristotle :parent :sensitive-soul
           :wp "Taste" :wp-disambig "Taste_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Geusis — taste, perception of flavour"}

   \u270B {:code "U+270B" :name "RAISED HAND"
           :concept :touch :thinker :aristotle :parent :sensitive-soul
           :wp "Somatosensory_system" :wp-disambig "Touch_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Haphē — touch, the most fundamental sense"}

   ;; Higher animal faculties
   \u29BF {:code "U+29BF" :name "CIRCLED BULLET"
           :concept :common-sense :thinker :aristotle :parent :sensitive-soul
           :wp "Common_sense" :wp-disambig "Common_sense_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Koinē aisthēsis — unifies data from all five senses"}

   \u2601 {:code "U+2601" :name "CLOUD"
           :concept :imagination :thinker :aristotle :parent :sensitive-soul
           :wp "Imagination" :wp-disambig "Imagination_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Phantasia — image-making faculty, bridges sense and thought"}

   \u2764 {:code "U+2764" :name "HEAVY BLACK HEART"
           :concept :desire :thinker :aristotle :parent :sensitive-soul
           :wp "Desire" :wp-disambig "Desire_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Orexis — appetitive faculty, moves toward or away"}

   \u27A1 {:code "U+27A1" :name "BLACK RIGHTWARDS ARROW"
           :concept :locomotion :thinker :aristotle :parent :sensitive-soul
           :wp "Animal_locomotion" :wp-disambig "Locomotion_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Kinēsis — self-movement driven by desire"}

   ;; ── RATIONAL SOUL (noētikon) ─────────────────────────
   ;; Present in: humans only
   \u2666 {:code "U+2666" :name "BLACK DIAMOND SUIT"
           :concept :rational-soul :thinker :aristotle
           :wp "Nous" :wp-disambig "Reason_(disambiguation)"
           :collibra-type "Business Asset"
           :faculties [:passive-intellect :active-intellect :deliberation]
           :description "Noētikon — the rational principle, unique to humans"}

   \u25CB {:code "U+25CB" :name "WHITE CIRCLE"
           :concept :passive-intellect :thinker :aristotle :parent :rational-soul
           :wp "Passive_intellect" :wp-disambig "Intellect_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Nous pathētikos — receives intelligible forms"}

   \u25CF {:code "U+25CF" :name "BLACK CIRCLE"
           :concept :active-intellect :thinker :aristotle :parent :rational-soul
           :wp "Active_intellect" :wp-disambig "Intellect_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Nous poiētikos — makes all things thinkable, immortal"}

   \u2696 {:code "U+2696" :name "SCALES"
           :concept :deliberation :thinker :aristotle :parent :rational-soul
           :wp "Deliberation" :wp-disambig "Deliberation_(disambiguation)"
           :collibra-type "Business Asset"
           :description "Bouleusis — practical reasoning about action"}})

;; ════════════════════════════════════════════════════════════════════
;; LAYER 2: AVICENNA (IBN SINA) — Five Internal Senses
;; Kitāb al-Nafs within al-Shifāʾ (~1027 CE)
;; ════════════════════════════════════════════════════════════════════

(def avicenna-faculties
  "Ibn Sina's refinement: five INTERNAL senses + the Floating Man.
   The Floating Man proves self-awareness is independent of sensation."
  {;; The Floating Man — proof of immaterial self-awareness
   ;; WP: https://en.wikipedia.org/wiki/Floating_man
   \u2708 {:code "U+2708" :name "AIRPLANE"
           :concept :floating-man :thinker :avicenna
           :wp "Floating_man" :wp-disambig nil
           :collibra-type "Business Asset"
           :description "The Flying Man — self-awareness without any sensory input"}

   ;; ── FIVE INTERNAL SENSES ────────────────────────────
   ;; These refine Aristotle's common sense and imagination

   ;; 1. Sensus Communis (al-ḥiss al-mushtarak)
   \u2295 {:code "U+2295" :name "CIRCLED PLUS"
           :concept :sensus-communis :thinker :avicenna
           :wp "Common_sense" :wp-disambig "Common_sense_(Aristotle)"
           :collibra-type "Business Asset"
           :parent :sensitive-soul
           :description "Fuses data from all external senses into unified percept"}

   ;; 2. Retentive Imagination (al-khayāl / al-muṣawwira)
   \u29C1 {:code "U+29C1" :name "CIRCLE WITH SUPERIMPOSED X"
           :concept :retentive-imagination :thinker :avicenna
           :wp "Imagination" :wp-disambig "Mental_image"
           :collibra-type "Business Asset"
           :parent :sensitive-soul
           :description "Stores sensory forms after the object is removed"}

   ;; 3. Compositive Imagination (al-mutakhayyila)
   \u2A01 {:code "U+2A01" :name "N-ARY CIRCLED PLUS"
           :concept :compositive-imagination :thinker :avicenna
           :wp "Imagination" :wp-disambig "Creative_imagination"
           :collibra-type "Business Asset"
           :parent :sensitive-soul
           :description "Combines and separates stored images — creates golden mountains"}

   ;; 4. Estimative Faculty (al-wahmiyya)
   \u26A0 {:code "U+26A0" :name "WARNING SIGN"
           :concept :estimation :thinker :avicenna
           :wp "Estimative_faculty" :wp-disambig nil
           :collibra-type "Business Asset"
           :parent :sensitive-soul
           :description "Judges non-sensible meanings: friend/foe, safe/dangerous"}

   ;; 5. Memory (al-ḥāfiẓa)
   \u2318 {:code "U+2318" :name "PLACE OF INTEREST"
           :concept :memory :thinker :avicenna
           :wp "Memory" :wp-disambig "Memory_(disambiguation)"
           :collibra-type "Business Asset"
           :parent :sensitive-soul
           :description "Retains estimative judgements — the archive of meaning"}

   ;; ── INTELLECTIVE HIERARCHY ──────────────────────────
   ;; Avicenna's five stages of intellect

   \u2070 {:code "U+2070" :name "SUPERSCRIPT ZERO"
           :concept :material-intellect :thinker :avicenna
           :wp "Passive_intellect" :wp-disambig "Tabula_rasa"
           :collibra-type "Business Asset"
           :parent :rational-soul
           :description "Pure potentiality — the blank tablet"}

   \u00B9 {:code "U+00B9" :name "SUPERSCRIPT ONE"
           :concept :habitual-intellect :thinker :avicenna
           :wp "Disposition" :wp-disambig "Habit_(disambiguation)"
           :collibra-type "Business Asset"
           :parent :rational-soul
           :description "Acquired disposition toward knowing first principles"}

   \u00B2 {:code "U+00B2" :name "SUPERSCRIPT TWO"
           :concept :actual-intellect :thinker :avicenna
           :wp "Intellect" :wp-disambig "Intellect_(disambiguation)"
           :collibra-type "Business Asset"
           :parent :rational-soul
           :description "Active engagement — thinks when it chooses"}

   \u00B3 {:code "U+00B3" :name "SUPERSCRIPT THREE"
           :concept :acquired-intellect :thinker :avicenna
           :wp "Active_intellect" :wp-disambig "Nous_(disambiguation)"
           :collibra-type "Business Asset"
           :parent :rational-soul
           :description "Knowledge received from the Active Intellect"}

   \u2074 {:code "U+2074" :name "SUPERSCRIPT FOUR"
           :concept :active-intellect-cosmic :thinker :avicenna
           :wp "Active_intellect" :wp-disambig "Nous"
           :collibra-type "Business Asset"
           :parent :rational-soul
           :description "The supernal Intellect — source of all intelligibles"}})

;; ════════════════════════════════════════════════════════════════════
;; LAYER 3: TRANSITION OPERATORS — Markov Chain Arrows
;; How faculties influence each other with probability
;; ════════════════════════════════════════════════════════════════════

(def transition-symbols
  "Unicode arrows and operators representing state transitions
   in the conscious agent Markov chain."
  {\u2192 {:code "U+2192" :concept :transition
           :description "State transition: P(next | current)"}
   \u21C4 {:code "U+21C4" :concept :bidirectional-coupling
           :description "Two agents mutually perceiving each other"}
   \u21BA {:code "U+21BA" :concept :perception-decision-action-loop
           :description "The P→D→A cycle, the heartbeat of a conscious agent"}
   \u2A00 {:code "U+2A00" :concept :agent-fusion
           :description "Composition of two conscious agents into one"}
   \u2234 {:code "U+2234" :concept :therefore
           :description "Logical consequence — deliberation yields action"}
   \u2235 {:code "U+2235" :concept :because
           :description "Causal grounding — experience motivates decision"}
   \u22A2 {:code "U+22A2" :concept :entails
           :description "Formal entailment within the kernel"}
   \u2261 {:code "U+2261" :concept :identity
           :description "Entity resolution — Union-Find equality"}
   \u2248 {:code "U+2248" :concept :approximate-equality
           :description "Cosine similarity above threshold"}
   \u2282 {:code "U+2282" :concept :proper-subset
           :description "Faculty containment — nutritive ⊂ sensitive ⊂ rational"}
   \u222B {:code "U+222B" :concept :integration
           :description "Qualia-kernel integration over all actions and world states"}
   \u2211 {:code "U+2211" :concept :summation
           :description "Probability normalization — rows sum to 1"}
   \u220F {:code "U+220F" :concept :product
           :description "Product of Markov kernels in composition"}
   \u2205 {:code "U+2205" :concept :empty-set
           :description "No experience — pre-consciousness void"}
   \u2203 {:code "U+2203" :concept :exists
           :description "Something exists to be experienced — the first fact"}
   \u2200 {:code "U+2200" :concept :for-all
           :description "Universal quantifier — conscious agents all the way down"}})

;; ════════════════════════════════════════════════════════════════════
;; LAYER 4: CONTEXT — The new Collibra Business Asset Type
;; ════════════════════════════════════════════════════════════════════

(def context-symbols
  "Context is a disambiguation operation.
   Wikipedia disambiguation pages are the best existing model of context:
   the same word means different things in different contexts."
  {\u2630 {:code "U+2630" :concept :context
           :wp "Context_(disambiguation)"
           :collibra-type "Context"
           :collibra-parent "Business Asset"
           :description "A disambiguation frame — determines which meaning applies"}

   \u2637 {:code "U+2637" :concept :context-switch
           :wp "Context_switch"
           :collibra-type "Context"
           :description "Transition between disambiguation frames"}

   \u262F {:code "U+262F" :concept :context-duality
           :wp "Yin_and_yang"
           :collibra-type "Context"
           :description "Every context contains the seed of its opposite"}

   \u2638 {:code "U+2638" :concept :context-wheel
           :wp "Dharma"
           :collibra-type "Context"
           :description "The wheel of contexts — cyclic reinterpretation"}})

;; ════════════════════════════════════════════════════════════════════
;; MASTER CODEBOOK: The complete ordered mapping
;; ════════════════════════════════════════════════════════════════════

(def codebook
  "The complete Unicode-to-consciousness codebook.
   Ordered by ontological level: operators → vegetative → animal → rational → context.
   This is the reference data aligned with Collibra."
  (merge markov-kernel-symbols
         aristotle-faculties
         avicenna-faculties
         transition-symbols
         context-symbols))

(defn lookup
  "Look up a concept by Unicode character."
  [ch]
  (get codebook ch))

(defn by-concept
  "Find the Unicode character for a given concept keyword."
  [concept-kw]
  (first (keep (fn [[ch m]] (when (= concept-kw (:concept m)) ch)) codebook)))

(defn by-thinker
  "All mappings attributed to a given thinker."
  [thinker-kw]
  (into {} (filter (fn [[_ m]] (= thinker-kw (:thinker m))) codebook)))

(defn codebook-table
  "Return the codebook as a sorted sequence for display."
  []
  (->> codebook
       (sort-by (comp :code val))
       (map (fn [[ch m]]
              (assoc m :char (str ch))))))
