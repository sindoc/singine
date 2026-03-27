(ns singine.net.edge
  "singine edge HTTP client — governed requests to the singine-edge node.

   The singine-edge node is a Spring Boot + Apache Camel HTTP service that
   exposes mail messages and system health over HTTP (Rails REST conventions).

   REST API (singine-edge, port 8080 by default):
     GET  /health               → {:ok :status :routes :time}
     GET  /messages             → {:ok :messages :count :time}
     GET  /messages?search=term → {:ok :messages :count :search :time}
     GET  /messages/:id         → {:ok :message :uid :time}
     POST /messages             → {:ok :sent :from :to :subject :time}
     POST /messages/:id/forward → {:ok :forwarded :uid :to :time}
     POST /messages/snap        → {:ok :snapped :count :files :time}

   Rails naming conventions (consistent with singine.net.mail):
     :index   → GET  /messages                (search/list)
     :show    → GET  /messages/:id            (fetch by UID)
     :create  → POST /messages                (send)
     :forward → POST /messages/:id/forward    (forward)
     :snap    → POST /messages/snap           (git snapshot)

   Design:
     - Pure JDK HttpClient (java.net.http) — no extra dependencies
     - Every function returns a governed zero-arg thunk (lam/govern pattern)
     - Dry-run support: :dry-run true returns synthetic results without HTTP
     - 30-second timeout on all requests (consistent with singine.net.mail)
     - JSON response bodies parsed via clojure.data.json
     - Content-Type: application/json (sent + expected)

   Configuration (via opts map):
     :edge-host   — edge node host (default \"localhost\")
     :edge-port   — edge node port (default 8080)
     :edge-scheme — \"http\" or \"https\" (default \"http\")
     :dry-run     — synthetic results, no HTTP (default false)

   URN: urn:singine:net:edge"
  (:require [singine.pos.lambda :as lam]
            [clojure.data.json  :as json]
            [clojure.string     :as str])
  (:import [java.net.http HttpClient HttpRequest HttpResponse
            HttpResponse$BodyHandlers HttpRequest$BodyPublishers]
           [java.net URI]
           [java.time Duration]))

;; ── HTTP client factory ───────────────────────────────────────────────────────

(defn- make-http-client
  "Build a JDK HttpClient with 30-second connect timeout."
  []
  (-> (HttpClient/newBuilder)
      (.connectTimeout (Duration/ofSeconds 30))
      (.build)))

;; ── Base URL builder ─────────────────────────────────────────────────────────

(defn- base-url
  "Construct the base URL for the edge node from opts."
  [{:keys [edge-scheme edge-host edge-port]
    :or   {edge-scheme "http" edge-host "localhost" edge-port 8080}}]
  (str edge-scheme "://" edge-host ":" edge-port))

(defn- edge-uri
  "Build a URI for the given path + optional query string."
  [opts path & {:keys [query-params]}]
  (let [base  (base-url opts)
        qs    (when (seq query-params)
                (str "?" (str/join "&"
                           (map (fn [[k v]] (str (name k) "=" v))
                                query-params))))]
    (URI/create (str base path (or qs "")))))

;; ── HTTP helpers ──────────────────────────────────────────────────────────────

(defn- get-request
  "Build an HTTP GET request with 30-second timeout."
  [^URI uri]
  (-> (HttpRequest/newBuilder uri)
      (.GET)
      (.header "Accept" "application/json")
      (.timeout (Duration/ofSeconds 30))
      (.build)))

(defn- post-request
  "Build an HTTP POST request with JSON body and 30-second timeout."
  [^URI uri body-map]
  (let [body-str (json/write-str body-map)]
    (-> (HttpRequest/newBuilder uri)
        (.POST (HttpRequest$BodyPublishers/ofString body-str))
        (.header "Content-Type" "application/json")
        (.header "Accept" "application/json")
        (.timeout (Duration/ofSeconds 30))
        (.build))))

(defn- send-request
  "Send an HTTP request; return parsed JSON body or error map."
  [^HttpClient client ^HttpRequest req]
  (try
    (let [^HttpResponse resp (.send client req (HttpResponse$BodyHandlers/ofString))
          status (.statusCode resp)
          body   (.body resp)
          parsed (when (and body (not (str/blank? body)))
                   (try (json/read-str body :key-fn keyword)
                        (catch Exception _ {:raw body})))]
      (if (< status 400)
        (assoc (or parsed {}) :http-status status)
        {:ok false :http-status status :error (str "HTTP " status) :body body}))
    (catch java.net.ConnectException e
      {:ok false :error "edge-node-unreachable" :detail (ex-message e)})
    (catch java.util.concurrent.TimeoutException e
      {:ok false :error "edge-request-timeout"  :detail (ex-message e)})
    (catch Exception e
      {:ok false :error "edge-request-failed"   :detail (ex-message e)})))

;; ── Synthetic responses (dry-run) ────────────────────────────────────────────

(defn- synthetic-health [t]
  {:ok      true
   :status  "UP"
   :service "singine-edge"
   :routes  ["singine.mail.messages.index"
             "singine.mail.messages.show"
             "singine.edge.health"]
   :dry-run true
   :time    (select-keys t [:iso :path])})

(defn- synthetic-messages [search t]
  {:ok       true
   :messages [{:uid "1001" :subject "Synthetic invoice" :from "test@localhost"
               :folder "INBOX" :dry-run true}
              {:uid "1002" :subject "Synthetic report"  :from "test@localhost"
               :folder "INBOX" :dry-run true}]
   :count    2
   :search   (or search "")
   :dry-run  true
   :time     (select-keys t [:iso :path])})

(defn- synthetic-message [uid t]
  {:ok      true
   :message {:uid uid :subject "Synthetic message" :from "test@localhost"
             :body-preview "This is a synthetic email body for dry-run testing."
             :folder "INBOX" :dry-run true}
   :uid     uid
   :dry-run true
   :time    (select-keys t [:iso :path])})

(defn- synthetic-send [opts t]
  {:ok      true
   :sent    true
   :from    (get opts :from "test@localhost")
   :to      (get opts :to "")
   :subject (get opts :subject "(no subject)")
   :dry-run true
   :time    (select-keys t [:iso :path])})

(defn- synthetic-snap [t]
  {:ok      true
   :snapped true
   :count   2
   :files   ["mail/INBOX/1001.eml.xml" "mail/INBOX/1002.eml.xml"]
   :dry-run true
   :time    (select-keys t [:iso :path])})

;; ── health! ───────────────────────────────────────────────────────────────────

(defn health!
  "Governed: GET /health — check the edge node is up and routes are running.

   opts:
     :edge-host  :edge-port  :edge-scheme
     :dry-run    if true, return synthetic health result

   Returns governed thunk. On call:
     {:ok true :status \"UP\" :service \"singine-edge\" :routes [...] :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (if (boolean (get opts :dry-run false))
        (synthetic-health t)
        (let [client (make-http-client)
              uri    (edge-uri opts "/health")
              req    (get-request uri)
              resp   (send-request client req)]
          (assoc resp :time (select-keys t [:iso :path])))))))

;; ── messages! (index) ────────────────────────────────────────────────────────

(defn messages!
  "Governed: GET /messages — list or search messages from the edge node.

   opts:
     :edge-host  :edge-port  :edge-scheme
     :search     optional search term (passed as ?search= query parameter)
     :max        max results (default 20, passed as ?max= query parameter)
     :dry-run    if true, return synthetic message list

   Returns governed thunk. On call:
     {:ok true :messages [...] :count N :search term :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [search  (get opts :search "")
            max-r   (int (get opts :max 20))
            dry-run (boolean (get opts :dry-run false))]
        (if dry-run
          (synthetic-messages search t)
          (let [client (make-http-client)
                qp     (cond-> {:max max-r}
                          (not (str/blank? search)) (assoc :search search))
                uri    (edge-uri opts "/messages" :query-params qp)
                req    (get-request uri)
                resp   (send-request client req)]
            (assoc resp :time (select-keys t [:iso :path]))))))))

;; ── message! (show) ──────────────────────────────────────────────────────────

(defn message!
  "Governed: GET /messages/:id — fetch a single message by UID.

   opts:
     :edge-host  :edge-port  :edge-scheme
     :uid        IMAP UID string to fetch
     :dry-run    if true, return synthetic message

   Returns governed thunk. On call:
     {:ok true :message {...} :uid uid :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [uid     (get opts :uid "")
            dry-run (boolean (get opts :dry-run false))]
        (if dry-run
          (synthetic-message uid t)
          (let [client (make-http-client)
                uri    (edge-uri opts (str "/messages/" uid))
                req    (get-request uri)
                resp   (send-request client req)]
            (assoc resp :time (select-keys t [:iso :path]))))))))

;; ── send-message! (create) ───────────────────────────────────────────────────

(defn send-message!
  "Governed: POST /messages — send an email via the edge node.

   opts:
     :edge-host  :edge-port  :edge-scheme
     :from       sender address
     :to         recipient address
     :subject    message subject
     :body       plain-text body
     :dry-run    if true, return synthetic send result

   Returns governed thunk. On call:
     {:ok true :sent true :from :to :subject :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [dry-run (boolean (get opts :dry-run false))]
        (if dry-run
          (synthetic-send opts t)
          (let [client   (make-http-client)
                uri      (edge-uri opts "/messages")
                body-map {:from    (get opts :from "")
                          :to      (get opts :to "")
                          :subject (get opts :subject "(no subject)")
                          :body    (get opts :body "")}
                req      (post-request uri body-map)
                resp     (send-request client req)]
            (assoc resp :time (select-keys t [:iso :path]))))))))

;; ── forward-message! ─────────────────────────────────────────────────────────

(defn forward-message!
  "Governed: POST /messages/:id/forward — forward a message to a recipient.

   opts:
     :edge-host  :edge-port  :edge-scheme
     :uid        IMAP UID of message to forward
     :to         recipient address for forwarded message
     :dry-run    if true, return synthetic result

   Returns governed thunk. On call:
     {:ok true :forwarded true :uid uid :to to :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [uid     (get opts :uid "")
            to      (get opts :to "")
            dry-run (boolean (get opts :dry-run false))]
        (if dry-run
          {:ok true :forwarded true :uid uid :to to
           :dry-run true :time (select-keys t [:iso :path])}
          (let [client   (make-http-client)
                uri      (edge-uri opts (str "/messages/" uid "/forward"))
                body-map {:to to}
                req      (post-request uri body-map)
                resp     (send-request client req)]
            (assoc resp :time (select-keys t [:iso :path]))))))))

;; ── snap! ────────────────────────────────────────────────────────────────────

(defn snap!
  "Governed: POST /messages/snap — trigger a git snapshot via the edge node.

   opts:
     :edge-host  :edge-port  :edge-scheme
     :dry-run    if true, return synthetic snap result

   Returns governed thunk. On call:
     {:ok true :snapped true :count N :files [...] :time {...}}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [dry-run (boolean (get opts :dry-run false))]
        (if dry-run
          (synthetic-snap t)
          (let [client   (make-http-client)
                uri      (edge-uri opts "/messages/snap")
                req      (post-request uri {})
                resp     (send-request client req)]
            (assoc resp :time (select-keys t [:iso :path]))))))))

;; ── edge! — top-level dispatcher ─────────────────────────────────────────────

(defn edge!
  "Governed top-level EDGE opcode entry point.

   op (with Rails naming aliases):
     :health                    — GET  /health
     :index  / :messages        — GET  /messages
     :show   / :message         — GET  /messages/:id
     :create / :send            — POST /messages
     :forward                   — POST /messages/:id/forward
     :snap                      — POST /messages/snap

   opts: see individual functions above.
   Add :edge-host :edge-port :edge-scheme to specify the edge node.
   Add :dry-run true for offline testing."
  [auth op opts]
  (lam/govern auth
    (fn [t]
      (let [resolved-op (case op
                          :messages :index
                          :message  :show
                          :send     :create
                          op)
            sub-thunk
            (case resolved-op
              :health  (health!          auth opts)
              :index   (messages!        auth opts)
              :show    (message!         auth opts)
              :create  (send-message!    auth opts)
              :forward (forward-message! auth opts)
              :snap    (snap!            auth opts)
              nil)]
        (if sub-thunk
          (sub-thunk)
          {:ok    false
           :error (str "Unknown edge op: " op
                       ". Use :health :index :show :create :forward :snap"
                       " (aliases: :messages :message :send)")
           :time  (select-keys t [:iso :path])})))))
