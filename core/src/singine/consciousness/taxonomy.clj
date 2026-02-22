(ns singine.consciousness.taxonomy
  "The unified taxonomy of consciousness from Aristotle to Hoffman.

   This namespace defines the ontological hierarchy of consciousness
   as a directed acyclic graph (DAG) where each node is a faculty
   and edges represent containment (⊂) or refinement (→).

   The taxonomy integrates:
   - Aristotle (De Anima, ~350 BCE): nutritive → sensitive → rational
   - Avicenna (al-Shifāʾ, ~1027 CE): five internal senses, floating man
   - Aquinas (Summa, ~1270 CE): agent intellect as divine illumination
   - Descartes (Meditations, 1641): res cogitans / res extensa split
   - Husserl (Logical Investigations, 1900): intentionality structure
   - Hoffman (Objects of Consciousness, 2014): Markov kernel agents

   Each faculty node carries:
   - A Markov kernel signature (what it maps FROM and TO)
   - A probability distribution type (how decisions are weighted)
   - A Unicode character from singine.unicode.mapping
   - A Wikipedia reference for disambiguation"
  (:refer-clojure :exclude [ancestors descendants]))

;; ════════════════════════════════════════════════════════════════════
;; THE GREAT CHAIN: Ontological levels of consciousness
;; ════════════════════════════════════════════════════════════════════

(def levels
  "The ontological levels, each subsuming all below it.
   This is the ⊂ relation: mineral ⊂ vegetative ⊂ animal ⊂ rational ⊂ intellectual."
  [:mineral :vegetative :animal :rational :intellectual])

(def level-properties
  {:mineral      {:self-awareness false :sensation false :locomotion false
                  :reasoning false :description "Exists but does not live"
                  :examples ["stone" "water" "crystal"]}
   :vegetative   {:self-awareness false :sensation false :locomotion false
                  :reasoning false :description "Lives, grows, reproduces"
                  :examples ["oak" "moss" "fungus"]}
   :animal       {:self-awareness :partial :sensation true :locomotion true
                  :reasoning false :description "Senses, moves, desires"
                  :examples ["wolf" "crow" "octopus"]}
   :rational     {:self-awareness true :sensation true :locomotion true
                  :reasoning true :description "Reasons, deliberates, abstracts"
                  :examples ["human" "possibly cetacean" "possibly primate"]}
   :intellectual {:self-awareness :pure :sensation :transcended :locomotion :unnecessary
                  :reasoning :intuitive :description "Pure intellection without matter"
                  :examples ["Avicenna's Active Intellect" "Aristotle's Unmoved Mover"]}})

;; ════════════════════════════════════════════════════════════════════
;; FACULTY GRAPH: The DAG of all faculties across all thinkers
;; ════════════════════════════════════════════════════════════════════

(def faculty-graph
  "Directed acyclic graph of soul faculties.
   Each node has :parents (what it refines) and :children (what refines it).
   The :kernel-sig shows the Markov kernel type: [from-space → to-space]."
  {;; ── ROOT ─────────────────────────────────────────────
   :consciousness
   {:level :all :thinker :hoffman
    :kernel-sig [:world-state :experience]
    :description "The ground of being — conscious agents all the way down"
    :children [:nutritive-soul :sensitive-soul :rational-soul]}

   ;; ── NUTRITIVE (Aristotle) ────────────────────────────
   :nutritive-soul
   {:level :vegetative :thinker :aristotle
    :kernel-sig [:environment :metabolic-state]
    :parents [:consciousness]
    :children [:growth :nutrition :reproduction]
    :description "Threptikon — the principle shared by all living things"}

   :growth
   {:level :vegetative :thinker :aristotle
    :kernel-sig [:nutrients :size-change]
    :parents [:nutritive-soul]
    :description "Auxēsis — directed increase in form"}

   :nutrition
   {:level :vegetative :thinker :aristotle
    :kernel-sig [:environment :energy-state]
    :parents [:nutritive-soul]
    :description "Assimilation of external matter into self"}

   :reproduction
   {:level :vegetative :thinker :aristotle
    :kernel-sig [:organism-state :offspring-probability]
    :parents [:nutritive-soul]
    :description "Genesis — generating another instance of the form"}

   ;; ── SENSITIVE (Aristotle + Avicenna) ─────────────────
   :sensitive-soul
   {:level :animal :thinker :aristotle
    :kernel-sig [:stimulus :percept]
    :parents [:consciousness]
    :children [:external-senses :internal-senses :desire :locomotion]
    :description "Aisthētikon — the capacity for experience"}

   :external-senses
   {:level :animal :thinker :aristotle
    :kernel-sig [:physical-stimulus :sensory-quality]
    :parents [:sensitive-soul]
    :children [:sight :hearing :smell :taste :touch]
    :description "The five gates of perception"}

   :sight
   {:level :animal :thinker :aristotle
    :kernel-sig [:light-pattern :colour-form]
    :parents [:external-senses]
    :description "Opsis — receives colour through a transparent medium"}

   :hearing
   {:level :animal :thinker :aristotle
    :kernel-sig [:air-vibration :sound-quality]
    :parents [:external-senses]
    :description "Akoē — receives sound through air or water"}

   :smell
   {:level :animal :thinker :aristotle
    :kernel-sig [:volatile-molecules :odour-quality]
    :parents [:external-senses]
    :description "Osphrēsis — receives odour, linked to taste"}

   :taste
   {:level :animal :thinker :aristotle
    :kernel-sig [:dissolved-substance :flavour-quality]
    :parents [:external-senses]
    :description "Geusis — receives flavour through moisture"}

   :touch
   {:level :animal :thinker :aristotle
    :kernel-sig [:contact-pressure :tactile-quality]
    :parents [:external-senses]
    :description "Haphē — the most fundamental sense, present in all animals"}

   ;; ── DESIRE AND LOCOMOTION (Aristotle) ──────────────────
   :desire
   {:level :animal :thinker :aristotle
    :kernel-sig [:percept :appetitive-response]
    :parents [:sensitive-soul]
    :description "Orexis — appetitive faculty, moves toward or away"}

   :locomotion
   {:level :animal :thinker :aristotle
    :kernel-sig [:desire-state :movement]
    :parents [:sensitive-soul]
    :description "Kinēsis — self-movement driven by desire"}

   ;; ── INTERNAL SENSES (Avicenna) ───────────────────────
   :internal-senses
   {:level :animal :thinker :avicenna
    :kernel-sig [:raw-percept :processed-image]
    :parents [:sensitive-soul]
    :children [:sensus-communis :retentive-imagination
               :compositive-imagination :estimation :memory]
    :description "Al-ḥawāss al-bāṭina — the five internal processing stages"}

   :sensus-communis
   {:level :animal :thinker :avicenna
    :kernel-sig [:multi-sensory-input :unified-percept]
    :parents [:internal-senses]
    :description "Al-ḥiss al-mushtarak — fuses all five senses into one object"}

   :retentive-imagination
   {:level :animal :thinker :avicenna
    :kernel-sig [:unified-percept :stored-form]
    :parents [:internal-senses]
    :description "Al-khayāl — holds the image after the object departs"}

   :compositive-imagination
   {:level :animal :thinker :avicenna
    :kernel-sig [:stored-forms :novel-composite]
    :parents [:internal-senses]
    :description "Al-mutakhayyila — combines images freely, creates golden mountains"}

   :estimation
   {:level :animal :thinker :avicenna
    :kernel-sig [:percept :intentional-meaning]
    :parents [:internal-senses]
    :description "Al-wahmiyya — grasps non-sensible significance: friend/foe, safe/threat"}

   :memory
   {:level :animal :thinker :avicenna
    :kernel-sig [:intentional-meaning :stored-judgement]
    :parents [:internal-senses]
    :description "Al-ḥāfiẓa — retains estimative judgements across time"}

   ;; ── RATIONAL (Aristotle + Avicenna) ──────────────────
   :rational-soul
   {:level :rational :thinker :aristotle
    :kernel-sig [:intelligible-form :concept]
    :parents [:consciousness]
    :children [:passive-intellect :active-intellect :deliberation
               :material-intellect :habitual-intellect :actual-intellect
               :acquired-intellect :active-intellect-cosmic]
    :description "Noētikon — the capacity for abstract thought"}

   :passive-intellect
   {:level :rational :thinker :aristotle
    :kernel-sig [:intelligible-form :received-concept]
    :parents [:rational-soul]
    :description "Nous pathētikos — the wax that receives the seal"}

   :active-intellect
   {:level :rational :thinker :aristotle
    :kernel-sig [:potential-intelligible :actual-intelligible]
    :parents [:rational-soul]
    :description "Nous poiētikos — the light that makes all colours visible"}

   :deliberation
   {:level :rational :thinker :aristotle
    :kernel-sig [:situation :action-choice]
    :parents [:rational-soul]
    :description "Bouleusis — practical reasoning about what to do"}

   ;; Avicenna's intellective stages (refinement of Aristotle)
   :material-intellect
   {:level :rational :thinker :avicenna
    :kernel-sig [:nothing :pure-potential]
    :parents [:rational-soul]
    :description "Pure potentiality — tabula rasa, the blank slate"}

   :habitual-intellect
   {:level :rational :thinker :avicenna
    :kernel-sig [:first-principles :disposition]
    :parents [:rational-soul]
    :description "Knows first principles, can think when prompted"}

   :actual-intellect
   {:level :rational :thinker :avicenna
    :kernel-sig [:disposition :active-thought]
    :parents [:rational-soul]
    :description "Actively thinking — knowledge in use"}

   :acquired-intellect
   {:level :rational :thinker :avicenna
    :kernel-sig [:active-intellect-emanation :illuminated-knowledge]
    :parents [:rational-soul]
    :description "Knowledge received through conjunction with Active Intellect"}

   :active-intellect-cosmic
   {:level :intellectual :thinker :avicenna
    :kernel-sig [:divine-emanation :all-intelligibles]
    :parents [:rational-soul]
    :description "The cosmic Active Intellect — source of all forms"}

   ;; ── SELF-AWARENESS (Avicenna's Floating Man) ─────────
   :self-awareness
   {:level :rational :thinker :avicenna
    :kernel-sig [:void :i-am]
    :parents [:rational-soul]
    :description "Proven by the Floating Man: awareness persists without any input"}

   ;; ── HOFFMAN'S ADDITIONS ──────────────────────────────
   :conscious-agent
   {:level :all :thinker :hoffman
    :kernel-sig [:world-state :experience-action-cycle]
    :parents [:consciousness]
    :children [:perception-kernel :decision-kernel :action-kernel]
    :description "C = ⟨(X,𝒳), (G,𝒢), P, D, A, N⟩ — the mathematical atom"}

   :perception-kernel
   {:level :all :thinker :hoffman
    :kernel-sig [:world-state :experience]
    :parents [:conscious-agent]
    :description "P: W × 𝒳 → [0,1] — how the world becomes experience"}

   :decision-kernel
   {:level :all :thinker :hoffman
    :kernel-sig [:experience :action]
    :parents [:conscious-agent]
    :description "D: X × 𝒢 → [0,1] — how experience becomes intention"}

   :action-kernel
   {:level :all :thinker :hoffman
    :kernel-sig [:action :world-state]
    :parents [:conscious-agent]
    :description "A: G × 𝒲 → [0,1] — how intention reshapes the world"}})

;; ════════════════════════════════════════════════════════════════════
;; TAXONOMY QUERIES
;; ════════════════════════════════════════════════════════════════════

(defn ancestors
  "All ancestors of a faculty (transitive closure of :parents)."
  [faculty-kw]
  (loop [queue (vec (:parents (get faculty-graph faculty-kw)))
         seen  #{}]
    (if (empty? queue)
      seen
      (let [f (first queue)
            node (get faculty-graph f)]
        (recur (into (rest queue)
                     (remove seen (:parents node)))
               (conj seen f))))))

(defn descendants
  "All descendants of a faculty (transitive closure of :children)."
  [faculty-kw]
  (loop [queue (vec (:children (get faculty-graph faculty-kw)))
         seen  #{}]
    (if (empty? queue)
      seen
      (let [f (first queue)
            node (get faculty-graph f)]
        (recur (into (rest queue)
                     (remove seen (:children node)))
               (conj seen f))))))

(defn faculties-at-level
  "All faculties belonging to a given ontological level."
  [level-kw]
  (into {} (filter (fn [[_ v]] (= level-kw (:level v))) faculty-graph)))

(defn kernel-signature
  "Get the Markov kernel signature [from → to] for a faculty."
  [faculty-kw]
  (:kernel-sig (get faculty-graph faculty-kw)))
