package singine.local;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * A trusted individual authorised to interact with the singine.local network.
 *
 * Each individual is identified by:
 *   - a stable URN    : urn:singine:individual:<id>
 *   - a role          : governs which HTTP routes and SSH operations are permitted
 *   - a publicKeyPem  : RSA public key for RS256 JWS verification (SSH-style cert auth)
 *   - custom claims   : injected into JWT payloads (scope, network, etc.)
 *
 * Serializes to the singine XML catalog format (collibra-catalog asset references)
 * and to EDN for Clojure interop.
 *
 * Role → permitted routes:
 *   API_CONSUMER        : POST /request, GET /catalog
 *   SSH_OPERATOR        : GET /ssh/access, POST /request
 *   CATALOG_READER      : GET /catalog, GET /dns
 *   CORTEX_BRIDGE_USER  : GET /bridge
 *   ADMIN               : all routes
 */
public final class TrustedIndividual {

    public enum Role {
        API_CONSUMER,
        SSH_OPERATOR,
        CATALOG_READER,
        CORTEX_BRIDGE_USER,
        ADMIN
    }

    private final String              id;
    private final String              name;
    private final String              urn;
    private final Role                role;
    private final String              email;
    private final String              grantedAt;
    private final String              publicKeyPem;
    private final Map<String, String> claims;

    public TrustedIndividual(
            String id, String name, Role role, String email,
            String grantedAt, String publicKeyPem, Map<String, String> claims) {
        this.id           = id;
        this.name         = name;
        this.urn          = "urn:singine:individual:" + id;
        this.role         = role;
        this.email        = email;
        this.grantedAt    = grantedAt;
        this.publicKeyPem = publicKeyPem == null ? "" : publicKeyPem;
        this.claims       = claims == null ? new LinkedHashMap<>() : new LinkedHashMap<>(claims);
    }

    // ── Accessors ─────────────────────────────────────────────────────────────

    public String              getId()           { return id; }
    public String              getName()         { return name; }
    public String              getUrn()          { return urn; }
    public Role                getRole()         { return role; }
    public String              getEmail()        { return email; }
    public String              getGrantedAt()    { return grantedAt; }
    public String              getPublicKeyPem() { return publicKeyPem; }
    public Map<String, String> getClaims()       { return claims; }

    /** Return a copy with the public key PEM set (after RSA key-pair generation). */
    public TrustedIndividual withPublicKeyPem(String pem) {
        return new TrustedIndividual(id, name, role, email, grantedAt, pem, claims);
    }

    // ── Authorisation helpers ─────────────────────────────────────────────────

    public boolean canAccessRoute(String routeId) {
        if (role == Role.ADMIN) return true;
        switch (routeId) {
            case SingineLocal.ROUTE_HEALTH:         return true;
            case SingineLocal.ROUTE_CATALOG:
            case SingineLocal.ROUTE_DNS:            return role == Role.CATALOG_READER
                                                        || role == Role.API_CONSUMER;
            case SingineLocal.ROUTE_REQUEST_CREATE: return role == Role.API_CONSUMER
                                                        || role == Role.SSH_OPERATOR;
            case SingineLocal.ROUTE_SSH_ACCESS:     return role == Role.SSH_OPERATOR;
            case SingineLocal.ROUTE_BRIDGE:         return role == Role.CORTEX_BRIDGE_USER;
            case SingineLocal.ROUTE_TRUSTED_INDEX:  return role == Role.ADMIN;
            default:                                return false;
        }
    }

    // ── Serialization ─────────────────────────────────────────────────────────

    /**
     * XML serialization aligned with singine XML catalog format.
     * Follows the elia-electricity skeleton pattern: collibra-catalog assets included.
     */
    public String toXml() {
        StringBuilder sb = new StringBuilder();
        sb.append("<trusted-individual id=\"").append(esc(id)).append("\">\n");
        sb.append("  <name>").append(esc(name)).append("</name>\n");
        sb.append("  <urn>").append(esc(urn)).append("</urn>\n");
        sb.append("  <role>").append(role.name().toLowerCase().replace('_', '-')).append("</role>\n");
        sb.append("  <email>").append(esc(email)).append("</email>\n");
        sb.append("  <granted-at>").append(esc(grantedAt)).append("</granted-at>\n");
        sb.append("  <collibra-catalog>\n");
        sb.append("    <asset assetType=\"TrustedIndividual\" collibraId=\"\" name=\"")
          .append(esc(name)).append("\"/>\n");
        sb.append("    <asset assetType=\"AccessRole\" collibraId=\"\" name=\"")
          .append(role.name()).append("\"/>\n");
        sb.append("  </collibra-catalog>\n");
        if (!publicKeyPem.isEmpty()) {
            sb.append("  <public-key encoding=\"pem\">").append(esc(publicKeyPem)).append("</public-key>\n");
        }
        if (!claims.isEmpty()) {
            sb.append("  <claims>\n");
            for (Map.Entry<String, String> e : claims.entrySet()) {
                sb.append("    <claim key=\"").append(esc(e.getKey())).append("\">")
                  .append(esc(e.getValue())).append("</claim>\n");
            }
            sb.append("  </claims>\n");
        }
        sb.append("</trusted-individual>\n");
        return sb.toString();
    }

    /** EDN serialization for Clojure interop. */
    public String toEdn() {
        return "{:individual/id \"" + id + "\"\n"
             + " :individual/name \"" + name + "\"\n"
             + " :individual/urn \"" + urn + "\"\n"
             + " :individual/role :" + role.name().toLowerCase() + "\n"
             + " :individual/email \"" + email + "\"\n"
             + " :individual/granted-at \"" + grantedAt + "\"}\n";
    }

    private static String esc(String s) {
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\"", "&quot;");
    }
}
