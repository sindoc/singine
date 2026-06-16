///usr/bin/env jbang "$0" "$@" ; exit $?
// Or: java SingineServe.java [port] [webroot]
// Requires Java 11+. No dependencies.
/**
 * SingineServe — singine's Java HTTP appserver for SilkPage documents.
 *
 * Single-file Java server using com.sun.net.httpserver (built into every JDK).
 * Serves the SilkPage www/ webroot statically.
 *
 * Usage:
 *   java bin/SingineServe.java [port] [webroot]
 *
 * Defaults:
 *   port    = 4242
 *   webroot = ../../silkpage/main/silkpage/www  (relative to singine repo root)
 *
 * Routes:
 *   GET /     → index.html
 *   GET /cv/  → cv/index.html
 *   GET /**   → static file
 */

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import java.io.*;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Map;
import java.util.concurrent.Executors;

public class SingineServe {

    static final Map<String, String> MIME = Map.ofEntries(
        Map.entry(".html",  "text/html; charset=utf-8"),
        Map.entry(".css",   "text/css; charset=utf-8"),
        Map.entry(".js",    "application/javascript; charset=utf-8"),
        Map.entry(".mjs",   "application/javascript; charset=utf-8"),
        Map.entry(".json",  "application/json; charset=utf-8"),
        Map.entry(".xml",   "application/xml; charset=utf-8"),
        Map.entry(".xsl",   "application/xslt+xml; charset=utf-8"),
        Map.entry(".xsd",   "application/xml; charset=utf-8"),
        Map.entry(".svg",   "image/svg+xml"),
        Map.entry(".png",   "image/png"),
        Map.entry(".jpg",   "image/jpeg"),
        Map.entry(".jpeg",  "image/jpeg"),
        Map.entry(".ico",   "image/x-icon"),
        Map.entry(".pdf",   "application/pdf"),
        Map.entry(".ttf",   "font/ttf"),
        Map.entry(".woff",  "font/woff"),
        Map.entry(".woff2", "font/woff2"),
        Map.entry(".txt",   "text/plain; charset=utf-8")
    );

    public static void main(String[] args) throws Exception {
        int    port    = args.length > 0 ? Integer.parseInt(args[0]) : 4242;
        String envRoot = System.getenv("SINGINE_WEBROOT");

        Path webroot;
        if (args.length > 1) {
            webroot = Path.of(args[1]).toAbsolutePath().normalize();
        } else if (envRoot != null) {
            webroot = Path.of(envRoot).toAbsolutePath().normalize();
        } else {
            // Default: singine repo root → sibling silkpage www/
            Path binDir  = Path.of(SingineServe.class.getProtectionDomain()
                                    .getCodeSource().getLocation().toURI()).getParent();
            Path repoRoot = binDir.getParent();          // singine/
            webroot = repoRoot.resolve("../../silkpage/main/silkpage/www")
                              .toAbsolutePath().normalize();
        }

        if (!Files.isDirectory(webroot)) {
            System.err.println("singine-serve: webroot not found: " + webroot);
            System.err.println("  Set SINGINE_WEBROOT or pass as second argument.");
            System.exit(1);
        }

        final Path root = webroot;
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/", new StaticHandler(root));
        server.setExecutor(Executors.newCachedThreadPool());
        server.start();

        System.out.println("singine-serve (Java) running");
        System.out.println("  webroot  " + root);
        System.out.println("  url      http://localhost:" + port + "/");
        System.out.println("  cv       http://localhost:" + port + "/cv/");
        System.out.println();
        System.out.println("  Ctrl+C to stop");
    }

    static class StaticHandler implements HttpHandler {
        private final Path root;
        StaticHandler(Path root) { this.root = root; }

        @Override
        public void handle(HttpExchange ex) throws IOException {
            if (!"GET".equalsIgnoreCase(ex.getRequestMethod()) &&
                !"HEAD".equalsIgnoreCase(ex.getRequestMethod())) {
                send(ex, 405, "text/plain", "405 Method Not Allowed".getBytes());
                return;
            }

            String rawPath = ex.getRequestURI().getPath();
            if (rawPath == null || rawPath.isEmpty()) rawPath = "/";

            // Decode and normalise
            String decoded = URI.create(rawPath).getPath();
            if (decoded.endsWith("/")) decoded += "index.html";

            Path abs = root.resolve("." + decoded).normalize();

            // Reject path traversal
            if (!abs.startsWith(root)) {
                send(ex, 403, "text/plain", "403 Forbidden".getBytes());
                return;
            }

            // If it's a directory, try index.html
            if (Files.isDirectory(abs)) abs = abs.resolve("index.html");

            if (!Files.isRegularFile(abs)) {
                byte[] body = ("404 Not Found: " + decoded).getBytes(StandardCharsets.UTF_8);
                send(ex, 404, "text/plain; charset=utf-8", body);
                return;
            }

            String ext  = ext(abs.getFileName().toString());
            String mime = MIME.getOrDefault(ext, "application/octet-stream");
            byte[] body = Files.readAllBytes(abs);

            ex.getResponseHeaders().set("Content-Type", mime);
            ex.sendResponseHeaders(200, body.length);
            if (!"HEAD".equalsIgnoreCase(ex.getRequestMethod())) {
                try (OutputStream os = ex.getResponseBody()) { os.write(body); }
            } else {
                ex.getResponseBody().close();
            }
        }

        private static void send(HttpExchange ex, int code, String mime, byte[] body)
                throws IOException {
            ex.getResponseHeaders().set("Content-Type", mime);
            ex.sendResponseHeaders(code, body.length);
            try (OutputStream os = ex.getResponseBody()) { os.write(body); }
        }

        private static String ext(String filename) {
            int i = filename.lastIndexOf('.');
            return i < 0 ? "" : filename.substring(i).toLowerCase();
        }
    }
}
