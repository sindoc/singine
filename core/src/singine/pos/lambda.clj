(ns singine.pos.lambda
  "Personal Operating System — governed lambda engine.

   Every executable unit in singine:pos is a governed lambda:

     (cons auth λ(t))

   where:
     auth  = {:agent uri, :activity proto, :token eval-fn}
     λ(t)  = a function of the time dimension t (Joda-Time compatible)
     t     = singine:time — a record that is Unicode-calendar-aware

   Execution sequence
   ──────────────────
     1. validate auth token against a prototypical activity
     2. if authorised  → apply λ to t, return result
     3. if denied      → return {:denied true, :agent agent, :reason reason}

   Auth is evaluated as a Markov kernel over {authorised, denied}:
     P(authorised | agent, activity, token) ∈ [0,1]
   A threshold θ (default 0.5) collapses the distribution to a decision.

   The λ arg list [f e f d g] maps to Hoffman's 6-tuple positions:
     f → perception kernel  P  (filter)
     e → experience space   X  (experience)
     f → (reused) filter    P  (second pass)
     d → decision kernel    D  (decide)
     g → action kernel      A  (govern / act)")

;; ── time record ─────────────────────────────────────────────────────────────

(defrecord SingineTime
  [instant        ;; java.time.Instant
   iso            ;; \"2026-02-21T11:50:00+01:00\"
   tz             ;; \"Europe/Brussels\"
   decade         ;; \"2020s\"
   path           ;; \"today/2020s/2026/02/21\"
   unicode-epoch  ;; Long — days since Unicode epoch (code-point 0 → date 0)
   ])

(defn now []
  (let [inst  (java.time.Instant/now)
        zdt   (java.time.ZonedDateTime/ofInstant inst (java.time.ZoneId/systemDefault))
        year  (.getYear zdt)
        month (format "%02d" (.getMonthValue zdt))
        day   (format "%02d" (.getDayOfMonth zdt))
        dec   (str (- year (mod year 10)) "s")]
    (->SingineTime
      inst
      (str zdt)
      (str (java.time.ZoneId/systemDefault))
      dec
      (str "today/" dec "/" year "/" month "/" day)
      (.toEpochMilli inst))))

;; ── auth record ─────────────────────────────────────────────────────────────

(defrecord Auth
  [agent      ;; URI string — urn:sindoc:singine:... or @handle
   activity   ;; keyword  — :anonymous-function | :read | :write | :connect
   token-fn   ;; (fn [agent activity t] -> p ∈ [0.0,1.0])
   theta      ;; threshold, default 0.5
   ])

(defn make-auth
  ([agent activity]
   (make-auth agent activity (fn [_ _ _] 1.0) 0.5))
  ([agent activity token-fn theta]
   (->Auth agent activity token-fn theta)))

;; ── governed lambda ──────────────────────────────────────────────────────────

(defn govern
  "Wrap a function f of time t with auth validation.
   Returns a zero-argument thunk; call it to execute.

   Usage:
     (def exec (govern auth (fn [t] {:result (str (:path t))})))
     (exec)   ;; -> {:result \"today/2020s/2026/02/21\"} or {:denied true ...}"
  [^Auth auth f]
  (fn []
    (let [t   (now)
          p   ((:token-fn auth) (:agent auth) (:activity auth) t)]
      (if (>= p (:theta auth))
        (f t)
        {:denied  true
         :agent   (:agent auth)
         :activity (:activity auth)
         :p       p
         :theta   (:theta auth)}))))

;; ── pipeline composition (cons auth λ(t)) ────────────────────────────────────

(defn pipe
  "Compose a sequence of governed lambdas into a pipeline.
   Each λᵢ receives the output of λᵢ₋₁ as its time context.
   Stops on first :denied result."
  [& governed-thunks]
  (fn []
    (reduce
      (fn [acc thunk]
        (if (:denied acc)
          (reduced acc)           ;; short-circuit — auth failed upstream
          (thunk)))
      {}
      governed-thunks)))

;; ── named arg list from the screenshot: (f e f d g) ─────────────────────────

(def ^:private arg-semantics
  "The lambda arg list decoded from the bio URI: l=f,e,f,d,g,"
  {:f :perception-kernel      ;; P — what is filtered from raw input
   :e :experience-space       ;; X — the qualia of the agent
   :d :decision-kernel        ;; D — which action to choose
   :g :action-kernel})        ;; A — the act itself (govern)

(defn decode-arg-list
  "Parse 'f,e,f,d,g,' -> [{:arg :f :role :perception-kernel} ...]"
  [s]
  (->> (clojure.string/split s #",")
       (remove empty?)
       (map (fn [a]
              (let [k (keyword a)]
                {:arg  k
                 :role (get arg-semantics k :unknown)})))))

;; ── entry point — execute the contact lambda from the screenshot ──────────────

(defn -main [& _]
  (let [auth  (make-auth "urn:sindoc:singine:a.c.cn.async"
                         :anonymous-function
                         ;; token-fn: governed=true means full authority granted
                         (fn [_ _ _] 1.0)
                         0.5)
        args  (decode-arg-list "f,e,f,d,g,")
        exec  (govern auth
                (fn [t]
                  {:uri     "urn:sindoc:singine:a.c.cn.async"
                   :args    args
                   :time    (select-keys t [:iso :tz :decade :path])
                   :result  :authorised}))]
    (println (exec))))
