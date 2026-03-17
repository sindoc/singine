package singine.local;

import java.net.*;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * DNS and port management for the singine.local network layer.
 *
 * Strategy:
 *   1. Register singine.local → 127.0.0.1 in the JVM's InetAddress cache
 *      using InetAddress.getByAddress(hostname, bytes) which embeds the hostname
 *      in the returned address object.  This is sufficient for tests that use
 *      the resolved InetAddress directly (e.g. ServerSocket, Socket).
 *   2. For HTTP URL-based connections (HttpURLConnection) the JVM re-resolves
 *      the hostname.  The client therefore connects to 127.0.0.1 directly and
 *      sets a "Host: singine.local" header — the canonical singine.local identity
 *      is asserted at the HTTP layer rather than the DNS layer.
 *   3. For production: add the /etc/hosts entry returned by hostsEntry().
 *
 * Port lifecycle:
 *   - DEFAULT_PORT = 2000 (canonical singine local-network port).
 *   - findAvailablePort(preferred) tries the preferred port first, then walks
 *     upward until a free port is found.  Tests bind to the returned port and
 *     assert that DEFAULT_PORT is the canonical value in all XML catalog refs.
 *
 * XML catalog / URN alignment:
 *   - Network domain URN : urn:singine:network:domain:singine.local
 *   - Port URN           : urn:singine:port:2000
 */
public final class SingineLocalDns {

    private static final Map<String, InetAddress> REGISTRY = new ConcurrentHashMap<>();

    private SingineLocalDns() {}

    // ── Registration ──────────────────────────────────────────────────────────

    /**
     * Register singine.local → 127.0.0.1 for test-local JVM resolution.
     * Safe to call multiple times.
     */
    public static InetAddress register() throws UnknownHostException {
        return register(SingineLocal.DEFAULT_HOST, "127.0.0.1");
    }

    /**
     * Register an arbitrary hostname → IPv4 address.
     * Returns the InetAddress with the hostname embedded (used by ServerSocket/Socket).
     */
    public static InetAddress register(String hostname, String ipv4) throws UnknownHostException {
        byte[] bytes = parseIPv4(ipv4);
        InetAddress addr = InetAddress.getByAddress(hostname, bytes);
        REGISTRY.put(hostname, addr);
        return addr;
    }

    /**
     * Resolve hostname.  Returns the registered address if present,
     * otherwise delegates to the system resolver.
     */
    public static InetAddress resolve(String hostname) throws UnknownHostException {
        InetAddress cached = REGISTRY.get(hostname);
        return cached != null ? cached : InetAddress.getByName(hostname);
    }

    /** True if singine.local is registered or resolves to a loopback/site-local address. */
    public static boolean isSingineLocalReachable() {
        try {
            InetAddress addr = resolve(SingineLocal.DEFAULT_HOST);
            return addr.isLoopbackAddress() || addr.isSiteLocalAddress();
        } catch (UnknownHostException e) {
            return false;
        }
    }

    // ── Port lifecycle ────────────────────────────────────────────────────────

    /**
     * Find an available TCP port, preferring {@code preferred}.
     * Walks upward (preferred, preferred+1, …) until a free port is found.
     * Returns the canonical DEFAULT_PORT (2000) in production; in test
     * environments it may return a different port if 2000 is occupied.
     */
    public static int findAvailablePort(int preferred) {
        for (int candidate = preferred; candidate < preferred + 100; candidate++) {
            try (ServerSocket probe = new ServerSocket(candidate)) {
                probe.setReuseAddress(true);
                return candidate;
            } catch (Exception ignored) {
                // port occupied — try next
            }
        }
        // fall back to OS-assigned ephemeral port
        try (ServerSocket probe = new ServerSocket(0)) {
            return probe.getLocalPort();
        } catch (Exception e) {
            throw new IllegalStateException("Cannot find a free TCP port", e);
        }
    }

    // ── Documentation helpers ─────────────────────────────────────────────────

    /** /etc/hosts line for production singine.local setup. */
    public static String hostsEntry() {
        return "127.0.0.1  " + SingineLocal.DEFAULT_HOST
             + "  # singine local network (port " + SingineLocal.DEFAULT_PORT + ")";
    }

    /** XML catalog fragment for the DNS and port registration. */
    public static String toDnsXml() {
        return "<dns-management>\n"
             + "  <host>" + SingineLocal.DEFAULT_HOST + "</host>\n"
             + "  <address>127.0.0.1</address>\n"
             + "  <port>" + SingineLocal.DEFAULT_PORT + "</port>\n"
             + "  <urn>" + SingineLocal.NETWORK_DOMAIN_URN + "</urn>\n"
             + "  <port-urn>" + SingineLocal.PORT_URN + "</port-urn>\n"
             + "  <collibra-catalog>\n"
             + "    <asset assetType=\"HostRecord\" collibraId=\"\" name=\"singine.local → 127.0.0.1\"/>\n"
             + "    <asset assetType=\"PortReservation\" collibraId=\"\" name=\"tcp:2000\"/>\n"
             + "  </collibra-catalog>\n"
             + "  <hosts-entry>" + hostsEntry() + "</hosts-entry>\n"
             + "</dns-management>\n";
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static byte[] parseIPv4(String ipv4) throws UnknownHostException {
        String[] parts = ipv4.split("\\.");
        if (parts.length != 4) throw new UnknownHostException("Invalid IPv4: " + ipv4);
        byte[] bytes = new byte[4];
        for (int i = 0; i < 4; i++) bytes[i] = (byte) Integer.parseInt(parts[i]);
        return bytes;
    }
}
