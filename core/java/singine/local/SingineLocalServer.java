package singine.local;

import com.sun.net.httpserver.*;
import singine.auth.JwsToken;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.util.*;
import java.util.concurrent.Executors;

/**
 * Embedded HTTP server for singine.local at port 2000.
 *
 * Implemented with JDK's com.sun.net.httpserver.HttpServer (no external deps).
 * Routes mirror the Camel-Jetty route convention from singine.camel.routes:
 *   singine.<layer>.<resource>.<action>
 *
 * Routes:
 *   GET  /health        — always 200; no auth required
 *   GET  /catalog       — XML catalog fragment; CATALOG_READER or API_CONSUMER
 *   GET  /dns           — DNS management XML; CATALOG_READER or API_CONSUMER
 *   GET  /trusted       — list all trusted individuals; ADMIN only
 *   POST /request       — governed request; API_CONSUMER or SSH_OPERATOR
 *   GET  /bridge        — cortex bridge stub; CORTEX_BRIDGE_USER
 *   GET  /ssh/access    — SSH access check with key-pair info; SSH_OPERATOR
 *
 * Auth:
 *   - Protected routes require: Authorization: Bearer <jws-token>
 *   - HS256 tokens verified with SingineLocal.TEST_JWT_SECRET
 *   - RS256 tokens verified with the individual's stored publicKeyPem
 *   - Role-based access checked via TrustedIndividual.canAccessRoute()
 *
 * The server holds an in-memory SQLite connection seeded with master data.
 * Tests may pass their own pre-seeded Connection to the constructor.
 */
public final class SingineLocalServer {

    private final HttpServer server;
    private final int        boundPort;
    private final Connection db;
    private final boolean    ownsDb;

    // ── Construction ──────────────────────────────────────────────────────────

    /**
     * Create and bind the server.  Finds a free port starting at
     * {@link SingineLocal#DEFAULT_PORT}.  Caller must invoke {@link #start()}.
     *
     * @param db pre-seeded SQLite connection; if null an in-memory DB is created
     */
    public SingineLocalServer(Connection db) throws Exception {
        this.boundPort = SingineLocalDns.findAvailablePort(SingineLocal.DEFAULT_PORT);
        this.server    = HttpServer.create(new InetSocketAddress("127.0.0.1", boundPort), 0);
        this.server.setExecutor(Executors.newFixedThreadPool(4));

        if (db != null) {
            this.db     = db;
            this.ownsDb = false;
        } else {
            Class.forName("org.sqlite.JDBC");
            this.db     = DriverManager.getConnection("jdbc:sqlite::memory:");
            this.ownsDb = true;
            TrustedIndividualStore.createSchema(this.db);
            TrustedIndividualStore.seedMasterData(this.db);
        }

        registerRoutes();
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    public void start() {
        server.start();
    }

    public void stop() {
        server.stop(0);
        if (ownsDb) {
            try { db.close(); } catch (Exception ignored) {}
        }
    }

    public int getPort() {
        return boundPort;
    }

    /** Base URL clients should connect to (127.0.0.1 for socket, singine.local in Host header). */
    public String connectUrl() {
        return SingineLocal.connectUrl(boundPort);
    }

    // ── Route registration ────────────────────────────────────────────────────

    private void registerRoutes() {
        server.createContext("/health",   exchange -> handleHealth(exchange));
        server.createContext("/catalog",  exchange -> handleCatalog(exchange));
        server.createContext("/dns",      exchange -> handleDns(exchange));
        server.createContext("/trusted",  exchange -> handleTrusted(exchange));
        server.createContext("/request",  exchange -> handleRequest(exchange));
        server.createContext("/bridge",   exchange -> handleBridge(exchange));
        server.createContext("/ssh",      exchange -> handleSshAccess(exchange));
    }

    // ── Handlers ─────────────────────────────────────────────────────────────

    private void handleHealth(HttpExchange ex) throws IOException {
        String body = "{\"status\":\"ok\",\"host\":\"" + SingineLocal.DEFAULT_HOST
                    + "\",\"port\":" + SingineLocal.DEFAULT_PORT
                    + ",\"urn\":\"" + SingineLocal.NETWORK_DOMAIN_URN + "\""
                    + ",\"route\":\"" + SingineLocal.ROUTE_HEALTH + "\"}";
        respond(ex, 200, "application/json", body);
    }

    private void handleCatalog(HttpExchange ex) throws IOException {
        TrustedIndividual who = authenticate(ex);
        if (who == null) return;
        if (!who.canAccessRoute(SingineLocal.ROUTE_CATALOG)) {
            respond(ex, 403, "application/json",
                    "{\"error\":\"forbidden\",\"required\":\"CATALOG_READER or API_CONSUMER\"}");
            return;
        }
        respond(ex, 200, "application/xml", SingineLocal.toCatalogXml());
    }

    private void handleDns(HttpExchange ex) throws IOException {
        TrustedIndividual who = authenticate(ex);
        if (who == null) return;
        if (!who.canAccessRoute(SingineLocal.ROUTE_DNS)) {
            respond(ex, 403, "application/json", "{\"error\":\"forbidden\"}");
            return;
        }
        respond(ex, 200, "application/xml", SingineLocalDns.toDnsXml());
    }

    private void handleTrusted(HttpExchange ex) throws IOException {
        TrustedIndividual who = authenticate(ex);
        if (who == null) return;
        if (!who.canAccessRoute(SingineLocal.ROUTE_TRUSTED_INDEX)) {
            respond(ex, 403, "application/json",
                    "{\"error\":\"forbidden\",\"required\":\"ADMIN\"}");
            return;
        }
        try {
            List<TrustedIndividual> all = TrustedIndividualStore.findAll(db);
            StringBuilder xml = new StringBuilder("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n");
            xml.append("<trusted-individuals urn=\"").append(SingineLocal.TRUSTED_STORE_URN).append("\">\n");
            for (TrustedIndividual ti : all) xml.append(indent(ti.toXml(), 2));
            xml.append("</trusted-individuals>\n");
            respond(ex, 200, "application/xml", xml.toString());
        } catch (Exception e) {
            respond(ex, 500, "application/json", "{\"error\":\"" + e.getMessage() + "\"}");
        }
    }

    private void handleRequest(HttpExchange ex) throws IOException {
        if (!"POST".equalsIgnoreCase(ex.getRequestMethod())) {
            respond(ex, 405, "application/json", "{\"error\":\"method not allowed\"}");
            return;
        }
        TrustedIndividual who = authenticate(ex);
        if (who == null) return;
        if (!who.canAccessRoute(SingineLocal.ROUTE_REQUEST_CREATE)) {
            respond(ex, 403, "application/json",
                    "{\"error\":\"forbidden\",\"required\":\"API_CONSUMER or SSH_OPERATOR\"}");
            return;
        }
        String body    = readBody(ex);
        String ts      = java.time.Instant.now().toString();
        String reqUrn  = "urn:singine:request:" + UUID.randomUUID();
        String respUrn = "urn:singine:response:" + UUID.randomUUID();

        String responseXml =
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
          + "<singine-response>\n"
          + "  <request-urn>" + reqUrn + "</request-urn>\n"
          + "  <response-urn>" + respUrn + "</response-urn>\n"
          + "  <principal-urn>" + who.getUrn() + "</principal-urn>\n"
          + "  <role>" + who.getRole().name().toLowerCase().replace('_', '-') + "</role>\n"
          + "  <ts>" + ts + "</ts>\n"
          + "  <host>" + SingineLocal.DEFAULT_HOST + "</host>\n"
          + "  <port>" + SingineLocal.DEFAULT_PORT + "</port>\n"
          + "  <catalog-urn>" + SingineLocal.CATALOG_URN + "</catalog-urn>\n"
          + "  <route>" + SingineLocal.ROUTE_REQUEST_CREATE + "</route>\n"
          + "  <outcome>\n"
          + "    <type>SUCCESS</type>\n"
          + "    <ultimate-metric>\n"
          + "      <formula>usage_value + business_value - platform_cost</formula>\n"
          + "    </ultimate-metric>\n"
          + "  </outcome>\n"
          + "  <echo><![CDATA[" + body.replace("]]>", "]]]]><![CDATA[>") + "]]></echo>\n"
          + "</singine-response>\n";

        respond(ex, 200, "application/xml", responseXml);
    }

    private void handleBridge(HttpExchange ex) throws IOException {
        TrustedIndividual who = authenticate(ex);
        if (who == null) return;
        if (!who.canAccessRoute(SingineLocal.ROUTE_BRIDGE)) {
            respond(ex, 403, "application/json",
                    "{\"error\":\"forbidden\",\"required\":\"CORTEX_BRIDGE_USER\"}");
            return;
        }
        // Stub: mirrors the Camel /bridge?action=sources response shape
        String action = queryParam(ex, "action", "sources");
        String json = "{\"route\":\"" + SingineLocal.ROUTE_BRIDGE + "\""
                    + ",\"bridge-urn\":\"" + SingineLocal.CORTEX_BRIDGE_URN + "\""
                    + ",\"action\":\"" + action + "\""
                    + ",\"principal\":\"" + who.getUrn() + "\""
                    + ",\"sources\":[{\"urn\":\"urn:singine:source:sqlite:local\","
                    + "\"type\":\"sqlite\",\"path\":\":memory:\"}]}";
        respond(ex, 200, "application/json", json);
    }

    private void handleSshAccess(HttpExchange ex) throws IOException {
        TrustedIndividual who = authenticate(ex);
        if (who == null) return;
        if (!who.canAccessRoute(SingineLocal.ROUTE_SSH_ACCESS)) {
            respond(ex, 403, "application/json",
                    "{\"error\":\"forbidden\",\"required\":\"SSH_OPERATOR\"}");
            return;
        }
        String xml =
            "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
          + "<ssh-access>\n"
          + "  <principal-urn>" + who.getUrn() + "</principal-urn>\n"
          + "  <ssh-policy-urn>" + SingineLocal.SSH_POLICY_URN + "</ssh-policy-urn>\n"
          + "  <cortex-bridge-urn>" + SingineLocal.CORTEX_BRIDGE_URN + "</cortex-bridge-urn>\n"
          + "  <public-key-pem>" + (who.getPublicKeyPem().isEmpty() ? "not-yet-set" : who.getPublicKeyPem()) + "</public-key-pem>\n"
          + "  <collibra-catalog>\n"
          + "    <asset assetType=\"SshAccessGrant\" collibraId=\"\" name=\"" + who.getName() + "\"/>\n"
          + "  </collibra-catalog>\n"
          + "  <granted>true</granted>\n"
          + "  <route>" + SingineLocal.ROUTE_SSH_ACCESS + "</route>\n"
          + "</ssh-access>\n";
        respond(ex, 200, "application/xml", xml);
    }

    // ── Auth ──────────────────────────────────────────────────────────────────

    /**
     * Verify the Bearer token and look up the individual in the DB.
     * Writes 401 and returns null on failure.
     *
     * Token verification:
     *   - Tries HS256 first (shared secret).
     *   - On failure tries RS256 using the individual's stored public key
     *     (individual id must be in the "sub" claim for RS256 lookup).
     */
    private TrustedIndividual authenticate(HttpExchange ex) throws IOException {
        String header = ex.getRequestHeaders().getFirst("Authorization");
        if (header == null || !header.startsWith("Bearer ")) {
            respond(ex, 401, "application/json",
                    "{\"error\":\"unauthorized\",\"hint\":\"Bearer token required\"}");
            return null;
        }
        String token = header.substring("Bearer ".length()).trim();
        Map<String, Object> claims;
        try {
            claims = JwsToken.verifyHS256(SingineLocal.TEST_JWT_SECRET, token);
        } catch (Exception hsFailure) {
            // HS256 failed — try RS256 using sub claim to locate the individual's public key
            try {
                // Decode payload to extract sub without full verification
                String sub = extractSubUnchecked(token);
                if (sub == null) throw new SecurityException("no sub claim");
                Optional<TrustedIndividual> candidate = TrustedIndividualStore.findById(db, sub);
                if (candidate.isEmpty() || candidate.get().getPublicKeyPem().isEmpty())
                    throw new SecurityException("no public key registered for " + sub);
                java.security.PublicKey pk = pemToPublicKey(candidate.get().getPublicKeyPem());
                claims = JwsToken.verifyRS256(token, pk);
            } catch (Exception rsFailure) {
                respond(ex, 401, "application/json",
                        "{\"error\":\"unauthorized\",\"detail\":\"token verification failed\"}");
                return null;
            }
        }
        String sub = String.valueOf(claims.get("sub"));
        try {
            Optional<TrustedIndividual> ti = TrustedIndividualStore.findById(db, sub);
            if (ti.isEmpty()) {
                respond(ex, 401, "application/json",
                        "{\"error\":\"unauthorized\",\"detail\":\"unknown individual: " + sub + "\"}");
                return null;
            }
            return ti.get();
        } catch (Exception e) {
            respond(ex, 500, "application/json", "{\"error\":\"" + e.getMessage() + "\"}");
            return null;
        }
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static void respond(HttpExchange ex, int status, String contentType, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", contentType + "; charset=utf-8");
        ex.getResponseHeaders().set("X-Singine-Host",   SingineLocal.DEFAULT_HOST);
        ex.getResponseHeaders().set("X-Singine-Port",   String.valueOf(SingineLocal.DEFAULT_PORT));
        ex.getResponseHeaders().set("X-Singine-Catalog", SingineLocal.CATALOG_URN);
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream os = ex.getResponseBody()) { os.write(bytes); }
    }

    private static String readBody(HttpExchange ex) throws IOException {
        try (InputStream is = ex.getRequestBody()) {
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    private static String queryParam(HttpExchange ex, String key, String defaultValue) {
        String query = ex.getRequestURI().getQuery();
        if (query == null) return defaultValue;
        for (String part : query.split("&")) {
            String[] kv = part.split("=", 2);
            if (kv.length == 2 && kv[0].equals(key)) return kv[1];
        }
        return defaultValue;
    }

    private static String indent(String xml, int spaces) {
        String pad = " ".repeat(spaces);
        return Arrays.stream(xml.split("\n"))
                     .map(l -> pad + l)
                     .reduce("", (a, b) -> a + b + "\n");
    }

    /** Decode JWT payload without verifying the signature — used only to extract sub for RS256 lookup. */
    private static String extractSubUnchecked(String token) {
        try {
            String[] parts = token.split("\\.");
            if (parts.length < 2) return null;
            byte[] payloadBytes = Base64.getUrlDecoder().decode(parts[1]);
            String payload = new String(payloadBytes, StandardCharsets.UTF_8);
            // minimal extraction: find "sub":"..."
            int idx = payload.indexOf("\"sub\"");
            if (idx < 0) return null;
            int colon = payload.indexOf(':', idx);
            int q1    = payload.indexOf('"', colon + 1);
            int q2    = payload.indexOf('"', q1 + 1);
            return payload.substring(q1 + 1, q2);
        } catch (Exception e) {
            return null;
        }
    }

    /** Parse a PEM-encoded RSA public key into a java.security.PublicKey. */
    private static java.security.PublicKey pemToPublicKey(String pem) throws Exception {
        String stripped = pem
            .replace("-----BEGIN PUBLIC KEY-----", "")
            .replace("-----END PUBLIC KEY-----", "")
            .replaceAll("\\s+", "");
        byte[] der = Base64.getDecoder().decode(stripped);
        java.security.spec.X509EncodedKeySpec spec = new java.security.spec.X509EncodedKeySpec(der);
        return java.security.KeyFactory.getInstance("RSA").generatePublic(spec);
    }
}
