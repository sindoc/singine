(ns singine.pos.unicode-time
  "Unicode → Calendar → Timezone → Country chain.

   Each Unicode code point is mapped to:
     1. ISO 639 language code(s) that use scripts containing this character
     2. Countries/regions where those languages are primary
     3. IANA timezones for those countries
     4. A relative calendar date (offset from a chosen epoch)

   The mapping is relative: you supply an epoch and a scale factor,
   and the date floats accordingly — aligned with singine temporal algebra.

   Game theory layer
   ─────────────────
   Each (unicode, country, timezone) triple is a strategy in a 3-player game:
     Player U — chooses a Unicode block (script)
     Player C — chooses a country that uses that script
     Player T — chooses a timezone within that country
   The payoff matrix is the number of speakers: higher = more salient mapping.
   Nash equilibrium = the most globally salient (script, country, tz) triple.

   Markov encoding
   ────────────────
   Transitions between scripts follow a row-stochastic matrix over
   Unicode block adjacency (blocks that share border code points are neighbours).
   This gives a gentle random walk through human writing systems.

   Haskell/Lisp oracle note
   ─────────────────────────
   The chain below is written to be transliterable to Haskell:
     unicode->langs  ::  CodePoint -> [LangCode]
     langs->countries :: LangCode  -> [Country]
     countries->tzs   :: Country   -> [TZ]
     tz->offset       :: TZ -> Epoch -> Scale -> RelativeDate")

;; ── Unicode block table (selected, representative) ───────────────────────────
;; Each entry: [start end block-name script iso639 countries speakers]
(def ^:private unicode-blocks
  "Curated subset. Extend with CLDR data for production."
  [{:start 0x0041 :end 0x007A :block "Basic Latin"
    :script "Latin" :langs ["en" "fr" "de" "es" "pt" "nl" "it"]
    :countries ["US" "GB" "FR" "DE" "ES" "BR" "NL" "BE"]
    :tzs ["America/New_York" "Europe/London" "Europe/Paris"
          "Europe/Berlin" "Europe/Brussels"]
    :speakers 1500000000}

   {:start 0x0600 :end 0x06FF :block "Arabic"
    :script "Arabic" :langs ["ar" "fa" "ur"]
    :countries ["SA" "EG" "IR" "PK" "AE" "BE"]   ;; BE has large Arabic-speaking diaspora
    :tzs ["Asia/Riyadh" "Africa/Cairo" "Asia/Tehran" "Asia/Karachi" "Europe/Brussels"]
    :speakers 422000000}

   {:start 0x0400 :end 0x04FF :block "Cyrillic"
    :script "Cyrillic" :langs ["ru" "uk" "bg" "sr"]
    :countries ["RU" "UA" "BG" "RS"]
    :tzs ["Europe/Moscow" "Europe/Kiev" "Europe/Sofia" "Europe/Belgrade"]
    :speakers 250000000}

   {:start 0x4E00 :end 0x9FFF :block "CJK Unified Ideographs"
    :script "Han" :langs ["zh" "ja" "ko"]
    :countries ["CN" "JP" "KR" "TW" "SG"]
    :tzs ["Asia/Shanghai" "Asia/Tokyo" "Asia/Seoul" "Asia/Taipei"]
    :speakers 1400000000}

   {:start 0x0900 :end 0x097F :block "Devanagari"
    :script "Devanagari" :langs ["hi" "mr" "ne" "sa"]
    :countries ["IN" "NP"]
    :tzs ["Asia/Kolkata" "Asia/Kathmandu"]
    :speakers 600000000}

   {:start 0x0370 :end 0x03FF :block "Greek"
    :script "Greek" :langs ["el"]
    :countries ["GR" "CY"]
    :tzs ["Europe/Athens" "Asia/Nicosia"]
    :speakers 13000000}

   {:start 0x0590 :end 0x05FF :block "Hebrew"
    :script "Hebrew" :langs ["he" "yi"]
    :countries ["IL"]
    :tzs ["Asia/Jerusalem"]
    :speakers 9000000}

   {:start 0x0C80 :end 0x0CFF :block "Kannada"
    :script "Kannada" :langs ["kn"]
    :countries ["IN"]
    :tzs ["Asia/Kolkata"]
    :speakers 44000000}])

;; ── lookup: code-point → block ───────────────────────────────────────────────

(defn code-point->block
  "Return the block record for a Unicode code point, or nil."
  [cp]
  (first (filter #(and (>= cp (:start %)) (<= cp (:end %)))
                 unicode-blocks)))

;; ── relative date mapping ────────────────────────────────────────────────────

(defn code-point->relative-date
  "Map a Unicode code point to a relative calendar date.

   epoch  — a java.time.LocalDate treated as day 0
   scale  — how many code points equal one day (default 0x100 = 256)

   Returns a java.time.LocalDate."
  ([cp] (code-point->relative-date cp (java.time.LocalDate/of 2000 1 1) 0x100))
  ([cp epoch scale]
   (.plusDays epoch (long (/ cp scale)))))

;; ── strategy record (game theory triple) ─────────────────────────────────────

(defrecord Strategy
  [code-point char-str block langs country tz relative-date speakers])

(defn best-strategy
  "Nash equilibrium: pick the (country, tz) pair with most speakers
   for a given code point. Returns a Strategy."
  [cp]
  (let [block (code-point->block cp)
        date  (code-point->relative-date cp)]
    (if block
      (->Strategy
        cp
        (try (str (char cp)) (catch Exception _ "?"))
        (:block block)
        (:langs block)
        (first (:countries block))       ;; highest-priority country
        (first (:tzs block))             ;; corresponding tz
        date
        (:speakers block))
      {:code-point cp :block :unknown :relative-date date})))

;; ── Markov walk over Unicode blocks ─────────────────────────────────────────
;; Transition matrix: uniform over adjacent blocks (by code-point distance)

(defn- adjacency-weight [a b]
  (let [gap (Math/abs (- (:start a) (:end b)))]
    (if (< gap 0x200) 1.0 0.0)))

(defn markov-step
  "Given a block, return the next block sampled from the adjacency distribution."
  [block]
  (let [weights (map #(adjacency-weight block %) unicode-blocks)
        total   (reduce + weights)]
    (if (zero? total)
      (rand-nth unicode-blocks)
      (let [r (* (rand) total)]
        (loop [blocks unicode-blocks ws weights acc 0.0]
          (if (empty? blocks)
            (last unicode-blocks)
            (let [acc' (+ acc (first ws))]
              (if (>= acc' r)
                (first blocks)
                (recur (rest blocks) (rest ws) acc')))))))))

(defn unicode-walk
  "Walk n steps through Unicode blocks starting from code point cp.
   Returns a lazy sequence of Strategy records."
  [cp n]
  (take n
    (iterate
      (fn [s]
        (let [next-block (markov-step (code-point->block (:code-point s)))]
          (best-strategy (+ (:start next-block)
                            (rand-int (- (:end next-block) (:start next-block)))))))
      (best-strategy cp))))

;; ── the lambda: Unicode → full context ──────────────────────────────────────

(defn unicode->context
  "The core lambda. Given a Unicode code point (as Long),
   return a rich context map:
     {:code-point :char :block :langs :country :tz
      :relative-date :speakers :iso639-primary}

   Pipe this into singine:time for temporal algebra."
  [cp]
  (let [s (best-strategy cp)]
    (assoc s :iso639-primary (first (:langs s)))))

;; ── filtered list: selected chars with full context ─────────────────────────
;; (matches the screenshot lambda arg list: f e f d g)

(defn selected-chars
  "Returns a list of [code char rest] triples for a seq of code points.
   'rest' is the full context map — arbitrary JSON-compatible."
  [code-points]
  (map (fn [cp]
         (let [ctx (unicode->context cp)]
           [cp
            (try (str (char cp)) (catch Exception _ "?"))
            ctx]))
       code-points))

;; ── demo ─────────────────────────────────────────────────────────────────────

(defn -main [& _]
  (let [;; Sample code points spanning the screenshot's implied ethnicities:
        ;; Latin (Sina/Belgium), Arabic (Iranian diaspora), Cyrillic, CJK, Devanagari
        sample [0x0053   ;; S — Latin
                0x0633   ;; س — Arabic (sin)
                0x0421   ;; С — Cyrillic
                0x5C71   ;; 山 — CJK
                0x0938]] ;; स — Devanagari (sa)
    (doseq [[cp ch ctx] (selected-chars sample)]
      (println (format "U+%04X  %-4s  block=%-28s country=%-4s tz=%-25s date=%s"
                       cp ch (:block ctx) (:country ctx) (:tz ctx)
                       (str (:relative-date ctx)))))))
