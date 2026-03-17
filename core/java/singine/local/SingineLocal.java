package singine.local;

/**
 * Constants and URN helpers for the singine.local network layer.
 *
 * Default binding : http://singine.local:2000
 * Default port    : 2000  (canonical singine local-network port)
 *
 * Aligned with:
 *   - singine XML catalog (collibra-catalog asset references)
 *   - singine.crypt       (JwsToken, CertAuthority — see singine.auth)
 *   - singine.cortex      (cortex_bridge, SSH-access governance)
 *
 * URN scheme:
 *   urn:singine:network:domain:singine.local
 *   urn:singine:port:2000
 *   urn:singine:catalog:local
 *   urn:singine:cortex:bridge:local
 *   urn:singine:store:trusted-individuals
 *   urn:singine:policy:ssh-access:local
 */
public final class SingineLocal {

    // ── Network defaults ──────────────────────────────────────────────────────

    public static final int    DEFAULT_PORT   = 2000;
    public static final String DEFAULT_HOST   = "singine.local";
    public static final String DEFAULT_SCHEME = "http";

    // ── XML catalog URNs ──────────────────────────────────────────────────────

    public static final String CATALOG_URN         = "urn:singine:catalog:local";
    public static final String PORT_URN             = "urn:singine:port:2000";
    public static final String NETWORK_DOMAIN_URN   = "urn:singine:network:domain:singine.local";
    public static final String TRUSTED_STORE_URN    = "urn:singine:store:trusted-individuals";
    public static final String CORTEX_BRIDGE_URN    = "urn:singine:cortex:bridge:local";
    public static final String SSH_POLICY_URN       = "urn:singine:policy:ssh-access:local";

    // ── HTTP route identifiers (Rails-style: singine.<layer>.<resource>.<action>) ──

    public static final String ROUTE_HEALTH         = "singine.local.health.show";
    public static final String ROUTE_CATALOG        = "singine.local.catalog.show";
    public static final String ROUTE_DNS            = "singine.local.dns.show";
    public static final String ROUTE_TRUSTED_INDEX  = "singine.local.trusted.index";
    public static final String ROUTE_REQUEST_CREATE = "singine.local.request.create";
    public static final String ROUTE_BRIDGE         = "singine.local.cortex.bridge";
    public static final String ROUTE_SSH_ACCESS     = "singine.local.ssh.access";

    // ── Crypt / auth ──────────────────────────────────────────────────────────

    /**
     * Shared HS256 secret for test environments.
     * Production deployments must rotate this via singine.crypt key management.
     */
    public static final String TEST_JWT_SECRET = "singine-local-test-secret-2026";

    /**
     * Token TTL for governed sessions: 1 hour.
     * Aligned with singine.ai mandate session lifetime.
     */
    public static final long TOKEN_TTL_SECONDS = 3600L;

    private SingineLocal() {}

    // ── URL helpers ───────────────────────────────────────────────────────────

    public static String baseUrl() {
        return DEFAULT_SCHEME + "://" + DEFAULT_HOST + ":" + DEFAULT_PORT;
    }

    /** Connect URL: uses 127.0.0.1 for socket-level connection. */
    public static String connectUrl(int port) {
        return DEFAULT_SCHEME + "://127.0.0.1:" + port;
    }

    // ── XML catalog fragment ──────────────────────────────────────────────────

    /**
     * XML catalog fragment for the singine.local network layer.
     * Follows the elia-electricity skeleton pattern from CLAUDE.md.
     */
    public static String toCatalogXml() {
        return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
             + "<singine-local-network>\n"
             + "  <network-layer id=\"singine-local\">\n"
             + "    <host>" + DEFAULT_HOST + "</host>\n"
             + "    <port>" + DEFAULT_PORT + "</port>\n"
             + "    <scheme>" + DEFAULT_SCHEME + "</scheme>\n"
             + "    <urn>" + NETWORK_DOMAIN_URN + "</urn>\n"
             + "    <catalog-urn>" + CATALOG_URN + "</catalog-urn>\n"
             + "    <collibra-catalog>\n"
             + "      <asset assetType=\"NetworkDomain\" collibraId=\"\" name=\"singine.local\"/>\n"
             + "      <asset assetType=\"Port\"          collibraId=\"\" name=\"2000\"/>\n"
             + "      <asset assetType=\"CortexBridge\"  collibraId=\"\" name=\"singine.cortex.local\"/>\n"
             + "      <asset assetType=\"SshPolicy\"     collibraId=\"\" name=\"ssh-access:local\"/>\n"
             + "    </collibra-catalog>\n"
             + "    <service-layer>\n"
             + "      <apis>\n"
             + "        <api id=\"singine-local-api\">\n"
             + "          <name>Singine Local Network API</name>\n"
             + "          <purpose>Governed request/response with trusted-individual authentication</purpose>\n"
             + "          <version>v1</version>\n"
             + "          <servesDomain>" + NETWORK_DOMAIN_URN + "</servesDomain>\n"
             + "        </api>\n"
             + "      </apis>\n"
             + "    </service-layer>\n"
             + "    <ssh-policy-urn>" + SSH_POLICY_URN + "</ssh-policy-urn>\n"
             + "    <platform-backend>\n"
             + "      <backend type=\"cortex-bridge\">\n"
             + "        <urn>" + CORTEX_BRIDGE_URN + "</urn>\n"
             + "        <purpose>SQLite-backed semantic bridge for SSH-access governance</purpose>\n"
             + "      </backend>\n"
             + "    </platform-backend>\n"
             + "    <ultimate-metric id=\"usage-cost-benefit-score\">\n"
             + "      <name>Usage Cost Benefit Score</name>\n"
             + "      <formula>usage_value + business_value - platform_cost</formula>\n"
             + "    </ultimate-metric>\n"
             + "  </network-layer>\n"
             + "</singine-local-network>\n";
    }
}
