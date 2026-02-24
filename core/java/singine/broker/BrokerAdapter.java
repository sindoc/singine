package singine.broker;

import org.apache.commons.lang3.StringUtils;
import org.apache.commons.codec.digest.DigestUtils;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * singine BrokerAdapter — Java isolation layer over Kafka and RabbitMQ.
 *
 * <p>Design principles (Apache Commons best practices):
 * <ul>
 *   <li>Same isolation pattern as MailClient / CamelMailAdapter.</li>
 *   <li>Two brokers abstracted behind a single interface: Kafka (streaming)
 *       and RabbitMQ (AMQP async transforms).</li>
 *   <li>:dry-run → returns synthetic ACK without network I/O.</li>
 *   <li>Checksum (SHA-256 via DigestUtils) on every message body.</li>
 *   <li>All methods are static — callers hold no state.</li>
 * </ul>
 *
 * <p>Broker identifiers:
 * <ul>
 *   <li>{@code "kafka"}    — Kafka topic publish/consume (TCP, event streaming)</li>
 *   <li>{@code "rabbitmq"} — RabbitMQ exchange publish / queue consume (AMQP)</li>
 * </ul>
 *
 * <p>Kafka topics used by singine:
 * <ul>
 *   <li>singine.inbound.email</li>
 *   <li>singine.inbound.api</li>
 *   <li>singine.processed.text</li>
 *   <li>singine.processed.triples</li>
 *   <li>singine.events.activity</li>
 *   <li>singine.events.gdpr</li>
 *   <li>singine.events.release</li>
 *   <li>singine.edge.sync</li>
 *   <li>singine.hf.publish</li>
 *   <li>singine.broker.dead   (DLQ)</li>
 * </ul>
 *
 * <p>RabbitMQ exchanges used by singine:
 * <ul>
 *   <li>singine.transforms  (direct) — OCR, wavelet, LaTeX-SVG jobs</li>
 *   <li>singine.build       (fanout) — Ant build triggers</li>
 *   <li>singine.notifications (topic) — daily POS check-in</li>
 * </ul>
 *
 * <p>URN: urn:singine:broker
 */
public class BrokerAdapter {

    // ── Constants ─────────────────────────────────────────────────────────────

    public static final String BROKER_KAFKA    = "kafka";
    public static final String BROKER_RABBITMQ = "rabbitmq";

    // Kafka default connection (may be overridden by env KAFKA_BROKERS)
    public static final String DEFAULT_KAFKA_BROKERS = "localhost:9092";

    // RabbitMQ default connection (may be overridden by env RABBIT_HOST)
    public static final String DEFAULT_RABBIT_HOST = "localhost";
    public static final int    DEFAULT_RABBIT_PORT = 5672;

    // ── publish() ─────────────────────────────────────────────────────────────

    /**
     * Publish a message to either Kafka or RabbitMQ.
     *
     * @param broker      "kafka" or "rabbitmq"
     * @param destination Kafka topic name OR RabbitMQ exchange name
     * @param routingKey  Kafka partition key OR RabbitMQ routing key (may be empty)
     * @param body        Message body (plain text or serialised JSON)
     * @param headers     Optional headers / message attributes (may be null)
     * @param dryRun      If true, return synthetic ACK without network I/O
     * @return Map containing: ok, broker, destination, message-id, checksum,
     *         dry-run flag, and optional error
     */
    public static Map<String, Object> publish(
            String broker,
            String destination,
            String routingKey,
            String body,
            Map<String, String> headers,
            boolean dryRun) {

        Map<String, Object> result = new HashMap<>();
        String messageId = UUID.randomUUID().toString();
        String checksum  = DigestUtils.sha256Hex(StringUtils.defaultIfBlank(body, ""));

        result.put("message-id", messageId);
        result.put("checksum",   checksum);
        result.put("broker",     StringUtils.defaultIfBlank(broker, BROKER_KAFKA));
        result.put("destination", StringUtils.defaultIfBlank(destination, ""));
        result.put("routing-key", StringUtils.defaultIfBlank(routingKey, ""));
        result.put("dry-run",    dryRun);

        if (dryRun) {
            result.put("ok",      true);
            result.put("status",  "synthetic-ack");
            result.put("offset",  -1L);
            return result;
        }

        // Live publish — delegated to Camel ProducerTemplate in the Clojure layer.
        // BrokerAdapter.java acts as the pure-Java contract; actual network I/O
        // is performed by singine.broker.kafka / singine.broker.rabbit via Camel.
        // This method returns a pre-populated result map; the Clojure caller
        // fills in the offset/delivery-tag after the Camel exchange completes.
        result.put("ok",     true);
        result.put("status", "pending-camel-dispatch");
        return result;
    }

    // ── consume() ────────────────────────────────────────────────────────────

    /**
     * Consume one message from either Kafka or RabbitMQ.
     *
     * @param broker      "kafka" or "rabbitmq"
     * @param source      Kafka topic name OR RabbitMQ queue name
     * @param consumerGroup Kafka consumer group (ignored for RabbitMQ)
     * @param timeoutMs   Max wait in ms (0 = return immediately if empty)
     * @param dryRun      If true, return synthetic message without network I/O
     * @return Map containing: ok, broker, source, body, headers, message-id, checksum
     */
    public static Map<String, Object> consume(
            String broker,
            String source,
            String consumerGroup,
            int    timeoutMs,
            boolean dryRun) {

        Map<String, Object> result = new HashMap<>();
        result.put("broker",         StringUtils.defaultIfBlank(broker, BROKER_KAFKA));
        result.put("source",         StringUtils.defaultIfBlank(source, ""));
        result.put("consumer-group", StringUtils.defaultIfBlank(consumerGroup, "singine-core"));
        result.put("timeout-ms",     timeoutMs);
        result.put("dry-run",        dryRun);

        if (dryRun) {
            String syntheticBody = "{\"event\":\"singine.test\",\"dry-run\":true}";
            String messageId     = UUID.randomUUID().toString();
            result.put("ok",         true);
            result.put("body",       syntheticBody);
            result.put("message-id", messageId);
            result.put("checksum",   DigestUtils.sha256Hex(syntheticBody));
            result.put("status",     "synthetic-message");
            result.put("offset",     -1L);
            return result;
        }

        // Live consume — delegated to Camel ConsumerTemplate in the Clojure layer.
        result.put("ok",     true);
        result.put("status", "pending-camel-consume");
        result.put("body",   null);
        return result;
    }

    // ── dead-letter() ────────────────────────────────────────────────────────

    /**
     * Route a failed message to the dead-letter queue / topic.
     * DLQ for Kafka: singine.broker.dead
     * DLQ for RabbitMQ: bound to singine.transforms exchange with routing key "dead"
     *
     * @param originalBroker      the broker that originally received the message
     * @param originalDestination the original topic / exchange
     * @param body                original message body
     * @param reason              error description
     * @param dryRun              synthetic mode
     * @return Map with ok, dlq-destination, message-id, reason
     */
    public static Map<String, Object> deadLetter(
            String originalBroker,
            String originalDestination,
            String body,
            String reason,
            boolean dryRun) {

        String dlqDestination = BROKER_KAFKA.equals(originalBroker)
                ? "singine.broker.dead"
                : "singine.transforms";
        String dlqRoutingKey  = BROKER_KAFKA.equals(originalBroker) ? "" : "dead";

        Map<String, Object> dlqBody = new HashMap<>();
        dlqBody.put("original-broker",      originalBroker);
        dlqBody.put("original-destination", originalDestination);
        dlqBody.put("reason",               StringUtils.defaultIfBlank(reason, "unknown"));
        dlqBody.put("original-checksum",    DigestUtils.sha256Hex(
                StringUtils.defaultIfBlank(body, "")));

        return publish(originalBroker, dlqDestination, dlqRoutingKey,
                dlqBody.toString(), null, dryRun);
    }

    // ── topicUrn() ───────────────────────────────────────────────────────────

    /**
     * Return the singine URN for a broker destination.
     * urn:singine:kafka:topic:<topicName>
     * urn:singine:rabbitmq:exchange:<exchangeName>
     */
    public static String destinationUrn(String broker, String destination) {
        String safeDest = StringUtils.defaultIfBlank(destination, "unknown")
                .toLowerCase().replace('.', ':');
        if (BROKER_RABBITMQ.equals(broker)) {
            return "urn:singine:rabbitmq:exchange:" + safeDest;
        }
        return "urn:singine:kafka:topic:" + safeDest;
    }
}
