package singine.local;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;

/**
 * HTTP client for singine.local:2000.
 *
 * Connects to 127.0.0.1:<port> (actual socket address) while sending
 * "Host: singine.local" in every request — preserving the canonical
 * singine.local identity at the HTTP layer without requiring a system DNS entry.
 *
 * All responses are returned as {@link SingineLocalResponse} which carries:
 *   - HTTP status
 *   - Content-Type
 *   - response body (String)
 *   - singine-specific headers (X-Singine-Host, X-Singine-Port, X-Singine-Catalog)
 *
 * JWS tokens are attached as: Authorization: Bearer <token>
 * Tokens are obtained from callers and are not generated here.
 */
public final class SingineLocalClient {

    /** HTTP response carrier. */
    public static final class SingineLocalResponse {
        public final int    status;
        public final String contentType;
        public final String body;
        public final String singineHost;
        public final String singinePort;
        public final String singineCatalog;

        SingineLocalResponse(int status, String contentType, String body,
                             String singineHost, String singinePort, String singineCatalog) {
            this.status          = status;
            this.contentType     = contentType;
            this.body            = body;
            this.singineHost     = singineHost;
            this.singinePort     = singinePort;
            this.singineCatalog  = singineCatalog;
        }

        public boolean isOk()       { return status >= 200 && status < 300; }
        public boolean isXml()      { return contentType != null && contentType.contains("xml"); }
        public boolean isJson()     { return contentType != null && contentType.contains("json"); }
        public boolean bodyContains(String fragment) { return body != null && body.contains(fragment); }
    }

    private final int    port;
    private final String token; // may be null for unauthenticated requests

    public SingineLocalClient(int port, String token) {
        this.port  = port;
        this.token = token;
    }

    /** Unauthenticated client (for /health and negative auth tests). */
    public static SingineLocalClient unauthenticated(int port) {
        return new SingineLocalClient(port, null);
    }

    // ── HTTP methods ──────────────────────────────────────────────────────────

    public SingineLocalResponse get(String path) throws IOException {
        return execute("GET", path, null);
    }

    public SingineLocalResponse post(String path, String body) throws IOException {
        return execute("POST", path, body);
    }

    // ── Core ──────────────────────────────────────────────────────────────────

    private SingineLocalResponse execute(String method, String path, String requestBody)
            throws IOException {
        URL url = new URL("http://127.0.0.1:" + port + path);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod(method);

        // Always assert singine.local as the canonical host
        conn.setRequestProperty("Host",         SingineLocal.DEFAULT_HOST + ":" + SingineLocal.DEFAULT_PORT);
        conn.setRequestProperty("Accept",        "*/*");
        conn.setRequestProperty("X-Singine-Client", "singine.local.java");

        if (token != null) {
            conn.setRequestProperty("Authorization", "Bearer " + token);
        }
        if (requestBody != null) {
            byte[] bytes = requestBody.getBytes(StandardCharsets.UTF_8);
            conn.setDoOutput(true);
            conn.setRequestProperty("Content-Type",   "application/json; charset=utf-8");
            conn.setRequestProperty("Content-Length",  String.valueOf(bytes.length));
            try (OutputStream os = conn.getOutputStream()) { os.write(bytes); }
        }

        int status = conn.getResponseCode();
        InputStream stream = status < 400 ? conn.getInputStream() : conn.getErrorStream();
        String body = stream == null ? "" : new String(stream.readAllBytes(), StandardCharsets.UTF_8);

        return new SingineLocalResponse(
            status,
            conn.getContentType(),
            body,
            conn.getHeaderField("X-Singine-Host"),
            conn.getHeaderField("X-Singine-Port"),
            conn.getHeaderField("X-Singine-Catalog"));
    }
}
