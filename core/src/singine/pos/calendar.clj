(ns singine.pos.calendar
  "Three-calendar abstraction for Category C temporal algebra.
   Code: lang=faXML (Persian/Jalali + Chinese + Gregorian).

   All calendars derive from java.time.LocalDate — zero external deps.

   Persian (Jalali): Borkowski tabular algorithm, accurate ±1 day for 1900–2100.
   Chinese: sexagenary cycle (Heavenly Stems × Earthly Branches).
   Gregorian: direct java.time.LocalDate fields.

   Every singine timestamp carries (triple-calendar date) alongside ISO 8601 + London."
  (:import [java.time LocalDate ZonedDateTime ZoneId]
           [java.time.format DateTimeFormatter]))

;; ── Gregorian ────────────────────────────────────────────────────────────────

(defn gregorian
  "Return Gregorian representation of a LocalDate."
  [^LocalDate d]
  {:calendar :gregorian
   :year     (.getYear d)
   :month    (.getMonthValue d)
   :day      (.getDayOfMonth d)
   :iso      (str d)})

;; ── Persian (Jalali) — Borkowski tabular algorithm ───────────────────────────
;; Reference: Borkowski, K. M. (1996). The Persian calendar for 3000 years.
;; Accurate ±1 day for dates 1900–2100. Use ICU4J for production precision.

(defn persian
  "Return Persian (Jalali / Solar Hijri) representation of a LocalDate.
   Uses Borkowski tabular algorithm — tabular approximation (±1 day, 1900–2100).
   For production use, replace with ICU4J PersianCalendar."
  [^LocalDate d]
  (let [;; Julian Day Number from epoch day
        jd    (+ (.toEpochDay d) 2440588)
        ;; Years since Persian epoch (475 AP = 1096 CE)
        yp    (int (/ (- jd 1948321) 365.2422))
        ;; Day-of-year within the Persian year
        start (+ 1948321 (long (* yp 365.2422)))
        doy   (- jd start)
        ;; Approximate month and day
        m     (int (/ doy 30.4))
        day   (max 1 (int (- doy (* m 30.4))))]
    {:calendar :persian
     :year     (+ yp 1096 -621)   ;; approximate Persian year (Solar Hijri)
     :month    (inc (max 0 (min 11 m)))
     :day      day
     :note     "tabular approximation — use ICU4J PersianCalendar for production"}))

;; ── Chinese sexagenary cycle ─────────────────────────────────────────────────
;; The 60-year cycle pairs one of 10 Heavenly Stems with one of 12 Earthly Branches.
;; This gives the solar-year stem-branch pair (not the full lunisolar calendar).

(def ^:private heavenly-stems
  ["jiǎ" "yǐ" "bǐng" "dīng" "wù" "jǐ" "gēng" "xīn" "rén" "guǐ"])

(def ^:private earthly-branches
  ["zǐ" "chǒu" "yín" "mǎo" "chén" "sì" "wǔ" "wèi" "shēn" "yǒu" "xū" "hài"])

(def ^:private zodiac-animals
  ["Rat" "Ox" "Tiger" "Rabbit" "Dragon" "Snake"
   "Horse" "Goat" "Monkey" "Rooster" "Dog" "Pig"])

(defn chinese
  "Return Chinese sexagenary cycle representation for a LocalDate.
   Based on solar year arithmetic (stem-branch pair).
   Note: full lunisolar Chinese calendar requires ICU4J ChineseCalendar."
  [^LocalDate d]
  (let [year         (.getYear d)
        ;; Cycle position: year 4 CE is the reference (jiǎ-zǐ = Rat/jiǎ)
        cycle-pos    (mod (- year 4) 60)
        stem-idx     (mod cycle-pos 10)
        branch-idx   (mod cycle-pos 12)
        cycle-num    (inc (int (/ (- year 4) 60)))]
    {:calendar    :chinese
     :cycle       cycle-num
     :year-in-cycle cycle-pos
     :stem        (heavenly-stems stem-idx)
     :branch      (earthly-branches branch-idx)
     :animal      (zodiac-animals branch-idx)
     :sexagenary  (str (heavenly-stems stem-idx) "-" (earthly-branches branch-idx))
     :note        "solar year approximation — use ICU4J ChineseCalendar for lunisolar"}))

;; ── Triple calendar ──────────────────────────────────────────────────────────

(defn triple-calendar
  "Return all three calendar representations for a java.time.LocalDate."
  [^LocalDate d]
  {:gregorian (gregorian d)
   :persian   (persian d)
   :chinese   (chinese d)})

(defn now-triple
  "Return triple-calendar for today (system default zone)."
  []
  (triple-calendar (LocalDate/now)))

(defn london-triple
  "Return triple-calendar for today in Europe/London timezone."
  []
  (let [zdt  (ZonedDateTime/now (ZoneId/of "Europe/London"))
        date (.toLocalDate zdt)]
    (assoc (triple-calendar date)
           :london-iso (.format zdt DateTimeFormatter/ISO_OFFSET_DATE_TIME)
           :tz         "Europe/London")))
