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
           [org.apache.camel.model RouteDefinition]))

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
                        "&consumer.bridgeErrorHandler=true"))]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from from-uri)
          (routeId "singine.mail.messages.index")
          (process (reify org.apache.camel.Processor
                     (process [_ ^Exchange ex]
                       (let [msg  (.getIn ex)
                             subj (or (.getHeader msg "Subject" String) "(no subject)")
                             from (or (.getHeader msg "From" String) "unknown")
                             uid  (str (System/currentTimeMillis))]
                         (log/debugf "singine.mail.messages.index: from=%s subj=%s" from subj)
                         ;; Build minimal XML envelope
                         (let [xml (str "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
                                        "<mail-batch xmlns=\"urn:singine:mail\" count=\"1\">"
                                        "<mail uid=\"" uid "\" folder=\"" folder "\">"
                                        "<from>" from "</from>"
                                        "<subject>" subj "</subject>"
                                        "</mail></mail-batch>")]
                           (.setBody msg xml)
                           (.setHeader msg "Content-Type" "application/xml")
                           (.setHeader msg "singine.mail.uid" uid))))))
          (to "direct:singine.mail.inbound")
          (end))))))

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
  [{:keys [http-port dry-run]
    :or   {http-port 8080 dry-run false}}]
  (let [from-uri (if dry-run
                   "timer:singine.edge.mock?period=10000&repeatCount=1"
                   (str "jetty:http://0.0.0.0:" http-port "/messages"
                        "?httpMethodRestrict=GET"
                        "&enableCORS=true"))]
    (route-builder
      (fn [^RouteBuilder rb]
        (.. rb
          (from from-uri)
          (routeId "singine.edge.messages.index")
          (process (reify org.apache.camel.Processor
                     (process [_ ^Exchange ex]
                       ;; Extract query param: ?search=invoice
                       (let [params (.getHeader (.getIn ex)
                                                "CamelHttpQuery" String)
                             search (when params
                                      (second (re-find #"search=([^&]+)" params)))]
                         (.setHeader (.getIn ex)
                                     "singine.mail.search"
                                     (or search ""))))))
          (to "direct:singine.mail.search")
          ;; Wrap response in JSON array
          (process (reify org.apache.camel.Processor
                     (process [_ ^Exchange ex]
                       (let [body (str (.getBody (.getIn ex)))]
                         (.setBody (.getIn ex)
                                   (str "{\"messages\":[" body "]}"))
                         (.setHeader (.getIn ex)
                                     "Content-Type"
                                     "application/json")))))
          (end))))))

;; ── Health check route: singine.edge.health ──────────────────────────────────

(defn health-route
  "HTTP health check — Rails: GET /health → HealthController#show.
   Returns 200 OK with JSON {\"status\":\"ok\",\"context\":\"started\"}.

   config keys:
     :http-port (default 8080)"
  [{:keys [http-port dry-run]
    :or   {http-port 8080 dry-run false}}]
  (let [from-uri (if dry-run
                   "timer:singine.health.mock?period=10000&repeatCount=1"
                   (str "jetty:http://0.0.0.0:" http-port "/health"
                        "?httpMethodRestrict=GET"))]
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
   (health-route       config)])
