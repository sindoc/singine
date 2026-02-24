#!/bin/bash
# edge-entrypoint.sh — singine edge container startup
# Starts the Clojure Camel routes engine (or Spring Boot when built).
set -euo pipefail

echo "singine-edge: starting edge HTTP node"
echo "  CAMEL_MAIL_HOST=${CAMEL_MAIL_HOST:-singine-mail}"
echo "  CAMEL_IMAP_PORT=${CAMEL_IMAP_PORT:-143}"
echo "  CAMEL_SMTP_PORT=${CAMEL_SMTP_PORT:-587}"
echo "  MAIL_USER=${MAIL_USER:-singine}"

# If Spring Boot jar is present (built Maven module), run it
if [ -f /app/edge/target/singine-edge.jar ]; then
  echo "singine-edge: starting Spring Boot jar"
  exec java \
    -DCAMEL_MAIL_HOST="${CAMEL_MAIL_HOST:-singine-mail}" \
    -DCAMEL_IMAP_PORT="${CAMEL_IMAP_PORT:-143}" \
    -DCAMEL_SMTP_PORT="${CAMEL_SMTP_PORT:-587}" \
    -DMAIL_USER="${MAIL_USER:-singine}" \
    -DMAIL_PASS="${MAIL_PASS:-singinepass}" \
    -DKAFKA_BROKERS="${KAFKA_BROKERS:-localhost:9092}" \
    -jar /app/edge/target/singine-edge.jar
fi

# Otherwise: run Clojure Camel routes directly
echo "singine-edge: no Spring Boot jar found, running Clojure Camel routes"
exec clojure -M \
  -e "(require 'singine.camel.context 'singine.camel.routes) \
      (let [cfg {:imap-host (System/getenv \"CAMEL_MAIL_HOST\") \
                 :imap-port (Integer/parseInt (or (System/getenv \"CAMEL_IMAP_PORT\") \"143\")) \
                 :smtp-host (System/getenv \"CAMEL_MAIL_HOST\") \
                 :smtp-port (Integer/parseInt (or (System/getenv \"CAMEL_SMTP_PORT\") \"587\")) \
                 :user (System/getenv \"MAIL_USER\") \
                 :pass (System/getenv \"MAIL_PASS\") \
                 :http-port 8080 :dry-run false} \
            ctx (singine.camel.context/make-context)] \
        (singine.camel.context/add-routes! ctx (singine.camel.routes/all-routes cfg)) \
        (.start ctx) \
        (println \"singine-edge: Camel started on port 8080\") \
        (.addShutdownHook (Runtime/getRuntime) (Thread. #(.stop ctx))) \
        @(promise))"
