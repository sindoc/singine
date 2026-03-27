(ns singine.server.main
  "singine local network server — entry point for `clojure -M:serve`.

   Starts Apache Camel (embedded Jetty) on 0.0.0.0:8080 and blocks
   until SIGTERM. All routes are CORS-enabled for iOS devices on the
   same local network.

   Routes exposed:
     GET /health       — ping (always available)
     GET /bridge       — SQLite bridge (sources/search/entity/sparql/graphql/latest-changes)
     GET /messages     — mail search/list
     GET /cap          — machine capability profile
     GET /loc/:iata    — resolve IATA → URN + timezone
     POST /loc         — correlate location + action (LAC engine)
     GET /timez        — timezone query (?cities=BRU,NYC)
     GET /backlog      — web backlog (when 16.H is implemented)

   Usage:
     clojure -M:serve
     clojure -M:serve --port 9090
     clojure -M:serve --dry-run

   iOS connection (same LAN):
     curl http://<mac-ip>:8080/health
     curl http://<mac-ip>:8080/cap
     curl 'http://<mac-ip>:8080/timez?cities=BRU,NYC'

   URN: urn:singine:server:main"
  (:require [singine.camel.context :as ctx]
            [singine.camel.routes  :as routes]
            [singine.cap.machine   :as cap]
            [singine.pos.lambda    :as lam]
            [clojure.tools.logging :as log])
  (:gen-class))

;; ── Default configuration ─────────────────────────────────────────────────────

(def ^:private default-config
  {:http-port    8080
   :imap-host    "localhost"
   :imap-port    143
   :imap-tls     false
   :smtp-host    "localhost"
   :smtp-port    587
   :kafka-brokers "localhost:9092"
   :dry-run      false})

;; ── Parse CLI args ────────────────────────────────────────────────────────────

(defn- parse-args [args]
  (loop [args args config {}]
    (cond
      (empty? args) config
      (= "--port"    (first args)) (recur (drop 2 args)
                                          (assoc config :http-port
                                                 (Integer/parseInt (second args))))
      (= "--dry-run" (first args)) (recur (rest args)
                                          (assoc config :dry-run true))
      :else (recur (rest args) config))))

;; ── Print connection banner ───────────────────────────────────────────────────

(defn- local-ips []
  "Return non-loopback IPv4 addresses for the local machine."
  (try
    (->> (java.net.NetworkInterface/getNetworkInterfaces)
         enumeration-seq
         (filter #(.isUp %))
         (mapcat #(enumeration-seq (.getInetAddresses %)))
         (filter #(instance? java.net.Inet4Address %))
         (remove #(.isLoopbackAddress %))
         (map #(.getHostAddress %)))
    (catch Exception _ ["<local-ip>"])))

(defn- print-banner [config]
  (let [port (:http-port config)
        ips  (local-ips)]
    (println)
    (println "┌─────────────────────────────────────────────────────────┐")
    (println "│  singine server                                          │")
    (println "│  Apache Camel 4.4 + Jetty                               │")
    (println "└─────────────────────────────────────────────────────────┘")
    (println)
    (println (str "  Listening on: 0.0.0.0:" port))
    (println)
    (println "  Connect from iOS devices (same LAN):")
    (doseq [ip ips]
      (println (str "    curl http://" ip ":" port "/health")))
    (println)
    (println "  Routes:")
    (println (str "    GET  http://0.0.0.0:" port "/health"))
    (println (str "    GET  http://0.0.0.0:" port "/bridge?action=sources"))
    (println (str "    GET  http://0.0.0.0:" port "/cap"))
    (println (str "    GET  http://0.0.0.0:" port "/messages?search=<term>"))
    (println (str "    GET  http://0.0.0.0:" port "/loc/<iata>"))
    (println (str "    GET  http://0.0.0.0:" port "/timez?cities=BRU,NYC"))
    (println)
    (when (:dry-run config)
      (println "  [DRY-RUN: all network I/O is synthetic — no real mail/Kafka]"))
    (println "  Press Ctrl-C to stop.")))

;; ── Shutdown hook ─────────────────────────────────────────────────────────────

(defn- register-shutdown-hook! [stop-fn]
  (.addShutdownHook (Runtime/getRuntime)
                    (Thread. ^Runnable
                             (fn []
                               (println)
                               (println "singine server: shutting down...")
                               (stop-fn)
                               (println "singine server: stopped.")))))

;; ── Main entry point ──────────────────────────────────────────────────────────

(defn -main
  "Start the singine local network server.
   Blocks until SIGTERM or Ctrl-C."
  [& args]
  (let [cli-config (parse-args args)
        config     (merge default-config cli-config)
        ;; Auth for governed calls
        auth       (lam/make-auth "urn:singine:agent:server" :anonymous-function)
        camel-ctx  (ctx/make-context)]

    ;; Probe capabilities
    (println "singine server: detecting machine capabilities...")
    (let [profile ((cap/detect! auth))]
      (println (str "  hostname:     " (:hostname profile)))
      (println (str "  os:           " (get-in profile [:os :family])))
      (println (str "  java:         " (get-in profile [:java :version])))
      (println (str "  capabilities: " (clojure.string/join ", " (map name (:capabilities profile))))))

    ;; Register all routes
    (println "singine server: registering Camel routes...")
    (ctx/add-routes! camel-ctx (routes/all-routes config))

    ;; Register shutdown hook before starting
    (register-shutdown-hook!
      (fn []
        ((ctx/stop! auth))))

    ;; Start Camel context
    (println "singine server: starting Apache Camel...")
    (.start camel-ctx)
    (reset! (var-get (find-var 'singine.camel.context/ctx-atom)) camel-ctx)

    ;; Print banner with connection instructions
    (print-banner config)

    ;; Block main thread until JVM shutdown
    (.. Thread currentThread join)))
