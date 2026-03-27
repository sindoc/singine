package singine.auth;

import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import javax.crypto.Mac;

/**
 * JwsToken — minimal JWT / JWS producer and verifier.
 *
 * Implements RFC 7515 (JWS) + RFC 7519 (JWT) using only JDK 11+ stdlib.
 * No external dependencies (no Nimbus JOSE, no Auth0 java-jwt).
 *
 * Supported algorithms:
 *   RS256 — RSA + SHA-256 (private key signs, public key verifies)
 *   HS256 — HMAC + SHA-256 (shared secret — symmetric, simpler but less IdP-suitable)
 *
 * JWT structure (compact serialisation):
 *   BASE64URL(header) . BASE64URL(payload) . BASE64URL(signature)
 *
 * Singine-specific claims added automatically:
 *   iss  — "urn:singine:idp"
 *   iat  — issued-at epoch seconds
 *   exp  — expiry epoch seconds (iat + ttlSeconds)
 *   jti  — random UUID (prevents replay)
 *   sid  — singine session URN: "urn:singine:session:<jti-prefix>"
 *
 * Usage (RS256):
 *   KeyPair kp = CertAuthority.generateKeyPair("singine-idp");
 *   String token = JwsToken.signRS256(kp.getPrivate(), claims, 3600);
 *   Map<String,Object> decoded = JwsToken.verify(token, kp.getPublic());
 *
 * Usage (HS256):
 *   String token = JwsToken.signHS256("my-secret", claims, 3600);
 *   Map<String,Object> decoded = JwsToken.verifyHS256("my-secret", token);
 */
public class JwsToken {

    // ── Sign RS256 ────────────────────────────────────────────────────────────

    /**
     * Creates a signed RS256 JWT.
     *
     * @param privateKey  RSA private key
     * @param claims      payload claims (String → Object values)
     * @param ttlSeconds  token lifetime in seconds
     * @return compact JWT string (header.payload.signature)
     */
    public static String signRS256(PrivateKey privateKey,
                                   Map<String, Object> claims,
                                   long ttlSeconds) throws Exception {
        String header  = base64UrlEncode(toJson(headerMap("RS256")));
        String payload = base64UrlEncode(toJson(enrichClaims(claims, ttlSeconds)));
        String signingInput = header + "." + payload;

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(privateKey);
        signer.update(signingInput.getBytes(StandardCharsets.UTF_8));
        byte[] sig = signer.sign();

        return signingInput + "." + base64UrlEncode(sig);
    }

    /**
     * Verifies an RS256 JWT and returns the decoded payload claims.
     *
     * @param token     compact JWT string
     * @param publicKey RSA public key
     * @return payload claims map (or throws if invalid/expired)
     */
    public static Map<String, Object> verifyRS256(String token,
                                                   PublicKey publicKey) throws Exception {
        String[] parts = splitToken(token);
        String signingInput = parts[0] + "." + parts[1];

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(publicKey);
        verifier.update(signingInput.getBytes(StandardCharsets.UTF_8));
        boolean valid = verifier.verify(base64UrlDecode(parts[2]));
        if (!valid) throw new SecurityException("JWS signature verification failed");

        Map<String, Object> claims = fromJson(new String(
                base64UrlDecode(parts[1]), StandardCharsets.UTF_8));
        checkExpiry(claims);
        return claims;
    }

    // ── Sign HS256 ────────────────────────────────────────────────────────────

    /**
     * Creates a signed HS256 JWT (symmetric HMAC-SHA256).
     *
     * @param secret     shared secret string
     * @param claims     payload claims
     * @param ttlSeconds token lifetime in seconds
     * @return compact JWT string
     */
    public static String signHS256(String secret,
                                   Map<String, Object> claims,
                                   long ttlSeconds) throws Exception {
        String header  = base64UrlEncode(toJson(headerMap("HS256")));
        String payload = base64UrlEncode(toJson(enrichClaims(claims, ttlSeconds)));
        String signingInput = header + "." + payload;

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new javax.crypto.spec.SecretKeySpec(
                secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        byte[] sig = mac.doFinal(signingInput.getBytes(StandardCharsets.UTF_8));

        return signingInput + "." + base64UrlEncode(sig);
    }

    /**
     * Verifies an HS256 JWT.
     *
     * @param secret shared secret
     * @param token  compact JWT string
     * @return payload claims map (or throws if invalid/expired)
     */
    public static Map<String, Object> verifyHS256(String secret,
                                                   String token) throws Exception {
        String[] parts = splitToken(token);
        String signingInput = parts[0] + "." + parts[1];

        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new javax.crypto.spec.SecretKeySpec(
                secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        byte[] expected = mac.doFinal(signingInput.getBytes(StandardCharsets.UTF_8));
        byte[] actual   = base64UrlDecode(parts[2]);

        if (!MessageDigest.isEqual(expected, actual)) {
            throw new SecurityException("HS256 signature verification failed");
        }

        Map<String, Object> claims = fromJson(new String(
                base64UrlDecode(parts[1]), StandardCharsets.UTF_8));
        checkExpiry(claims);
        return claims;
    }

    // ── Decode (without verification) ─────────────────────────────────────────

    /**
     * Decodes the payload claims without signature verification.
     * Useful for introspection and debugging.
     */
    public static Map<String, Object> decode(String token) throws Exception {
        String[] parts = splitToken(token);
        return fromJson(new String(base64UrlDecode(parts[1]), StandardCharsets.UTF_8));
    }

    /**
     * Decodes the header without signature verification.
     */
    public static Map<String, Object> decodeHeader(String token) throws Exception {
        String[] parts = splitToken(token);
        return fromJson(new String(base64UrlDecode(parts[0]), StandardCharsets.UTF_8));
    }

    // ── Internal helpers ──────────────────────────────────────────────────────

    private static Map<String, Object> headerMap(String alg) {
        Map<String, Object> h = new LinkedHashMap<>();
        h.put("alg", alg);
        h.put("typ", "JWT");
        return h;
    }

    private static Map<String, Object> enrichClaims(Map<String, Object> claims,
                                                      long ttlSeconds) {
        Map<String, Object> enriched = new LinkedHashMap<>(claims);
        long now = System.currentTimeMillis() / 1000L;
        String jti = UUID.randomUUID().toString();

        enriched.putIfAbsent("iss", "urn:singine:idp");
        enriched.putIfAbsent("iat", now);
        enriched.putIfAbsent("exp", now + ttlSeconds);
        enriched.putIfAbsent("jti", jti);
        enriched.putIfAbsent("sid", "urn:singine:session:" + jti.substring(0, 8));
        return enriched;
    }

    private static void checkExpiry(Map<String, Object> claims) throws Exception {
        Object expObj = claims.get("exp");
        if (expObj instanceof Number) {
            long exp = ((Number) expObj).longValue();
            long now = System.currentTimeMillis() / 1000L;
            if (now > exp) {
                throw new SecurityException("JWT expired at " + exp + " (now=" + now + ")");
            }
        }
    }

    private static String[] splitToken(String token) throws Exception {
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            throw new IllegalArgumentException(
                    "Invalid JWT: expected 3 parts, got " + parts.length);
        }
        return parts;
    }

    // ── Base64URL codec (RFC 4648 §5) ────────────────────────────────────────

    private static String base64UrlEncode(String s) {
        return base64UrlEncode(s.getBytes(StandardCharsets.UTF_8));
    }

    private static String base64UrlEncode(byte[] data) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(data);
    }

    private static byte[] base64UrlDecode(String s) {
        return Base64.getUrlDecoder().decode(s);
    }

    // ── Minimal JSON serialiser (avoids external deps) ────────────────────────

    /**
     * Converts a Map<String,Object> to a JSON string.
     * Supports: String, Number, Boolean, null, List, nested Map.
     */
    public static String toJson(Map<String, Object> map) {
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> e : map.entrySet()) {
            if (!first) sb.append(",");
            sb.append(jsonString(e.getKey())).append(":").append(jsonValue(e.getValue()));
            first = false;
        }
        sb.append("}");
        return sb.toString();
    }

    @SuppressWarnings("unchecked")
    private static String jsonValue(Object v) {
        if (v == null)                    return "null";
        if (v instanceof Boolean)         return v.toString();
        if (v instanceof Number)          return v.toString();
        if (v instanceof String)          return jsonString((String) v);
        if (v instanceof Map)             return toJson((Map<String, Object>) v);
        if (v instanceof List) {
            List<?> list = (List<?>) v;
            StringBuilder sb = new StringBuilder("[");
            for (int i = 0; i < list.size(); i++) {
                if (i > 0) sb.append(",");
                sb.append(jsonValue(list.get(i)));
            }
            sb.append("]");
            return sb.toString();
        }
        return jsonString(v.toString());
    }

    private static String jsonString(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"")
                       .replace("\n", "\\n").replace("\r", "\\r")
                       .replace("\t", "\\t") + "\"";
    }

    /**
     * Parses a flat or nested JSON object string into Map<String,Object>.
     * Handles: strings, longs, doubles, booleans, null, nested objects.
     * This is a purpose-built minimal parser — not a general JSON library.
     */
    public static Map<String, Object> fromJson(String json) throws Exception {
        json = json.trim();
        if (!json.startsWith("{") || !json.endsWith("}")) {
            throw new IllegalArgumentException("Not a JSON object: " + json);
        }
        Map<String, Object> result = new LinkedHashMap<>();
        String inner = json.substring(1, json.length() - 1).trim();
        if (inner.isEmpty()) return result;

        // Simple tokeniser: split on comma at top level
        List<String> pairs = splitTopLevel(inner, ',');
        for (String pair : pairs) {
            int colon = pair.indexOf(':');
            if (colon < 0) continue;
            String key = pair.substring(0, colon).trim();
            String val = pair.substring(colon + 1).trim();
            // Unquote key
            if (key.startsWith("\"")) key = key.substring(1, key.length() - 1);
            result.put(key, parseValue(val));
        }
        return result;
    }

    private static Object parseValue(String val) throws Exception {
        val = val.trim();
        if (val.equals("null"))  return null;
        if (val.equals("true"))  return Boolean.TRUE;
        if (val.equals("false")) return Boolean.FALSE;
        if (val.startsWith("\"")) return val.substring(1, val.length() - 1)
                .replace("\\\"", "\"").replace("\\\\", "\\")
                .replace("\\n", "\n").replace("\\r", "\r").replace("\\t", "\t");
        if (val.startsWith("{"))  return fromJson(val);
        // JSON array → List
        if (val.startsWith("[")) {
            List<Object> list = new ArrayList<>();
            String inner = val.substring(1, val.length() - 1).trim();
            if (!inner.isEmpty()) {
                for (String item : splitTopLevel(inner, ',')) {
                    list.add(parseValue(item.trim()));
                }
            }
            return list;
        }
        // Number
        if (val.contains(".")) {
            try { return Double.parseDouble(val); } catch (NumberFormatException e) { return val; }
        }
        try { return Long.parseLong(val); } catch (NumberFormatException e) { return val; }
    }

    private static List<String> splitTopLevel(String s, char sep) {
        List<String> parts = new ArrayList<>();
        int depth = 0;
        boolean inString = false;
        int start = 0;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '"' && (i == 0 || s.charAt(i-1) != '\\')) inString = !inString;
            if (!inString) {
                if (c == '{' || c == '[') depth++;
                else if (c == '}' || c == ']') depth--;
                else if (c == sep && depth == 0) {
                    parts.add(s.substring(start, i).trim());
                    start = i + 1;
                }
            }
        }
        if (start < s.length()) parts.add(s.substring(start).trim());
        return parts;
    }
}
