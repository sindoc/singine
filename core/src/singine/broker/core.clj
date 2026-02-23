(ns singine.broker.core
  "singine dual broker — Kafka (streaming) + RabbitMQ (AMQP async).

   All message routing is abstracted behind a single interface. Callers
   do not know which broker handles the message; they only specify
   the destination type (topic vs exchange) and the singine domain.

   Brokers:
     :kafka    — TCP event streaming, Apache Spark integration
     :rabbitmq — AMQP async transforms, build triggers, DLQ

   Kafka topics (all prefixed singine.*):
     singine.inbound.email       ← raw email from /var/mail
     singine.inbound.api         ← API uploads
     singine.processed.text      ← extracted text + metadata
     singine.processed.triples   ← RDF triples
     singine.events.activity     ← activity lifecycle
     singine.events.gdpr         ← GDPR audit records
     singine.events.release      ← git release triggers
     singine.edge.sync           ← edge node synchronisation
     singine.hf.publish          ← HuggingFace publish consumer
     singine.broker.dead         ← dead-letter queue

   RabbitMQ exchanges:
     singine.transforms  (direct) ← OCR, wavelet, LaTeX→SVG jobs
     singine.build       (fanout) ← Ant build triggers
     singine.notifications (topic) ← daily POS check-in

   Design:
     - Every function returns a governed zero-arg thunk (lam/govern pattern)
     - BrokerAdapter.java provides the Java isolation layer
     - Camel routes (singine.camel.routes) handle actual network I/O
     - :dry-run true → synthetic ACK/message, no network
     - URN: urn:singine:broker

   Usage:
     ((publish! auth {:broker :kafka :topic \"singine.inbound.email\" :body msg}))
     ((consume! auth {:broker :rabbitmq :queue \"singine.transforms.ocr\" :timeout-ms 5000}))"
  (:require [singine.pos.lambda :as lam]
            [clojure.string     :as str])
  (:import [singine.broker BrokerAdapter]))

;; ── Kafka topic registry ──────────────────────────────────────────────────────

(def kafka-topics
  "All Kafka topics managed by singine."
  {:inbound-email      "singine.inbound.email"
   :inbound-api        "singine.inbound.api"
   :processed-text     "singine.processed.text"
   :processed-triples  "singine.processed.triples"
   :events-activity    "singine.events.activity"
   :events-gdpr        "singine.events.gdpr"
   :events-release     "singine.events.release"
   :edge-sync          "singine.edge.sync"
   :hf-publish         "singine.hf.publish"
   :dead-letter        "singine.broker.dead"})

;; ── RabbitMQ exchange registry ────────────────────────────────────────────────

(def rabbit-exchanges
  "All RabbitMQ exchanges managed by singine."
  {:transforms     {:name "singine.transforms"     :type "direct"}
   :build          {:name "singine.build"           :type "fanout"}
   :notifications  {:name "singine.notifications"   :type "topic"}})

;; ── Helpers ───────────────────────────────────────────────────────────────────

(defn- java-map->clj
  "Convert a Java Map<String,Object> to a Clojure map with keyword keys."
  [m]
  (reduce (fn [acc [k v]] (assoc acc (keyword k) v)) {} m))

(defn- resolve-destination
  "Resolve a keyword topic/exchange to its string name."
  [broker dest]
  (cond
    (string? dest)  dest
    (keyword? dest)
    (case broker
      :kafka    (get kafka-topics dest (name dest))
      :rabbitmq (get-in rabbit-exchanges [dest :name] (name dest))
      (name dest))
    :else (str dest)))

(defn- broker-str [broker]
  (case broker
    :kafka    "kafka"
    :rabbitmq "rabbitmq"
    (name broker)))

;; ── publish! ─────────────────────────────────────────────────────────────────

(defn publish!
  "Governed: publish a message to either Kafka or RabbitMQ.

   opts:
     :broker       :kafka | :rabbitmq
     :topic        Kafka topic keyword or string (for :kafka)
     :exchange     RabbitMQ exchange keyword or string (for :rabbitmq)
     :routing-key  Kafka partition key OR RabbitMQ routing key (optional)
     :body         Message body string (JSON or plain text)
     :headers      Optional map of string header key→value
     :dry-run      Synthetic ACK if true (default false)

   Returns governed thunk. On call:
     {:ok true :broker :kafka :destination \"singine.inbound.email\"
      :message-id \"<uuid>\" :checksum \"<sha256>\" :dry-run true}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [broker      (get opts :broker :kafka)
            dest-key    (or (get opts :topic) (get opts :exchange) :inbound-email)
            dest-str    (resolve-destination broker dest-key)
            routing-key (str (get opts :routing-key ""))
            body        (str (get opts :body ""))
            dry-run     (boolean (get opts :dry-run false))
            headers     (when-let [h (get opts :headers)]
                          (reduce-kv (fn [m k v] (assoc m (name k) (str v))) {} h))
            result      (BrokerAdapter/publish
                          (broker-str broker)
                          dest-str
                          routing-key
                          body
                          headers
                          dry-run)]
        (assoc (java-map->clj result)
               :time (select-keys t [:iso :path])
               :broker broker
               :destination dest-str)))))

;; ── consume! ─────────────────────────────────────────────────────────────────

(defn consume!
  "Governed: consume one message from Kafka or RabbitMQ.

   opts:
     :broker         :kafka | :rabbitmq
     :topic          Kafka topic keyword or string (for :kafka)
     :queue          RabbitMQ queue name (for :rabbitmq)
     :consumer-group Kafka consumer group (default \"singine-core\")
     :timeout-ms     Max wait in ms (default 5000)
     :dry-run        Synthetic message if true (default false)

   Returns governed thunk. On call:
     {:ok true :broker :kafka :source \"singine.inbound.email\"
      :body \"{...}\" :message-id \"<uuid>\" :checksum \"<sha256>\"}"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [broker    (get opts :broker :kafka)
            src-key   (or (get opts :topic) (get opts :queue) :inbound-email)
            src-str   (resolve-destination broker src-key)
            group     (str (get opts :consumer-group "singine-core"))
            timeout   (int (get opts :timeout-ms 5000))
            dry-run   (boolean (get opts :dry-run false))
            result    (BrokerAdapter/consume
                        (broker-str broker)
                        src-str
                        group
                        timeout
                        dry-run)]
        (assoc (java-map->clj result)
               :time   (select-keys t [:iso :path])
               :broker broker
               :source src-str)))))

;; ── dead-letter! ─────────────────────────────────────────────────────────────

(defn dead-letter!
  "Governed: route a failed message to the DLQ.

   opts:
     :broker       original broker (:kafka | :rabbitmq)
     :destination  original topic / exchange
     :body         original message body
     :reason       error description
     :dry-run      synthetic if true

   DLQ destinations:
     Kafka:    singine.broker.dead
     RabbitMQ: singine.transforms exchange, routing-key 'dead'"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [broker  (get opts :broker :kafka)
            dest    (str (get opts :destination ""))
            body    (str (get opts :body ""))
            reason  (str (get opts :reason "unknown"))
            dry-run (boolean (get opts :dry-run false))
            result  (BrokerAdapter/deadLetter
                      (broker-str broker) dest body reason dry-run)]
        (assoc (java-map->clj result)
               :time (select-keys t [:iso :path]))))))

;; ── broker! — top-level dispatcher ───────────────────────────────────────────

(defn broker!
  "Governed top-level BROKER opcode entry point.

   op:
     :publish     — publish message (Kafka or RabbitMQ)
     :consume     — consume one message
     :dead-letter — route to DLQ

   opts: see individual functions above.
   Always add :dry-run true for offline testing."
  [auth op opts]
  (lam/govern auth
    (fn [t]
      (let [sub-thunk
            (case op
              :publish     (publish!     auth opts)
              :consume     (consume!     auth opts)
              :dead-letter (dead-letter! auth opts)
              nil)]
        (if sub-thunk
          (sub-thunk)
          {:ok    false
           :error (str "Unknown broker op: " op
                       ". Use :publish :consume :dead-letter")
           :time  (select-keys t [:iso :path])})))))

;; ── destination-urn ──────────────────────────────────────────────────────────

(defn destination-urn
  "Return the singine URN for a broker destination.
   urn:singine:kafka:topic:<topicName>
   urn:singine:rabbitmq:exchange:<exchangeName>"
  [broker destination]
  (BrokerAdapter/destinationUrn (broker-str broker) (str destination)))
