/**
 * Singine Local Network Layer — HTTP server, DNS management, and trusted-individual
 * authentication at {@code singine.local:2000}.
 *
 * <h2>Overview</h2>
 * <p>The {@code singine.local} package implements the singine local-network layer:</p>
 * <ul>
 *   <li>Default binding: {@code http://singine.local:2000}</li>
 *   <li>DNS management: {@code singine.local → 127.0.0.1}</li>
 *   <li>SQLite-backed trusted-individual store with access grants</li>
 *   <li>JWS-authenticated HTTP request/response (HS256 and RS256)</li>
 *   <li>singine XML catalog alignment (collibra-catalog asset references)</li>
 *   <li>singine.crypt integration ({@link singine.auth.JwsToken}, {@link singine.auth.CertAuthority})</li>
 *   <li>singine.cortex integration (/bridge route, SPARQL/search)</li>
 * </ul>
 *
 * <h2>Components</h2>
 * <table border="1">
 *   <tr><th>Class</th><th>Role</th></tr>
 *   <tr><td>{@link singine.local.SingineLocal}</td>
 *       <td>Constants (DEFAULT_PORT=2000, DEFAULT_HOST="singine.local"), all catalog/SSH/cortex
 *           URNs, XML catalog method</td></tr>
 *   <tr><td>{@link singine.local.TrustedIndividual}</td>
 *       <td>Data model: 5 roles, canAccessRoute(), XML+EDN serialization aligned with
 *           collibra-catalog format</td></tr>
 *   <tr><td>{@link singine.local.TrustedIndividualStore}</td>
 *       <td>SQLite store: DDL, CRUD, seedMasterData() (4 individuals + access grants)</td></tr>
 *   <tr><td>{@link singine.local.SingineLocalDns}</td>
 *       <td>DNS management: register singine.local→127.0.0.1, findAvailablePort(2000),
 *           /etc/hosts helper</td></tr>
 *   <tr><td>{@link singine.local.SingineLocalServer}</td>
 *       <td>Embedded JDK HttpServer on port 2000, 7 routes with role-based HS256+RS256 auth</td></tr>
 *   <tr><td>{@link singine.local.SingineLocalClient}</td>
 *       <td>HTTP client: connects to 127.0.0.1:port, sends Host: singine.local header</td></tr>
 *   <tr><td>{@link singine.local.SingineLocalIntegrationTest}</td>
 *       <td>15 integration test cases (main() runner, no JUnit dependency)</td></tr>
 * </table>
 *
 * <h2>HTTP Routes</h2>
 * <table border="1">
 *   <tr><th>Route</th><th>Route ID</th><th>Auth</th><th>Role</th></tr>
 *   <tr><td>GET  /health</td><td>singine.local.health.show</td><td>none</td><td>—</td></tr>
 *   <tr><td>GET  /catalog</td><td>singine.local.catalog.show</td><td>Bearer</td><td>API_CONSUMER, CATALOG_READER</td></tr>
 *   <tr><td>GET  /dns</td><td>singine.local.dns.show</td><td>Bearer</td><td>API_CONSUMER, CATALOG_READER</td></tr>
 *   <tr><td>GET  /trusted</td><td>singine.local.trusted.index</td><td>Bearer</td><td>ADMIN</td></tr>
 *   <tr><td>POST /request</td><td>singine.local.request.create</td><td>Bearer</td><td>API_CONSUMER, SSH_OPERATOR</td></tr>
 *   <tr><td>GET  /bridge</td><td>singine.local.cortex.bridge</td><td>Bearer</td><td>CORTEX_BRIDGE_USER</td></tr>
 *   <tr><td>GET  /ssh/access</td><td>singine.local.ssh.access</td><td>Bearer RS256</td><td>SSH_OPERATOR</td></tr>
 * </table>
 *
 * <h2>Master Data (Trusted Individuals)</h2>
 * <table border="1">
 *   <tr><th>ID</th><th>Name</th><th>Role</th><th>Auth</th></tr>
 *   <tr><td>individual-alice-01</td><td>Alice Operator</td><td>SSH_OPERATOR</td><td>RS256</td></tr>
 *   <tr><td>individual-bob-02</td><td>Bob Consumer</td><td>API_CONSUMER</td><td>HS256</td></tr>
 *   <tr><td>individual-cara-03</td><td>Cara Analyst</td><td>CORTEX_BRIDGE_USER</td><td>RS256</td></tr>
 *   <tr><td>individual-dave-04</td><td>Dave Admin</td><td>ADMIN</td><td>HS256</td></tr>
 * </table>
 *
 * <h2>URN Scheme</h2>
 * <ul>
 *   <li>{@code urn:singine:network:domain:singine.local} — network domain</li>
 *   <li>{@code urn:singine:port:2000}                    — canonical port</li>
 *   <li>{@code urn:singine:catalog:local}                — XML catalog</li>
 *   <li>{@code urn:singine:cortex:bridge:local}          — cortex bridge</li>
 *   <li>{@code urn:singine:store:trusted-individuals}    — trusted individual store</li>
 *   <li>{@code urn:singine:policy:ssh-access:local}      — SSH access policy</li>
 *   <li>{@code urn:singine:individual:<id>}              — per-individual URN</li>
 * </ul>
 *
 * <h2>DNS Management</h2>
 * <p>For production, add to {@code /etc/hosts}:</p>
 * <pre>
 *   127.0.0.1  singine.local  # singine local network (port 2000)
 * </pre>
 * <p>For tests, call {@link singine.local.SingineLocalDns#register()} which seeds
 * the JVM address cache. The HTTP client uses {@code 127.0.0.1} for socket connections
 * and asserts {@code Host: singine.local} at the HTTP layer.</p>
 *
 * <h2>Integration Test</h2>
 * <pre>
 *   ant test-local
 * </pre>
 * <p>Runs 15 test cases covering health, catalog, DNS, governed requests, SSH access,
 * cortex bridge, admin routes, unauthorized/forbidden access, SQLite master data,
 * XML catalog content, HS256/RS256 crypto, response headers, and XML serialization.</p>
 *
 * @see singine.local.SingineLocal
 * @see singine.local.TrustedIndividual
 * @see singine.local.TrustedIndividualStore
 * @see singine.local.SingineLocalServer
 * @see singine.local.SingineLocalDns
 * @see singine.auth.JwsToken
 * @see singine.auth.CertAuthority
 */
package singine.local;
