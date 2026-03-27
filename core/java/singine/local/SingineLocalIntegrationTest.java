package singine.local;

import singine.auth.CertAuthority;
import singine.auth.JwsToken;

import java.security.KeyPair;
import java.sql.*;
import java.util.*;

/**
 * Integration test: singine.local default port 2000
 * ===================================================
 * Self-contained Java test with a main() runner (no JUnit dependency).
 *
 * Coverage:
 *   TC-01  Health check              — GET /health             (no auth)
 *   TC-02  XML catalog               — GET /catalog            (Bob: API_CONSUMER, HS256)
 *   TC-03  DNS management            — GET /dns                (Bob: API_CONSUMER, HS256)
 *   TC-04  Governed request          — POST /request           (Bob: API_CONSUMER, HS256)
 *   TC-05  SSH operator access       — GET /ssh/access         (Alice: SSH_OPERATOR, RS256)
 *   TC-06  Cortex bridge             — GET /bridge?action=sources (Cara: CORTEX_BRIDGE_USER, RS256)
 *   TC-07  Admin trusted list        — GET /trusted            (Dave: ADMIN, HS256)
 *   TC-08  Unauthorised — no token   — POST /request           → 401
 *   TC-09  Unauthorised — wrong role — GET /ssh/access         (Bob: not SSH_OPERATOR) → 403
 *   TC-10  SQLite master data        — verify seed counts and grant records
 *   TC-11  XML catalog content       — assert collibra-catalog URN references
 *   TC-12  Crypt: HS256 round-trip   — sign + verify with TEST_JWT_SECRET
 *   TC-13  Crypt: RS256 round-trip   — CertAuthority key-pair + JwsToken RS256
 *   TC-14  Response headers          — X-Singine-Host, X-Singine-Port, X-Singine-Catalog
 *   TC-15  TrustedIndividual XML     — verify XML serialization shape
 *
 * Aligned with:
 *   - singine XML catalog (SingineLocal.toCatalogXml, collibra-catalog assets)
 *   - singine.crypt       (singine.auth.JwsToken, singine.auth.CertAuthority)
 *   - singine.cortex      (cortex bridge stub at /bridge)
 *   - singine.local DNS   (SingineLocalDns.register, Host header assertion)
 *
 * Run:
 *   ant compile && java -cp classes:$(find ~/.m2 -name '*.jar' | paste -sd:) \
 *       singine.local.SingineLocalIntegrationTest
 *
 * Or via Ant:
 *   ant test-local
 */
public final class SingineLocalIntegrationTest {

    // ── Test state ────────────────────────────────────────────────────────────

    private static int passed = 0;
    private static int failed = 0;

    // Server and DB shared across all TCs
    private static SingineLocalServer server;
    private static Connection         db;
    private static int                serverPort;

    // Per-individual JWS tokens
    private static String tokenAlice; // RS256
    private static String tokenBob;   // HS256
    private static String tokenCara;  // RS256
    private static String tokenDave;  // HS256

    // RSA key pairs for Alice and Cara (SSH_OPERATOR, CORTEX_BRIDGE_USER)
    private static KeyPair kpAlice;
    private static KeyPair kpCara;

    // ── Entry point ───────────────────────────────────────────────────────────

    public static void main(String[] args) throws Exception {
        System.out.println("=================================================================");
        System.out.println("singine.local Integration Test Suite");
        System.out.println("Host   : " + SingineLocal.DEFAULT_HOST);
        System.out.println("Port   : " + SingineLocal.DEFAULT_PORT + " (canonical)");
        System.out.println("Catalog: " + SingineLocal.CATALOG_URN);
        System.out.println("=================================================================");
        System.out.println();

        try {
            setupSuite();
            runTests();
        } finally {
            teardownSuite();
        }

        System.out.println();
        System.out.println("=================================================================");
        System.out.printf("Results: %d passed, %d failed%n", passed, failed);
        System.out.println("=================================================================");
        System.exit(failed > 0 ? 1 : 0);
    }

    // ── Suite setup / teardown ────────────────────────────────────────────────

    private static void setupSuite() throws Exception {
        // 1. Register singine.local → 127.0.0.1 in JVM address cache
        SingineLocalDns.register();
        System.out.println("[setup] DNS: singine.local → 127.0.0.1");
        System.out.println("[setup] /etc/hosts entry: " + SingineLocalDns.hostsEntry());

        // 2. Open in-memory SQLite and seed master data
        Class.forName("org.sqlite.JDBC");
        db = DriverManager.getConnection("jdbc:sqlite::memory:");
        TrustedIndividualStore.createSchema(db);
        TrustedIndividualStore.seedMasterData(db);
        System.out.println("[setup] SQLite: in-memory DB seeded with 4 trusted individuals");

        // 3. Generate RSA key pairs for Alice (SSH_OPERATOR) and Cara (CORTEX_BRIDGE_USER)
        //    CertAuthority needs a writable keystore path; use a temp JKS for the test suite.
        //    Delete the file first so CertAuthority creates a fresh keystore (empty file causes EOFException).
        java.nio.file.Path tmpKsPath = java.nio.file.Files.createTempFile("singine-test-", ".jks");
        java.nio.file.Files.delete(tmpKsPath);
        CertAuthority ca = new CertAuthority(tmpKsPath.toString(), "singine-test");
        kpAlice = ca.generateKeyPair("alice-ssh-key").keyPair;
        kpCara  = ca.generateKeyPair("cara-cortex-key").keyPair;

        // Store Alice's public key PEM in the DB (enables RS256 auth on /ssh/access)
        String alicePem = publicKeyToPem(kpAlice);
        String caraPem  = publicKeyToPem(kpCara);
        TrustedIndividualStore.updatePublicKey(db, "individual-alice-01", alicePem);
        TrustedIndividualStore.updatePublicKey(db, "individual-cara-03",  caraPem);
        System.out.println("[setup] RSA key pairs generated and stored for Alice and Cara");

        // 4. Mint JWS tokens
        // Alice: RS256 — sub = her individual id
        tokenAlice = JwsToken.signRS256(kpAlice.getPrivate(),
            Map.of("sub", "individual-alice-01",
                   "scope", "ssh:read ssh:exec",
                   "network", "singine.local"),
            SingineLocal.TOKEN_TTL_SECONDS);

        // Bob: HS256
        tokenBob = JwsToken.signHS256(SingineLocal.TEST_JWT_SECRET,
            Map.of("sub", "individual-bob-02",
                   "scope", "catalog:read api:read",
                   "network", "singine.local"),
            SingineLocal.TOKEN_TTL_SECONDS);

        // Cara: RS256
        tokenCara = JwsToken.signRS256(kpCara.getPrivate(),
            Map.of("sub", "individual-cara-03",
                   "scope", "cortex:read bridge:search",
                   "network", "singine.local"),
            SingineLocal.TOKEN_TTL_SECONDS);

        // Dave: HS256
        tokenDave = JwsToken.signHS256(SingineLocal.TEST_JWT_SECRET,
            Map.of("sub", "individual-dave-04",
                   "scope", "admin:all",
                   "network", "singine.local"),
            SingineLocal.TOKEN_TTL_SECONDS);
        System.out.println("[setup] JWS tokens minted: Alice(RS256), Bob(HS256), Cara(RS256), Dave(HS256)");

        // 5. Start embedded server (passes the pre-seeded DB)
        server     = new SingineLocalServer(db);
        serverPort = server.getPort();
        server.start();
        System.out.println("[setup] Server started: 127.0.0.1:" + serverPort
                         + " (canonical: " + SingineLocal.DEFAULT_HOST
                         + ":" + SingineLocal.DEFAULT_PORT + ")");
        System.out.println();
    }

    private static void teardownSuite() {
        if (server != null) server.stop();
        try { if (db != null && !db.isClosed()) db.close(); } catch (Exception ignored) {}
        System.out.println("[teardown] Server stopped, DB closed.");
    }

    // ── Test runner ───────────────────────────────────────────────────────────

    private static void runTests() throws Exception {
        tc01_health();
        tc02_catalog_bob();
        tc03_dns_bob();
        tc04_request_bob();
        tc05_ssh_access_alice();
        tc06_cortex_bridge_cara();
        tc07_trusted_list_dave();
        tc08_unauthorized_no_token();
        tc09_forbidden_wrong_role();
        tc10_sqlite_master_data();
        tc11_xml_catalog_content();
        tc12_crypt_hs256_roundtrip();
        tc13_crypt_rs256_roundtrip();
        tc14_response_headers();
        tc15_trusted_individual_xml();
    }

    // ── Test cases ─────────────────────────────────────────────────────────────

    private static void tc01_health() {
        String name = "TC-01 Health check (GET /health, no auth)";
        try {
            var resp = SingineLocalClient.unauthenticated(serverPort).get("/health");
            assertTrue(name, "status 200", resp.status == 200);
            assertTrue(name, "is JSON",    resp.isJson());
            assertTrue(name, "status:ok",  resp.bodyContains("\"status\":\"ok\""));
            assertTrue(name, "host in body", resp.bodyContains(SingineLocal.DEFAULT_HOST));
            assertTrue(name, "port in body", resp.bodyContains(String.valueOf(SingineLocal.DEFAULT_PORT)));
            assertTrue(name, "network URN",  resp.bodyContains(SingineLocal.NETWORK_DOMAIN_URN));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc02_catalog_bob() {
        String name = "TC-02 XML catalog (GET /catalog, Bob API_CONSUMER HS256)";
        try {
            var resp = new SingineLocalClient(serverPort, tokenBob).get("/catalog");
            assertTrue(name, "status 200",       resp.status == 200);
            assertTrue(name, "is XML",            resp.isXml());
            assertTrue(name, "catalog URN",       resp.bodyContains(SingineLocal.CATALOG_URN));
            assertTrue(name, "network domain URN",resp.bodyContains(SingineLocal.NETWORK_DOMAIN_URN));
            assertTrue(name, "port 2000",         resp.bodyContains("<port>2000</port>"));
            assertTrue(name, "collibra-catalog",  resp.bodyContains("collibra-catalog"));
            assertTrue(name, "ultimate-metric",   resp.bodyContains("ultimate-metric"));
            assertTrue(name, "cortex-bridge URN", resp.bodyContains(SingineLocal.CORTEX_BRIDGE_URN));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc03_dns_bob() {
        String name = "TC-03 DNS management (GET /dns, Bob API_CONSUMER HS256)";
        try {
            var resp = new SingineLocalClient(serverPort, tokenBob).get("/dns");
            assertTrue(name, "status 200",       resp.status == 200);
            assertTrue(name, "is XML",            resp.isXml());
            assertTrue(name, "host singine.local",resp.bodyContains(SingineLocal.DEFAULT_HOST));
            assertTrue(name, "port 2000",         resp.bodyContains("<port>2000</port>"));
            assertTrue(name, "address 127.0.0.1", resp.bodyContains("127.0.0.1"));
            assertTrue(name, "port URN",          resp.bodyContains(SingineLocal.PORT_URN));
            assertTrue(name, "hosts-entry",       resp.bodyContains("singine.local"));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc04_request_bob() {
        String name = "TC-04 Governed request (POST /request, Bob API_CONSUMER HS256)";
        try {
            String requestBody = "{\"action\":\"catalog:read\",\"resource\":\"" + SingineLocal.CATALOG_URN + "\"}";
            var resp = new SingineLocalClient(serverPort, tokenBob).post("/request", requestBody);
            assertTrue(name, "status 200",          resp.status == 200);
            assertTrue(name, "is XML",               resp.isXml());
            assertTrue(name, "request-urn present",  resp.bodyContains("request-urn"));
            assertTrue(name, "response-urn present", resp.bodyContains("response-urn"));
            assertTrue(name, "principal URN",        resp.bodyContains("individual-bob-02"));
            assertTrue(name, "role api-consumer",    resp.bodyContains("api-consumer"));
            assertTrue(name, "catalog URN",          resp.bodyContains(SingineLocal.CATALOG_URN));
            assertTrue(name, "route id",             resp.bodyContains(SingineLocal.ROUTE_REQUEST_CREATE));
            assertTrue(name, "outcome SUCCESS",      resp.bodyContains("SUCCESS"));
            assertTrue(name, "ultimate-metric",      resp.bodyContains("ultimate-metric"));
            assertTrue(name, "echo present",         resp.bodyContains("catalog:read"));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc05_ssh_access_alice() {
        String name = "TC-05 SSH operator access (GET /ssh/access, Alice SSH_OPERATOR RS256)";
        try {
            var resp = new SingineLocalClient(serverPort, tokenAlice).get("/ssh/access");
            assertTrue(name, "status 200",          resp.status == 200);
            assertTrue(name, "is XML",               resp.isXml());
            assertTrue(name, "principal URN Alice",  resp.bodyContains("individual-alice-01"));
            assertTrue(name, "ssh-policy URN",       resp.bodyContains(SingineLocal.SSH_POLICY_URN));
            assertTrue(name, "cortex-bridge URN",    resp.bodyContains(SingineLocal.CORTEX_BRIDGE_URN));
            assertTrue(name, "public-key-pem set",   !resp.bodyContains("not-yet-set"));
            assertTrue(name, "granted true",         resp.bodyContains("<granted>true</granted>"));
            assertTrue(name, "collibra-catalog",     resp.bodyContains("collibra-catalog"));
            assertTrue(name, "SshAccessGrant asset", resp.bodyContains("SshAccessGrant"));
            assertTrue(name, "route id",             resp.bodyContains(SingineLocal.ROUTE_SSH_ACCESS));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc06_cortex_bridge_cara() {
        String name = "TC-06 Cortex bridge (GET /bridge?action=sources, Cara CORTEX_BRIDGE_USER RS256)";
        try {
            var resp = new SingineLocalClient(serverPort, tokenCara).get("/bridge?action=sources");
            assertTrue(name, "status 200",       resp.status == 200);
            assertTrue(name, "is JSON",           resp.isJson());
            assertTrue(name, "bridge URN",        resp.bodyContains(SingineLocal.CORTEX_BRIDGE_URN));
            assertTrue(name, "action sources",    resp.bodyContains("\"action\":\"sources\""));
            assertTrue(name, "principal Cara",    resp.bodyContains("individual-cara-03"));
            assertTrue(name, "source type sqlite",resp.bodyContains("\"type\":\"sqlite\""));
            assertTrue(name, "route id",          resp.bodyContains(SingineLocal.ROUTE_BRIDGE));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc07_trusted_list_dave() {
        String name = "TC-07 Admin trusted list (GET /trusted, Dave ADMIN HS256)";
        try {
            var resp = new SingineLocalClient(serverPort, tokenDave).get("/trusted");
            assertTrue(name, "status 200",        resp.status == 200);
            assertTrue(name, "is XML",             resp.isXml());
            assertTrue(name, "trusted-individuals", resp.bodyContains("trusted-individuals"));
            assertTrue(name, "Alice present",      resp.bodyContains("individual-alice-01"));
            assertTrue(name, "Bob present",        resp.bodyContains("individual-bob-02"));
            assertTrue(name, "Cara present",       resp.bodyContains("individual-cara-03"));
            assertTrue(name, "Dave present",       resp.bodyContains("individual-dave-04"));
            assertTrue(name, "collibra-catalog",   resp.bodyContains("collibra-catalog"));
            assertTrue(name, "trusted store URN",  resp.bodyContains(SingineLocal.TRUSTED_STORE_URN));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc08_unauthorized_no_token() {
        String name = "TC-08 Unauthorized — no Bearer token (POST /request)";
        try {
            var resp = SingineLocalClient.unauthenticated(serverPort).post("/request", "{}");
            assertTrue(name, "status 401",      resp.status == 401);
            assertTrue(name, "error field",     resp.bodyContains("unauthorized"));
            assertTrue(name, "hint present",    resp.bodyContains("Bearer token required"));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc09_forbidden_wrong_role() {
        String name = "TC-09 Forbidden — wrong role (GET /ssh/access, Bob is API_CONSUMER not SSH_OPERATOR)";
        try {
            var resp = new SingineLocalClient(serverPort, tokenBob).get("/ssh/access");
            assertTrue(name, "status 403",        resp.status == 403);
            assertTrue(name, "error forbidden",   resp.bodyContains("forbidden"));
            assertTrue(name, "required role hint",resp.bodyContains("SSH_OPERATOR"));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc10_sqlite_master_data() {
        String name = "TC-10 SQLite master data (count + grant records)";
        try {
            List<TrustedIndividual> all = TrustedIndividualStore.findAll(db);
            assertTrue(name, "4 individuals seeded", all.size() == 4);

            List<TrustedIndividual> sshOps = TrustedIndividualStore.findByRole(
                    db, TrustedIndividual.Role.SSH_OPERATOR.name());
            assertTrue(name, "1 SSH_OPERATOR", sshOps.size() == 1);
            assertTrue(name, "Alice is SSH_OPERATOR", "individual-alice-01".equals(sshOps.get(0).getId()));

            List<Map<String, String>> aliceGrants = TrustedIndividualStore.listGrants(db, "individual-alice-01");
            assertTrue(name, "Alice has 2 grants", aliceGrants.size() == 2);
            boolean hasSshExec = aliceGrants.stream().anyMatch(g -> "ssh:exec".equals(g.get("action")));
            assertTrue(name, "Alice grant: ssh:exec", hasSshExec);

            List<Map<String, String>> bobGrants = TrustedIndividualStore.listGrants(db, "individual-bob-02");
            assertTrue(name, "Bob has 2 grants", bobGrants.size() == 2);

            Optional<TrustedIndividual> dave = TrustedIndividualStore.findById(db, "individual-dave-04");
            assertTrue(name, "Dave found",        dave.isPresent());
            assertTrue(name, "Dave is ADMIN",     dave.get().getRole() == TrustedIndividual.Role.ADMIN);
            assertTrue(name, "Dave URN correct",  "urn:singine:individual:individual-dave-04".equals(dave.get().getUrn()));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc11_xml_catalog_content() {
        String name = "TC-11 XML catalog content (SingineLocal.toCatalogXml)";
        try {
            String xml = SingineLocal.toCatalogXml();
            assertTrue(name, "xml declaration",        xml.contains("<?xml"));
            assertTrue(name, "singine-local-network",  xml.contains("singine-local-network"));
            assertTrue(name, "network-layer id",       xml.contains("id=\"singine-local\""));
            assertTrue(name, "host singine.local",     xml.contains("<host>singine.local</host>"));
            assertTrue(name, "port 2000",              xml.contains("<port>2000</port>"));
            assertTrue(name, "catalog URN",            xml.contains(SingineLocal.CATALOG_URN));
            assertTrue(name, "network domain URN",     xml.contains(SingineLocal.NETWORK_DOMAIN_URN));
            assertTrue(name, "cortex bridge URN",      xml.contains(SingineLocal.CORTEX_BRIDGE_URN));
            assertTrue(name, "ssh policy URN",         xml.contains(SingineLocal.SSH_POLICY_URN));
            assertTrue(name, "collibra-catalog block", xml.contains("collibra-catalog"));
            assertTrue(name, "service-layer / api",    xml.contains("service-layer"));
            assertTrue(name, "platform-backend",       xml.contains("platform-backend"));
            assertTrue(name, "ultimate-metric",        xml.contains("ultimate-metric"));
            assertTrue(name, "formula present",        xml.contains("usage_value + business_value - platform_cost"));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc12_crypt_hs256_roundtrip() {
        String name = "TC-12 Crypt: HS256 sign + verify (singine.auth.JwsToken)";
        try {
            Map<String, Object> claims = new LinkedHashMap<>();
            claims.put("sub",     "individual-bob-02");
            claims.put("network", "singine.local");
            claims.put("scope",   "catalog:read");

            String token = JwsToken.signHS256(SingineLocal.TEST_JWT_SECRET, claims, 3600);
            assertTrue(name, "token non-null", token != null && !token.isBlank());
            assertTrue(name, "three-part JWT",  token.split("\\.").length == 3);

            Map<String, Object> decoded = JwsToken.verifyHS256(SingineLocal.TEST_JWT_SECRET, token);
            assertTrue(name, "sub preserved",  "individual-bob-02".equals(decoded.get("sub")));
            assertTrue(name, "iss = urn:singine:idp", "urn:singine:idp".equals(decoded.get("iss")));
            assertTrue(name, "jti present",    decoded.containsKey("jti"));
            assertTrue(name, "sid present",    decoded.containsKey("sid"));
            assertTrue(name, "exp present",    decoded.containsKey("exp"));
            assertTrue(name, "iat present",    decoded.containsKey("iat"));

            // Wrong secret must throw
            boolean rejected = false;
            try { JwsToken.verifyHS256("wrong-secret", token); } catch (Exception e) { rejected = true; }
            assertTrue(name, "wrong secret rejected", rejected);
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc13_crypt_rs256_roundtrip() {
        String name = "TC-13 Crypt: RS256 sign + verify (CertAuthority + JwsToken)";
        try {
            java.nio.file.Path tmpKsPath = java.nio.file.Files.createTempFile("singine-tc13-", ".jks");
            java.nio.file.Files.delete(tmpKsPath);
            CertAuthority ca = new CertAuthority(tmpKsPath.toString(), "singine-test");
            CertAuthority.KeyPairEntry kpe = ca.generateKeyPair("test-tc13-rsa-key");
            assertTrue(name, "alias correct",             "test-tc13-rsa-key".equals(kpe.alias));
            assertTrue(name, "urn has urn:singine:keypair:", kpe.urn.startsWith("urn:singine:keypair:"));
            assertTrue(name, "public key PEM present",    !kpe.publicKeyPem.isBlank());
            assertTrue(name, "algorithm starts with RSA", kpe.algorithm.startsWith("RSA"));

            Map<String, Object> claims = new LinkedHashMap<>();
            claims.put("sub",     "individual-alice-01");
            claims.put("network", "singine.local");
            claims.put("scope",   "ssh:exec");

            String token = JwsToken.signRS256(kpe.keyPair.getPrivate(), claims, 3600);
            assertTrue(name, "token non-null",  token != null && !token.isBlank());
            assertTrue(name, "three-part JWT",   token.split("\\.").length == 3);

            Map<String, Object> decoded = JwsToken.verifyRS256(token, kpe.keyPair.getPublic());
            assertTrue(name, "sub preserved",   "individual-alice-01".equals(decoded.get("sub")));
            assertTrue(name, "iss singine:idp", "urn:singine:idp".equals(decoded.get("iss")));
            assertTrue(name, "sid present",     decoded.containsKey("sid"));

            // Wrong key must throw
            CertAuthority.KeyPairEntry other = ca.generateKeyPair("other-key");
            boolean rejected = false;
            try { JwsToken.verifyRS256(token, other.keyPair.getPublic()); } catch (Exception e) { rejected = true; }
            assertTrue(name, "wrong public key rejected", rejected);
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc14_response_headers() {
        String name = "TC-14 Response headers (X-Singine-Host, X-Singine-Port, X-Singine-Catalog)";
        try {
            var resp = SingineLocalClient.unauthenticated(serverPort).get("/health");
            assertTrue(name, "X-Singine-Host set",
                SingineLocal.DEFAULT_HOST.equals(resp.singineHost));
            assertTrue(name, "X-Singine-Port = 2000",
                String.valueOf(SingineLocal.DEFAULT_PORT).equals(resp.singinePort));
            assertTrue(name, "X-Singine-Catalog set",
                SingineLocal.CATALOG_URN.equals(resp.singineCatalog));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    private static void tc15_trusted_individual_xml() {
        String name = "TC-15 TrustedIndividual XML serialization shape";
        try {
            TrustedIndividual ti = new TrustedIndividual(
                "test-xml-01", "Test User",
                TrustedIndividual.Role.CATALOG_READER,
                "test@singine.local", "2026-03-17T00:00:00Z",
                "-----BEGIN PUBLIC KEY-----\nMIIBIjANBg==\n-----END PUBLIC KEY-----",
                Map.of("scope", "catalog:read", "network", "singine.local"));

            String xml = ti.toXml();
            assertTrue(name, "element id attr",            xml.contains("id=\"test-xml-01\""));
            assertTrue(name, "urn:singine:individual",     xml.contains("urn:singine:individual:test-xml-01"));
            assertTrue(name, "role catalog-reader",        xml.contains("<role>catalog-reader</role>"));
            assertTrue(name, "collibra-catalog present",   xml.contains("collibra-catalog"));
            assertTrue(name, "assetType TrustedIndividual",xml.contains("assetType=\"TrustedIndividual\""));
            assertTrue(name, "assetType AccessRole",       xml.contains("assetType=\"AccessRole\""));
            assertTrue(name, "public-key pem encoding",    xml.contains("encoding=\"pem\""));
            assertTrue(name, "claims present",             xml.contains("scope"));
            assertTrue(name, "canAccessRoute catalog",     ti.canAccessRoute(SingineLocal.ROUTE_CATALOG));
            assertTrue(name, "cannotAccessRoute ssh",      !ti.canAccessRoute(SingineLocal.ROUTE_SSH_ACCESS));
            assertTrue(name, "EDN has role keyword",       ti.toEdn().contains(":individual/role :catalog_reader"));
            pass(name);
        } catch (Throwable t) { fail(name, t); }
    }

    // ── Assertion helpers ─────────────────────────────────────────────────────

    private static void assertTrue(String tc, String label, boolean condition) {
        if (!condition) throw new AssertionError("FAIL [" + label + "]");
    }

    private static void pass(String name) {
        passed++;
        System.out.printf("  PASS  %s%n", name);
    }

    private static void fail(String name, Throwable t) {
        failed++;
        System.out.printf("  FAIL  %s%n", name);
        System.out.printf("        %s: %s%n", t.getClass().getSimpleName(), t.getMessage());
    }

    // ── Crypto helper ─────────────────────────────────────────────────────────

    /** Convert an RSA public key to a PEM-encoded string. */
    private static String publicKeyToPem(KeyPair kp) {
        byte[] encoded = kp.getPublic().getEncoded();
        String b64 = Base64.getMimeEncoder(64, new byte[]{'\n'}).encodeToString(encoded);
        return "-----BEGIN PUBLIC KEY-----\n" + b64 + "\n-----END PUBLIC KEY-----";
    }
}
