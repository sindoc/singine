(ns singine.camel.context
  "Apache Camel CamelContext lifecycle — governed start/stop.

   Design principles (from Apache Commons best practices):
   · Single CamelContext per JVM process (singleton, held in atom).
   · All routes registered before start! is called.
   · Stop via stop! — blocks until all in-flight exchanges complete.
   · Health check via healthy? — reports route status.

   Isolation layer:
   · context.clj holds the CamelContext atom.
   · routes.clj adds routes to it before start.
   · mail.clj calls (producer-template) / (consumer-template) after start.

   Rails convention analogy:
   · context = the Rails application object (config/application.rb)
   · routes = config/routes.rb
   · start! = rails server
   · stop! = Ctrl-C / SIGTERM handler

   URN: urn:singine:camel:context"
  (:require [singine.pos.lambda :as lam]
            [clojure.tools.logging :as log])
  (:import [org.apache.camel.impl DefaultCamelContext]
           [org.apache.camel CamelContext]
           [org.apache.camel.builder RouteBuilder]))

;; ── Singleton CamelContext ────────────────────────────────────────────────────

;; Holds the single CamelContext for this JVM. nil until start! is called.
(defonce ^:private ctx-atom (atom nil))

;; ── Lifecycle ─────────────────────────────────────────────────────────────────

(defn make-context
  "Create a new DefaultCamelContext with singine defaults.
   Does NOT start it — call start! after adding routes."
  []
  (doto (DefaultCamelContext.)
    (.setName "singine-camel")
    (.disableJMX)))

(defn add-routes!
  "Add a Camel RouteBuilder (or seq of RouteBuilders) to ctx before start.
   Idempotent: safe to call multiple times with different builders."
  [^CamelContext ctx route-builder-or-seq]
  (let [builders (if (sequential? route-builder-or-seq)
                   route-builder-or-seq
                   [route-builder-or-seq])]
    (doseq [^RouteBuilder b builders]
      (.addRoutes ctx b))
    ctx))

(defn start!
  "Start the CamelContext. Stores it in ctx-atom.
   Governed by auth — returns a zero-arg thunk.
   Call (thunk) to actually start.

   Usage:
     ((start! auth))
     ;; → {:ok true :context-name \"singine-camel\" :routes N :time ...}"
  [auth]
  (lam/govern auth
    (fn [t]
      (let [ctx (or @ctx-atom (make-context))]
        (when-not (= (.getStatus ctx)
                     org.apache.camel.ServiceStatus/Started)
          (log/info "singine-camel: starting CamelContext")
          (.start ctx)
          (reset! ctx-atom ctx))
        {:ok           true
         :context-name (.getName ctx)
         :routes       (count (.getRoutes ctx))
         :status       (str (.getStatus ctx))
         :time         (select-keys t [:iso :path])}))))

(defn stop!
  "Stop the CamelContext gracefully (waits for in-flight exchanges).
   Governed by auth — returns a zero-arg thunk."
  [auth]
  (lam/govern auth
    (fn [t]
      (if-let [^CamelContext ctx @ctx-atom]
        (do (log/info "singine-camel: stopping CamelContext")
            (.stop ctx)
            (reset! ctx-atom nil)
            {:ok true :status "stopped" :time (select-keys t [:iso :path])})
        {:ok false :reason "no active CamelContext" :time (select-keys t [:iso :path])}))))

;; ── Accessors ─────────────────────────────────────────────────────────────────

(defn context
  "Return the active CamelContext, or nil if not started."
  []
  @ctx-atom)

(defn healthy?
  "True if the CamelContext is started and all routes are running."
  []
  (if-let [^CamelContext ctx @ctx-atom]
    (and (= (.getStatus ctx) org.apache.camel.ServiceStatus/Started)
         (every? #(= (.getStatus %) org.apache.camel.ServiceStatus/Started)
                 (.getRoutes ctx)))
    false))

(defn producer-template
  "Return a Camel ProducerTemplate from the active CamelContext.
   Used by CamelMailAdapter.java and singine.net.edge to send exchanges."
  []
  (when-let [^CamelContext ctx @ctx-atom]
    (.createProducerTemplate ctx)))

(defn consumer-template
  "Return a Camel ConsumerTemplate from the active CamelContext.
   Used for polling-style IMAP consumption."
  []
  (when-let [^CamelContext ctx @ctx-atom]
    (.createConsumerTemplate ctx)))

(defn start-server!
  "Start the Camel context with all routes and block until SIGTERM.
   Designed to be called from singine.server.main (clojure -M:serve).
   Prints connection info for iOS devices on the local network.

   opts:
     :http-port (default 8080)
     :dry-run   (default false)"
  [auth opts]
  (lam/govern auth
    (fn [t]
      (let [http-port (:http-port opts 8080)
            dry-run   (:dry-run opts false)
            result    ((start! auth))]
        {:ok        (:ok result)
         :port      http-port
         :dry-run   dry-run
         :routes    (:routes result)
         :status    (:status result)
         :bind-addr "0.0.0.0"
         :time      (select-keys t [:iso :path])}))))

;; ── Status summary ─────────────────────────────────────────────────────────────

(defn status-summary
  "Return a map describing the current CamelContext status.
   Safe to call even if the context is not started."
  []
  (if-let [^CamelContext ctx @ctx-atom]
    {:started true
     :name    (.getName ctx)
     :status  (str (.getStatus ctx))
     :routes  (mapv (fn [r] {:id     (.getId r)
                              :status (str (.getStatus r))
                              :uri    (str (.getEndpointUrl r))})
                    (.getRoutes ctx))}
    {:started false
     :name    "singine-camel"
     :status  "not-started"
     :routes  []}))
