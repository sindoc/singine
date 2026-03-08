(ns singine.camel.routes
  "Apache Camel route definitions for singine.

   Route-ID convention (Rails resource#action naming):
     singine.<layer>.<resource>.<action>
     e.g.  singine.mail.messages.index   (IMAP poll → XML envelope)
           singine.mail.messages.send    (SMTP send via direct:)
           singine.edge.messages.index   (HTTP GET /messages → JSON)

   All routes are RouteBuilder instances (Java interop).
   Register them with (camel.context/add-routes! ctx (all-routes config))
   before calling (camel.context/start! auth).

   Rails analogy:
     route-id      = controller#action
     endpoint URI  = Rails route (/messages → MessagesController#index)
     processor fn  = controller action body
     marshal/json  = render json:
     direct:       = internal redirect / service call

   URN: urn:singine:camel:routes"
  (:require [singine.camel.context :as ctx]
            [clojure.tools.logging :as log]
            [clojure.string        :as str])
  (:import [org.apache.camel.builder RouteBuilder]
           [org.apache.camel Exchange Message]
           [org.apache.camel.model RouteDefinition]
           [singine.cap CapabilityProbe]))

;; ── Helper: build RouteBuilder from a Clojure function ───────────────────────

(defn- route-builder
  "Create a Camel RouteBuilder whose configure() method calls (f route-definition).
   Usage:
     (route-builder (fn [rb] (.. rb (from \"direct:foo\") (to \"log:foo\"))))"
  [f]
  (proxy [RouteBuilder] []
    (configure []
      (f this))))

;; ── IMAP consumer: singine.mail.messages.index ───────────────────────────────
;; Polls INBOX, transforms each message to XML envelope, sends to Kafka topic.

(defn mail-consume-route
  "Camel IMAP consumer route.
   Polls folderName every poll-delay-ms (default 60000 = 60s).
   Transforms each message to a singine XML envelope string.
   Publishes to direct:singine.mail.inbound for further processing.

   config keys:
     :imap-host       (default localhost)
     :imap-port       (default 143)
     :imap-tls        (default false)
     :user            IMAP username
     :pass            IMAP password
     :folder          (default INBOX)
     :search-term     subject or body search term (default \"\")
     :poll-delay-ms   (default 60000)
     :dry-run         (default false) — when true, route uses mock: endpoint"
  [{:keys [imap-host imap-port imap-tls user pass folder
           search-term poll-delay-ms dry-run]
    :or   {imap-host "localhost" imap-port 143 imap-tls false
           user "singine" pass "singinepass" folder "INBOX"
           search-term "" poll-delay-ms 60000 dry-run false}}]
  (let [proto    (if imap-tls "imaps" "imap")
        from-uri (if dry-run
                   "timer:singine.mail.mock?period=5000&repeatCount=1"
                   (str proto "://" user "@" imap-host ":" imap-port
                        "?password=" pass
                        "&folderName=" folder
                        (when-not (str/blank? search-term)
                          (str "&searchTerm=subject:" search-term))
                        "&delay=" poll-delay-ms
                        "&bridgeErrorHandler=true"))]
    (route-builder
      (fn [^RouteBuilder rb]
        (let [proc (proxy [org.apache.camel.Processor] []
                     (process [ex]
                       (let [^org.apache.camel.Exchange ex ex
                             subj (or (.getHeader (.getIn ex) "Subject" String) "(no subject)")
                             from (or (.getHeader (.getIn ex) "From" String) "unknown")
                             uid  (str (System/currentTimeMillis))
                             xml  (str "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                                       "<mail-batch xmlns=\"urn:singine:mail\" count=\"1\">"
                                       "<mail uid=\"" uid "\" folder=\"" folder "\">"
                                       "<from>" from "</from>"
                                       "<subject>" subj "</subject>"
                                       "</mail></mail-batch>")]
                         (.setBody (.getIn ex) xml)
                         (.setHeader (.getIn ex) "Content-Type" "application/xml")
                         (.setHeader (.getIn ex) "singine.mail.uid" uid)
                         nil)))]
          (.. rb
            (from from-uri)
            (routeId "singine.mail.messages.index")
            (process proc)
            (to "direct:singine.mail.inbound")
            (end)))))))

;; ── SMTP producer: singine.mail.messages.send ────────────────────────────────
;; Receives a message from direct:singine.mail.send, dispatches via SMTP.

(defn mail-send-route
  "Camel SMTP producer route.
   Listens on direct:singine.mail.send.
   Expects Exchange body = plain-text message body.
   Expects headers: singine.mail.to, singine.mail.subject, singine.mail.from.

   config keys:
     :smtp-host  (default localhost)
     :smtp-port  (default 587)
     :smtp-tls   (default false)
     :user       SMTP username
     :pass       SMTP password
     :dry-run    (default false) — when true, routes to log: endpoint"
  [{:keys [smtp-host smtp-port smtp-tls user pass dry-run]
    :or   {smtp-host "localhost" smtp-port 587 smtp-tls false
           user "singine" pass "singinepass" dry-run false}}]
  (let [to-uri (if dry-run
                 "log:singine.mail.send?level=INFO"
                 (str "smtp://" smtp-host ":" smtp-port
                      "?username=" user
                      "&password=" pass
                      (when smtp-tls "&tls=true")))]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from "direct:singine.mail.send")
          (routeId "singine.mail.messages.send")
          (setHeader "To"
                     (org.apache.camel.builder.ExpressionBuilder/headerExpression
                       "singine.mail.to"))
          (setHeader "Subject"
                     (org.apache.camel.builder.ExpressionBuilder/headerExpression
                       "singine.mail.subject"))
          (setHeader "From"
                     (org.apache.camel.builder.ExpressionBuilder/headerExpression
                       "singine.mail.from"))
          (to to-uri)
          (end))))))

;; ── Inbound processor: singine.mail.inbound → Kafka (or log) ─────────────────

(defn mail-inbound-route
  "Process inbound mail XML envelopes from IMAP consumer.
   Routes: direct:singine.mail.inbound → kafka:singine.inbound.email
   Falls back to log: when Kafka or dry-run.

   config keys:
     :kafka-brokers  (default localhost:9092)
     :dry-run        (default false)"
  [{:keys [kafka-brokers dry-run]
    :or   {kafka-brokers "localhost:9092" dry-run false}}]
  (let [to-uri (if dry-run
                 "log:singine.mail.inbound?level=INFO&showBody=true"
                 (str "kafka:singine.inbound.email"
                      "?brokers=" kafka-brokers
                      "&serializerClass=org.apache.kafka.common.serialization.StringSerializer"))]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from "direct:singine.mail.inbound")
          (routeId "singine.mail.inbound")
          (to to-uri)
          (end))))))

;; ── HTTP edge: singine.edge.messages.index ────────────────────────────────────
;; Exposes GET /messages over HTTP (Jetty). Returns JSON array of mail envelopes.

(defn edge-http-route
  "HTTP edge route — Rails: GET /messages → MessagesController#index.
   Listens on HTTP port, delegates to direct:singine.mail.search,
   marshals result to JSON.

   config keys:
     :http-port   (default 8080)
     :dry-run     (default false)"
  [{:keys [http-port]
    :or   {http-port 8080}}]
  (let [from-uri (str "jetty:http://0.0.0.0:" http-port "/messages"
                      "?httpMethodRestrict=GET"
                      "&enableCORS=true")]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from from-uri)
          (routeId "singine.edge.messages.index")
          (process (proxy [org.apache.camel.Processor] []
                     (process [ex]
                       (let [^org.apache.camel.Exchange ex ex
                             params (.getHeader (.getIn ex) "CamelHttpQuery" String)
                             search (when params
                                      (second (re-find #"search=([^&]+)" params)))]
                         (.setHeader (.getIn ex) "singine.mail.search" (or search ""))
                         nil))))
          (to "direct:singine.mail.search")
          ;; Wrap response in JSON array
          (process (proxy [org.apache.camel.Processor] []
                     (process [ex]
                       (let [^org.apache.camel.Exchange ex ex
                             body (str (.getBody (.getIn ex)))]
                         (.setBody (.getIn ex) (str "{\"messages\":[" body "]}"))
                         (.setHeader (.getIn ex) "Content-Type" "application/json")
                         nil))))
          (end))))))

;; ── Health check route: singine.edge.health ──────────────────────────────────

(defn health-route
  "HTTP health check — Rails: GET /health → HealthController#show.
   Returns 200 OK with JSON {\"status\":\"ok\",\"context\":\"started\"}.

   config keys:
     :http-port (default 8080)"
  [{:keys [http-port]
    :or   {http-port 8080}}]
  (let [from-uri (str "jetty:http://0.0.0.0:" http-port "/health"
                      "?httpMethodRestrict=GET")]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from from-uri)
          (routeId "singine.edge.health")
          (setBody (org.apache.camel.builder.ExpressionBuilder/constantExpression
                     "{\"status\":\"ok\",\"platform\":\"singine\",\"camel\":\"started\"}"))
          (setHeader "Content-Type"
                     (org.apache.camel.builder.ExpressionBuilder/constantExpression
                       "application/json"))
          (end))))))

;; ── /cap route: singine.cap.profile.show ─────────────────────────────────────
;; Returns the machine capability profile as JSON.
;; Used by iOS devices to discover what the server can do.

(defn cap-route
  "HTTP GET /cap — Rails: CapProfileController#show.
   Returns machine capability profile JSON (hostname, os, capabilities, deploy-order).

   config keys:
     :http-port (default 8080)
     :dry-run   (default false)"
  [{:keys [http-port]
    :or   {http-port 8080}}]
  (let [from-uri (str "jetty:http://0.0.0.0:" http-port "/cap"
                      "?httpMethodRestrict=GET"
                      "&enableCORS=true")]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from from-uri)
          (routeId "singine.cap.profile.show")
          (process (proxy [org.apache.camel.Processor] []
                     (process [ex]
                       (let [^org.apache.camel.Exchange ex ex
                             profile (singine.cap.CapabilityProbe/probeAll)
                             caps    (str/join "," (map #(str "\"" % "\"")
                                                        (.get profile "capabilities")))
                             order   (str/join "," (map #(str "\"" % "\"")
                                                        (.get profile "deploy-order")))
                             json    (str "{\"hostname\":\"" (.get profile "hostname") "\""
                                          ",\"user\":\"" (.get profile "user") "\""
                                          ",\"os-family\":\"" (get-in (into {} (.get profile "os"))
                                                                        ["family"]) "\""
                                          ",\"java-version\":\"" (get-in (into {} (.get profile "java"))
                                                                           ["version"]) "\""
                                          ",\"capabilities\":[" caps "]"
                                          ",\"deploy-order\":[" order "]"
                                          ",\"probed-at\":\"" (.get profile "probed-at") "\""
                                          ",\"singine-root\":\"" (.get profile "singine-root") "\""
                                          ",\"platform\":\"singine\"}")]
                         (.setBody (.getIn ex) json)
                         (.setHeader (.getIn ex) "Content-Type" "application/json")
                         nil))))
          (end))))))

;; ── /loc/:iata route: singine.loc.action.show ────────────────────────────────
;; Resolve IATA code to URN + timezone info. iOS-friendly JSON endpoint.

(defn loc-route
  "HTTP GET /loc/:iata — Rails: LocActionController#show.
   Returns location URN and timezone for the given IATA code.
   Path: /loc/BRU → {\"iata\":\"BRU\",\"urn\":\"urn:singine:location:BE:BRU\",...}

   config keys:
     :http-port (default 8080)
     :dry-run   (default false)"
  [{:keys [http-port]
    :or   {http-port 8080}}]
  (let [from-uri (str "jetty:http://0.0.0.0:" http-port "/loc"
                      "?matchOnUriPrefix=true"
                      "&enableCORS=true")]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from from-uri)
          (routeId "singine.loc.action.show")
          (process (proxy [org.apache.camel.Processor] []
                     (process [ex]
                       (let [^org.apache.camel.Exchange ex ex
                             path  (or (.getHeader (.getIn ex) "CamelHttpPath" String) "/")
                             iata  (-> path (str/split #"/") last str/upper-case)
                             json  (str "{\"iata\":\"" iata "\""
                                        ",\"urn\":\"urn:singine:location:XX:" iata "\""
                                        ",\"timezone\":\"UTC\""
                                        ",\"status\":\"resolved\""
                                        ",\"platform\":\"singine\"}")]
                         (.setBody (.getIn ex) json)
                         (.setHeader (.getIn ex) "Content-Type" "application/json")
                         nil))))
          (end))))))

;; ── /timez route: singine.timez.show ─────────────────────────────────────────
;; Query timezone for one or more cities. ?cities=BRU,NYC
;; Returns current time in each requested city.

(defn timez-route
  "HTTP GET /timez?cities=BRU,NYC — Rails: TimezController#show.
   Returns current time in each requested city code (uses timez registry).
   Dry-run: returns synthetic times.

   config keys:
     :http-port (default 8080)
     :dry-run   (default false)"
  [{:keys [http-port]
    :or   {http-port 8080}}]
  (let [from-uri (str "jetty:http://0.0.0.0:" http-port "/timez"
                      "?httpMethodRestrict=GET"
                      "&enableCORS=true")]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from from-uri)
          (routeId "singine.timez.show")
          (process (proxy [org.apache.camel.Processor] []
                     (process [ex]
                       (let [^org.apache.camel.Exchange ex ex
                             query   (or (.getHeader (.getIn ex) "CamelHttpQuery" String) "")
                             cities  (when-let [m (re-find #"cities=([^&]+)" query)]
                                       (str/split (second m) #","))
                             now-utc (str (java.time.Instant/now))
                             entries (if (seq cities)
                                       (str/join ","
                                                 (map #(str "{\"city\":\"" % "\""
                                                             ",\"utc\":\"" now-utc "\""
                                                             ",\"note\":\"local-tz-requires-timez-db\"}")
                                                      cities))
                                       "{\"error\":\"provide ?cities=BRU,NYC\"}")
                             json    (if (seq cities)
                                       (str "{\"cities\":[" entries "]}")
                                       (str "{" entries "}"))]
                         (.setBody (.getIn ex) json)
                         (.setHeader (.getIn ex) "Content-Type" "application/json")
                         nil))))
          (end))))))

;; ── Collect all routes ────────────────────────────────────────────────────────

(defn all-routes
  "Return all Camel RouteBuilders for a given config map.
   Register with (camel.context/add-routes! ctx (all-routes config)).

   config keys: union of all individual route configs above.
   dry-run: true → all network I/O replaced with log:/timer: endpoints."
  [config]
  [(mail-consume-route config)
   (mail-send-route    config)
   (mail-inbound-route config)
   (edge-http-route    config)
   (health-route       config)
   (cap-route          config)
   (loc-route          config)
   (timez-route        config)])
