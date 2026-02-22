(ns singine.persona.agents
  "Persona-based conscious agent scenarios.

   Each persona represents a documented human archetype — well-studied
   in psychology, philosophy, and cognitive science — instantiated as
   a Hoffman conscious agent with specific Markov kernels.

   The kernels encode how that persona:
   - Perceives the world (P): what they notice, what they miss
   - Decides on action (D): how experience translates to intention
   - Acts on the world (A): how intention becomes consequence

   The transition probabilities between nodes represent the IMPACT
   of a decision: high probability = strong tendency, low = unlikely.

   Persona types documented in literature:
   - The Philosopher (Aristotle/Avicenna tradition)
   - The Artisan (embodied knowledge, craft)
   - The Guardian (threat-detection, Avicenna's estimation)
   - The Explorer (novelty-seeking, compositive imagination)
   - The Healer (empathic perception, nutritive attention)
   - The Networker (social perception, agent fusion)

   Each persona maps to a specific emphasis within the consciousness
   taxonomy and demonstrates different Markov kernel weightings."
  (:require [singine.consciousness.markov :as markov]))

;; ════════════════════════════════════════════════════════════════════
;; WORLD STATES: The shared environment all personas inhabit
;; ════════════════════════════════════════════════════════════════════

(def world-states
  "Universal world states — the W in every agent's tuple.
   These represent the basic situations a conscious entity encounters."
  [:tranquil      ;; no threat, no opportunity — baseline
   :novel         ;; something new has appeared
   :threatening   ;; potential danger detected
   :opportune     ;; beneficial possibility available
   :ambiguous     ;; meaning unclear — requires disambiguation (CONTEXT)
   :social        ;; other agents present — potential for fusion
   :chaotic])     ;; high entropy — many simultaneous signals

;; ════════════════════════════════════════════════════════════════════
;; EXPERIENCE STATES: What can be perceived
;; ════════════════════════════════════════════════════════════════════

(def experience-states
  "Universal experience states — the X in every agent's tuple.
   Maps to Avicenna's internal senses and Aristotle's faculties."
  [:calm          ;; sensus communis reports nothing notable
   :curious       ;; compositive imagination activated
   :fearful       ;; estimation detects threat
   :eager         ;; desire (orexis) engaged toward opportunity
   :confused      ;; conflicting signals — context needed
   :connected     ;; awareness of other conscious agents
   :overwhelmed]) ;; too many signals — memory overloaded

;; ════════════════════════════════════════════════════════════════════
;; ACTION STATES: What can be done
;; ════════════════════════════════════════════════════════════════════

(def action-states
  "Universal action states — the G in every agent's tuple.
   Maps to Aristotle's deliberation (bouleusis) outcomes."
  [:observe       ;; gather more information (passive intellect)
   :explore       ;; move toward novelty (locomotion + curiosity)
   :retreat       ;; move away from threat (self-preservation)
   :engage        ;; interact with opportunity (active intellect)
   :disambiguate  ;; seek context to resolve confusion
   :connect       ;; fuse with another agent (Hoffman composition)
   :rest])        ;; withdraw to baseline (nutritive restoration)

;; ════════════════════════════════════════════════════════════════════
;; PERSONA DEFINITIONS
;; ════════════════════════════════════════════════════════════════════

(defn philosopher-agent
  "The Philosopher — weighted toward observation and disambiguation.
   Dominant faculty: rational soul (nous), deliberation (bouleusis).
   Avicenna's acquired intellect is their natural state.

   P: sees ambiguity everywhere, perceives novelty as curiosity
   D: almost always chooses to observe or disambiguate
   A: actions tend to preserve tranquility or create novelty"
  []
  (markov/make-agent
    experience-states action-states world-states
    ;; P: world → experience (how the philosopher perceives)
    ;;        calm  curio fear  eager confus conn  overwh
    [[0.60  0.15  0.02  0.05  0.10  0.05  0.03]   ;; tranquil → mostly calm
     [0.05  0.70  0.02  0.08  0.10  0.03  0.02]   ;; novel → very curious
     [0.10  0.10  0.30  0.02  0.40  0.03  0.05]   ;; threatening → confused more than afraid
     [0.10  0.30  0.02  0.30  0.15  0.08  0.05]   ;; opportune → curious AND eager
     [0.05  0.20  0.05  0.05  0.55  0.05  0.05]   ;; ambiguous → deeply confused
     [0.10  0.15  0.02  0.08  0.10  0.50  0.05]   ;; social → connected
     [0.05  0.10  0.10  0.03  0.30  0.02  0.40]]  ;; chaotic → confused and overwhelmed

    ;; D: experience → action (how the philosopher decides)
    ;;        obs   expl  retr  enga  disamb conn  rest
    [[0.50  0.10  0.05  0.05  0.15  0.05  0.10]   ;; calm → observe
     [0.30  0.25  0.02  0.10  0.25  0.05  0.03]   ;; curious → observe or disambiguate
     [0.20  0.05  0.30  0.02  0.35  0.03  0.05]   ;; fearful → disambiguate (understand the threat)
     [0.20  0.15  0.02  0.30  0.20  0.08  0.05]   ;; eager → engage but still think
     [0.15  0.05  0.05  0.05  0.60  0.05  0.05]   ;; confused → DISAMBIGUATE (highest)
     [0.20  0.05  0.02  0.10  0.15  0.40  0.08]   ;; connected → connect deeply
     [0.10  0.03  0.15  0.02  0.20  0.05  0.45]]  ;; overwhelmed → rest and observe

    ;; A: action → world (how the philosopher's actions change the world)
    ;;        tranq novel threat opp   ambig social chaotic
    [[0.40  0.20  0.05  0.10  0.15  0.05  0.05]   ;; observe → tends toward tranquil/novel
     [0.10  0.40  0.05  0.20  0.10  0.10  0.05]   ;; explore → creates novelty
     [0.30  0.05  0.10  0.05  0.20  0.05  0.25]   ;; retreat → tranquil but maybe chaotic
     [0.15  0.20  0.05  0.30  0.10  0.15  0.05]   ;; engage → opportunity expands
     [0.25  0.25  0.03  0.15  0.10  0.15  0.07]   ;; disambiguate → resolves to tranquil/novel
     [0.10  0.15  0.05  0.15  0.10  0.40  0.05]   ;; connect → more social
     [0.50  0.10  0.05  0.05  0.10  0.05  0.15]]));; rest → returns to tranquil

(defn guardian-agent
  "The Guardian — weighted toward threat detection and protection.
   Dominant faculty: estimation (al-wahmiyya), Avicenna's key sense.
   The sheep perceives the wolf's hostility without reasoning.

   P: hyper-aware of threats, sees danger in ambiguity
   D: quick to retreat or engage defensively
   A: actions tend to neutralize threats or create safety"
  []
  (markov/make-agent
    experience-states action-states world-states
    ;; P: world → experience
    [[0.40  0.10  0.10  0.05  0.10  0.15  0.10]   ;; tranquil → alert calm
     [0.10  0.20  0.25  0.10  0.15  0.10  0.10]   ;; novel → suspicious
     [0.02  0.03  0.70  0.02  0.08  0.05  0.10]   ;; threatening → VERY fearful
     [0.15  0.10  0.15  0.30  0.10  0.10  0.10]   ;; opportune → cautiously eager
     [0.05  0.10  0.35  0.05  0.25  0.10  0.10]   ;; ambiguous → fear bias
     [0.15  0.10  0.10  0.10  0.10  0.35  0.10]   ;; social → alert but connected
     [0.03  0.05  0.30  0.02  0.15  0.05  0.40]]  ;; chaotic → fear and overwhelm

    ;; D: experience → action
    [[0.30  0.10  0.10  0.10  0.10  0.15  0.15]   ;; calm → observe, ready
     [0.20  0.25  0.10  0.10  0.15  0.10  0.10]   ;; curious → explore cautiously
     [0.10  0.05  0.45  0.15  0.10  0.05  0.10]   ;; fearful → retreat or engage
     [0.15  0.15  0.05  0.35  0.10  0.10  0.10]   ;; eager → engage
     [0.15  0.10  0.25  0.05  0.30  0.05  0.10]   ;; confused → retreat or disambiguate
     [0.15  0.10  0.05  0.10  0.10  0.40  0.10]   ;; connected → protect group
     [0.10  0.05  0.30  0.05  0.10  0.10  0.30]]  ;; overwhelmed → retreat and rest

    ;; A: action → world
    [[0.35  0.15  0.10  0.10  0.10  0.10  0.10]   ;; observe → stable
     [0.15  0.30  0.10  0.15  0.10  0.10  0.10]   ;; explore → novelty
     [0.40  0.05  0.15  0.05  0.10  0.10  0.15]   ;; retreat → tranquil
     [0.20  0.10  0.15  0.20  0.10  0.15  0.10]   ;; engage → opportunity or threat
     [0.25  0.15  0.10  0.15  0.15  0.10  0.10]   ;; disambiguate → clearer
     [0.15  0.10  0.05  0.15  0.10  0.35  0.10]   ;; connect → social
     [0.50  0.05  0.05  0.05  0.10  0.10  0.15]]));; rest → tranquil

(defn explorer-agent
  "The Explorer — weighted toward novelty-seeking and imagination.
   Dominant faculty: compositive imagination (al-mutakhayyila).
   Creates golden mountains from stored images.

   P: sees opportunity and novelty in everything
   D: almost always explores or engages
   A: actions tend to create novelty and diversity"
  []
  (markov/make-agent
    experience-states action-states world-states
    ;; P: world → experience
    [[0.30  0.30  0.02  0.15  0.10  0.08  0.05]   ;; tranquil → restless curiosity
     [0.05  0.60  0.02  0.20  0.05  0.05  0.03]   ;; novel → VERY curious
     [0.10  0.15  0.20  0.10  0.15  0.10  0.20]   ;; threatening → curious even about danger
     [0.05  0.25  0.02  0.50  0.05  0.08  0.05]   ;; opportune → VERY eager
     [0.10  0.35  0.05  0.10  0.20  0.10  0.10]   ;; ambiguous → curious (not confused)
     [0.10  0.20  0.02  0.15  0.08  0.40  0.05]   ;; social → connected and curious
     [0.05  0.25  0.10  0.10  0.15  0.05  0.30]]  ;; chaotic → curious but overwhelmed

    ;; D: experience → action
    [[0.15  0.35  0.02  0.15  0.10  0.15  0.08]   ;; calm → explore!
     [0.10  0.50  0.02  0.15  0.10  0.08  0.05]   ;; curious → EXPLORE
     [0.15  0.15  0.25  0.10  0.15  0.10  0.10]   ;; fearful → still might explore
     [0.05  0.25  0.02  0.45  0.08  0.10  0.05]   ;; eager → engage and explore
     [0.10  0.30  0.05  0.10  0.25  0.10  0.10]   ;; confused → explore to understand
     [0.10  0.20  0.02  0.15  0.08  0.40  0.05]   ;; connected → explore together
     [0.10  0.15  0.15  0.05  0.10  0.05  0.40]]  ;; overwhelmed → forced rest

    ;; A: action → world
    [[0.20  0.30  0.05  0.15  0.10  0.10  0.10]   ;; observe → novelty emerging
     [0.05  0.45  0.05  0.20  0.10  0.10  0.05]   ;; explore → MORE novelty
     [0.30  0.10  0.15  0.10  0.15  0.05  0.15]   ;; retreat → tranquil
     [0.10  0.25  0.05  0.30  0.10  0.15  0.05]   ;; engage → opportunity
     [0.15  0.30  0.05  0.20  0.10  0.10  0.10]   ;; disambiguate → novelty
     [0.10  0.20  0.05  0.15  0.10  0.30  0.10]   ;; connect → social novelty
     [0.35  0.20  0.05  0.10  0.10  0.10  0.10]]));; rest → recharges into tranquil

(defn healer-agent
  "The Healer — weighted toward empathic perception and restoration.
   Dominant faculty: nutritive soul (threptikon) elevated to consciousness.
   Also strong in sensus communis — reads the whole situation.

   P: hyper-aware of suffering and imbalance
   D: chooses connection and restoration
   A: actions tend to restore tranquility"
  []
  (markov/make-agent
    experience-states action-states world-states
    ;; P: world → experience
    [[0.45  0.10  0.05  0.10  0.05  0.20  0.05]   ;; tranquil → calm, connected
     [0.15  0.25  0.05  0.15  0.10  0.25  0.05]   ;; novel → curious about others
     [0.05  0.05  0.20  0.05  0.10  0.40  0.15]   ;; threatening → feels others' fear
     [0.10  0.15  0.03  0.25  0.07  0.35  0.05]   ;; opportune → connected eagerness
     [0.10  0.10  0.10  0.05  0.20  0.30  0.15]   ;; ambiguous → reaches for connection
     [0.15  0.10  0.05  0.10  0.05  0.50  0.05]   ;; social → VERY connected
     [0.05  0.05  0.15  0.03  0.15  0.20  0.37]]  ;; chaotic → overwhelmed but connected

    ;; D: experience → action
    [[0.20  0.10  0.02  0.10  0.08  0.30  0.20]   ;; calm → connect and rest
     [0.15  0.15  0.02  0.15  0.13  0.30  0.10]   ;; curious → connect to learn
     [0.10  0.05  0.10  0.05  0.10  0.40  0.20]   ;; fearful → connect despite fear
     [0.10  0.10  0.02  0.25  0.08  0.35  0.10]   ;; eager → connect and engage
     [0.15  0.05  0.05  0.05  0.20  0.35  0.15]   ;; confused → connect to clarify
     [0.10  0.05  0.02  0.15  0.08  0.50  0.10]   ;; connected → STAY connected
     [0.10  0.03  0.10  0.02  0.10  0.25  0.40]]  ;; overwhelmed → rest with others

    ;; A: action → world
    [[0.40  0.15  0.03  0.10  0.07  0.15  0.10]   ;; observe → calming presence
     [0.20  0.25  0.05  0.15  0.10  0.15  0.10]   ;; explore → gentle discovery
     [0.45  0.05  0.05  0.05  0.10  0.15  0.15]   ;; retreat → deep tranquility
     [0.20  0.15  0.03  0.25  0.07  0.25  0.05]   ;; engage → social opportunity
     [0.30  0.15  0.03  0.15  0.07  0.20  0.10]   ;; disambiguate → clarity
     [0.20  0.10  0.03  0.15  0.07  0.40  0.05]   ;; connect → MORE social
     [0.50  0.05  0.03  0.07  0.10  0.15  0.10]]));; rest → deep tranquility

(defn networker-agent
  "The Networker — weighted toward agent fusion and social dynamics.
   Dominant faculty: Hoffman's agent composition operation.
   This persona naturally fuses with other agents.

   P: perceives social opportunities in everything
   D: biased toward connection and engagement
   A: actions create social configurations"
  []
  (markov/make-agent
    experience-states action-states world-states
    ;; P: world → experience
    [[0.25  0.15  0.03  0.15  0.07  0.30  0.05]   ;; tranquil → seeking connection
     [0.10  0.20  0.03  0.20  0.07  0.35  0.05]   ;; novel → social curiosity
     [0.10  0.05  0.15  0.05  0.10  0.40  0.15]   ;; threatening → seeks allies
     [0.05  0.10  0.03  0.30  0.07  0.40  0.05]   ;; opportune → social opportunity
     [0.10  0.10  0.05  0.10  0.15  0.40  0.10]   ;; ambiguous → asks others
     [0.10  0.10  0.03  0.12  0.05  0.55  0.05]   ;; social → HYPER connected
     [0.05  0.05  0.10  0.05  0.10  0.35  0.30]]  ;; chaotic → seeks group

    ;; D: experience → action
    [[0.10  0.10  0.02  0.15  0.08  0.45  0.10]   ;; calm → connect
     [0.10  0.15  0.02  0.15  0.08  0.40  0.10]   ;; curious → connect and explore
     [0.10  0.05  0.15  0.05  0.10  0.40  0.15]   ;; fearful → seek group safety
     [0.05  0.10  0.02  0.25  0.08  0.45  0.05]   ;; eager → connect and engage
     [0.10  0.05  0.05  0.05  0.15  0.50  0.10]   ;; confused → ask the network
     [0.05  0.05  0.02  0.10  0.08  0.60  0.10]   ;; connected → DEEPEN connection
     [0.10  0.03  0.10  0.02  0.05  0.30  0.40]]  ;; overwhelmed → rest in group

    ;; A: action → world
    [[0.25  0.15  0.05  0.10  0.10  0.25  0.10]   ;; observe → social awareness
     [0.10  0.20  0.05  0.15  0.10  0.30  0.10]   ;; explore → find connections
     [0.30  0.05  0.10  0.05  0.10  0.25  0.15]   ;; retreat → to group
     [0.10  0.15  0.05  0.20  0.05  0.35  0.10]   ;; engage → social opportunity
     [0.15  0.15  0.05  0.15  0.10  0.30  0.10]   ;; disambiguate → social clarity
     [0.05  0.10  0.03  0.15  0.07  0.55  0.05]   ;; connect → STRONGLY social
     [0.40  0.05  0.05  0.05  0.10  0.20  0.15]]));; rest → social tranquil

;; ════════════════════════════════════════════════════════════════════
;; PERSONA REGISTRY
;; ════════════════════════════════════════════════════════════════════

(def persona-registry
  "All documented personas with their dominant faculties and descriptions."
  {:philosopher {:constructor philosopher-agent
                 :dominant-faculty :rational-soul
                 :avicenna-emphasis :acquired-intellect
                 :aristotle-emphasis :deliberation
                 :hoffman-kernel-bias :perception
                 :description "Seeks understanding through observation and disambiguation"
                 :wikipedia "https://en.wikipedia.org/wiki/Philosopher"}

   :guardian    {:constructor guardian-agent
                 :dominant-faculty :estimation
                 :avicenna-emphasis :estimation
                 :aristotle-emphasis :desire
                 :hoffman-kernel-bias :perception
                 :description "Protects through threat detection and rapid response"
                 :wikipedia "https://en.wikipedia.org/wiki/Guardian"}

   :explorer    {:constructor explorer-agent
                 :dominant-faculty :compositive-imagination
                 :avicenna-emphasis :compositive-imagination
                 :aristotle-emphasis :locomotion
                 :hoffman-kernel-bias :action
                 :description "Seeks novelty through movement and recombination"
                 :wikipedia "https://en.wikipedia.org/wiki/Explorer"}

   :healer      {:constructor healer-agent
                 :dominant-faculty :sensus-communis
                 :avicenna-emphasis :sensus-communis
                 :aristotle-emphasis :nutritive-soul
                 :hoffman-kernel-bias :perception
                 :description "Restores balance through empathic connection"
                 :wikipedia "https://en.wikipedia.org/wiki/Healer"}

   :networker   {:constructor networker-agent
                 :dominant-faculty :conscious-agent
                 :avicenna-emphasis :sensus-communis
                 :aristotle-emphasis :common-sense
                 :hoffman-kernel-bias :action
                 :description "Creates composite agents through social fusion"
                 :wikipedia "https://en.wikipedia.org/wiki/Facilitator"}})

(defn instantiate-persona
  "Create a conscious agent from a persona keyword."
  [persona-kw]
  (when-let [spec (get persona-registry persona-kw)]
    ((:constructor spec))))
