package singine.local;

import java.sql.*;
import java.time.Instant;
import java.util.*;

/**
 * SQLite-backed store for trusted individuals and access grants.
 *
 * Schema mirrors the singine.ai session persistence model:
 *   trusted_individuals  — master individual records
 *   access_grants        — per-session grants (analogous to ai_mandates)
 *
 * All SQL is plain JDBC — no ORM, no external query library.
 * Use try-with-resources throughout; callers own the Connection lifecycle.
 *
 * Seed data covers all four roles and aligns with the singine XML catalog
 * ultimate-metric principle: each grant records the resource URN it governs.
 */
public final class TrustedIndividualStore {

    public static final String DDL =
        "CREATE TABLE IF NOT EXISTS trusted_individuals (\n"
      + "  id             TEXT PRIMARY KEY,\n"
      + "  name           TEXT NOT NULL,\n"
      + "  urn            TEXT NOT NULL,\n"
      + "  role           TEXT NOT NULL,\n"
      + "  email          TEXT NOT NULL,\n"
      + "  granted_at     TEXT NOT NULL,\n"
      + "  public_key_pem TEXT NOT NULL DEFAULT '',\n"
      + "  claims_json    TEXT NOT NULL DEFAULT '{}'\n"
      + ");\n"
      + "CREATE TABLE IF NOT EXISTS access_grants (\n"
      + "  grant_id       TEXT PRIMARY KEY,\n"
      + "  individual_id  TEXT NOT NULL,\n"
      + "  resource_urn   TEXT NOT NULL,\n"
      + "  action         TEXT NOT NULL,\n"
      + "  decision       TEXT NOT NULL DEFAULT 'granted',\n"
      + "  granted_at     TEXT NOT NULL,\n"
      + "  note           TEXT NOT NULL DEFAULT ''\n"
      + ");";

    private TrustedIndividualStore() {}

    // ── Schema ────────────────────────────────────────────────────────────────

    public static void createSchema(Connection conn) throws SQLException {
        try (Statement st = conn.createStatement()) {
            for (String stmt : DDL.split(";")) {
                String s = stmt.trim();
                if (!s.isEmpty()) st.execute(s);
            }
        }
    }

    // ── CRUD ──────────────────────────────────────────────────────────────────

    public static void insert(Connection conn, TrustedIndividual ti) throws SQLException {
        final String sql =
            "INSERT OR REPLACE INTO trusted_individuals "
          + "(id, name, urn, role, email, granted_at, public_key_pem, claims_json) "
          + "VALUES (?, ?, ?, ?, ?, ?, ?, ?)";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, ti.getId());
            ps.setString(2, ti.getName());
            ps.setString(3, ti.getUrn());
            ps.setString(4, ti.getRole().name());
            ps.setString(5, ti.getEmail());
            ps.setString(6, ti.getGrantedAt());
            ps.setString(7, ti.getPublicKeyPem());
            ps.setString(8, claimsToJson(ti.getClaims()));
            ps.executeUpdate();
        }
    }

    public static Optional<TrustedIndividual> findById(Connection conn, String id)
            throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT * FROM trusted_individuals WHERE id = ?")) {
            ps.setString(1, id);
            try (ResultSet rs = ps.executeQuery()) {
                return rs.next() ? Optional.of(fromRow(rs)) : Optional.empty();
            }
        }
    }

    public static List<TrustedIndividual> findByRole(Connection conn, String role)
            throws SQLException {
        List<TrustedIndividual> out = new ArrayList<>();
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT * FROM trusted_individuals WHERE role = ? ORDER BY granted_at")) {
            ps.setString(1, role);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) out.add(fromRow(rs));
            }
        }
        return out;
    }

    public static List<TrustedIndividual> findAll(Connection conn) throws SQLException {
        List<TrustedIndividual> out = new ArrayList<>();
        try (Statement st = conn.createStatement();
             ResultSet rs = st.executeQuery(
                     "SELECT * FROM trusted_individuals ORDER BY granted_at")) {
            while (rs.next()) out.add(fromRow(rs));
        }
        return out;
    }

    /** Update only the public_key_pem column (called after RSA key-pair generation). */
    public static void updatePublicKey(Connection conn, String id, String pem)
            throws SQLException {
        try (PreparedStatement ps = conn.prepareStatement(
                "UPDATE trusted_individuals SET public_key_pem = ? WHERE id = ?")) {
            ps.setString(1, pem);
            ps.setString(2, id);
            ps.executeUpdate();
        }
    }

    // ── Access grants ─────────────────────────────────────────────────────────

    public static void grantAccess(
            Connection conn, String individualId, String resourceUrn,
            String action, String note) throws SQLException {
        final String sql =
            "INSERT INTO access_grants "
          + "(grant_id, individual_id, resource_urn, action, decision, granted_at, note) "
          + "VALUES (?, ?, ?, ?, 'granted', ?, ?)";
        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, UUID.randomUUID().toString());
            ps.setString(2, individualId);
            ps.setString(3, resourceUrn);
            ps.setString(4, action);
            ps.setString(5, Instant.now().toString());
            ps.setString(6, note);
            ps.executeUpdate();
        }
    }

    public static List<Map<String, String>> listGrants(Connection conn, String individualId)
            throws SQLException {
        List<Map<String, String>> out = new ArrayList<>();
        try (PreparedStatement ps = conn.prepareStatement(
                "SELECT * FROM access_grants WHERE individual_id = ? ORDER BY granted_at")) {
            ps.setString(1, individualId);
            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    Map<String, String> row = new LinkedHashMap<>();
                    row.put("grant_id",      rs.getString("grant_id"));
                    row.put("individual_id", rs.getString("individual_id"));
                    row.put("resource_urn",  rs.getString("resource_urn"));
                    row.put("action",        rs.getString("action"));
                    row.put("decision",      rs.getString("decision"));
                    row.put("granted_at",    rs.getString("granted_at"));
                    row.put("note",          rs.getString("note"));
                    out.add(row);
                }
            }
        }
        return out;
    }

    // ── Master-data seed ──────────────────────────────────────────────────────

    /**
     * Seeds the canonical test master data: four individuals covering all roles
     * plus their corresponding access grants.
     *
     * Individual URNs follow singine URN scheme: urn:singine:individual:<id>
     * Grant resource URNs come from SingineLocal constants (XML catalog aligned).
     *
     * Note: publicKeyPem is seeded empty; integration tests update it after
     * calling CertAuthority.generateKeyPair() for RS256/SSH-capable individuals.
     */
    public static void seedMasterData(Connection conn) throws SQLException {
        // Alice — SSH operator: cert-based (RS256) access to SSH routes and cortex bridge
        insert(conn, new TrustedIndividual(
            "individual-alice-01", "Alice Operator",
            TrustedIndividual.Role.SSH_OPERATOR,
            "alice@singine.local", "2026-01-01T00:00:00Z", "",
            Map.of("scope",   "ssh:read ssh:exec",
                   "network", "singine.local",
                   "alg",     "RS256")));
        grantAccess(conn, "individual-alice-01",
            SingineLocal.CORTEX_BRIDGE_URN, "ssh:exec",
            "SSH operator: cert-auth access to cortex bridge at singine.local:2000");
        grantAccess(conn, "individual-alice-01",
            SingineLocal.SSH_POLICY_URN, "ssh:read",
            "SSH operator: read SSH policy manifest");

        // Bob — API consumer: HS256 token access to catalog and request endpoints
        insert(conn, new TrustedIndividual(
            "individual-bob-02", "Bob Consumer",
            TrustedIndividual.Role.API_CONSUMER,
            "bob@singine.local", "2026-01-15T00:00:00Z", "",
            Map.of("scope",   "catalog:read api:read",
                   "network", "singine.local",
                   "alg",     "HS256")));
        grantAccess(conn, "individual-bob-02",
            SingineLocal.CATALOG_URN, "api:read",
            "API consumer: read access to singine XML catalog");
        grantAccess(conn, "individual-bob-02",
            SingineLocal.NETWORK_DOMAIN_URN, "request:create",
            "API consumer: submit governed requests to singine.local:2000");

        // Cara — cortex bridge user: RS256 access to /bridge (SPARQL, search)
        insert(conn, new TrustedIndividual(
            "individual-cara-03", "Cara Analyst",
            TrustedIndividual.Role.CORTEX_BRIDGE_USER,
            "cara@singine.local", "2026-02-01T00:00:00Z", "",
            Map.of("scope",   "cortex:read bridge:search bridge:sparql",
                   "network", "singine.local",
                   "alg",     "RS256")));
        grantAccess(conn, "individual-cara-03",
            SingineLocal.CORTEX_BRIDGE_URN, "bridge:search",
            "Cortex bridge: full-text search access via singine.local:2000/bridge");
        grantAccess(conn, "individual-cara-03",
            SingineLocal.CORTEX_BRIDGE_URN, "bridge:sparql",
            "Cortex bridge: SPARQL query access");

        // Dave — admin: HS256 master token for full access
        insert(conn, new TrustedIndividual(
            "individual-dave-04", "Dave Admin",
            TrustedIndividual.Role.ADMIN,
            "dave@singine.local", "2026-01-01T00:00:00Z", "",
            Map.of("scope",   "admin:all",
                   "network", "singine.local",
                   "alg",     "HS256")));
        grantAccess(conn, "individual-dave-04",
            SingineLocal.NETWORK_DOMAIN_URN, "admin:all",
            "Admin: full access to all singine.local:2000 routes");
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    private static TrustedIndividual fromRow(ResultSet rs) throws SQLException {
        return new TrustedIndividual(
            rs.getString("id"),
            rs.getString("name"),
            TrustedIndividual.Role.valueOf(rs.getString("role")),
            rs.getString("email"),
            rs.getString("granted_at"),
            rs.getString("public_key_pem"),
            jsonToClaims(rs.getString("claims_json")));
    }

    static String claimsToJson(Map<String, String> claims) {
        if (claims == null || claims.isEmpty()) return "{}";
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, String> e : claims.entrySet()) {
            if (!first) sb.append(",");
            sb.append("\"").append(e.getKey().replace("\"", "\\\"")).append("\":")
              .append("\"").append(e.getValue().replace("\"", "\\\"")).append("\"");
            first = false;
        }
        return sb.append("}").toString();
    }

    static Map<String, String> jsonToClaims(String json) {
        Map<String, String> out = new LinkedHashMap<>();
        if (json == null || json.isBlank() || "{}".equals(json.trim())) return out;
        String inner = json.trim();
        if (inner.startsWith("{")) inner = inner.substring(1);
        if (inner.endsWith("}"))   inner = inner.substring(0, inner.length() - 1);
        for (String pair : inner.split(",")) {
            String[] kv = pair.split(":", 2);
            if (kv.length == 2) {
                out.put(kv[0].trim().replaceAll("^\"|\"$", ""),
                        kv[1].trim().replaceAll("^\"|\"$", ""));
            }
        }
        return out;
    }
}
