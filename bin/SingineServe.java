///usr/bin/env jbang "$0" "$@" ; exit $?
// Or: java SingineServe.java [port] [webroot]
// Requires Java 11+. No dependencies.
/**
 * SingineServe — singine's Java HTTP appserver for SilkPage documents.
 *
 * - Serves static files from webroot
 * - Applies cv.xsl XSLT transformation to cv-data.xml on every GET /cv/
 * - API endpoints:
 *     GET  /api/cv/status              → JSON server info
 *     GET  /api/cv/download?format=pdf|rtf|html|md   → file download
 *     POST /api/cv/regenerate          → re-apply XSLT, return JSON
 *
 * Usage:
 *   java bin/SingineServe.java [port] [webroot]
 *   singine serve [--port 4242]
 *
 * Defaults:
 *   port    = 4242
 *   webroot = ../../silkpage/main/silkpage/www
 */

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;

import javax.xml.transform.*;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;
import java.io.*;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.logging.Level;
import java.util.logging.Logger;

public class SingineServe {

    static final Logger LOG = Logger.getLogger("SingineServe");

    static final Map<String, String> MIME = new HashMap<>();
    static {
        MIME.put(".html",  "text/html; charset=utf-8");
        MIME.put(".css",   "text/css; charset=utf-8");
        MIME.put(".js",    "application/javascript; charset=utf-8");
        MIME.put(".mjs",   "application/javascript; charset=utf-8");
        MIME.put(".json",  "application/json; charset=utf-8");
        MIME.put(".xml",   "application/xml; charset=utf-8");
        MIME.put(".xsl",   "application/xslt+xml; charset=utf-8");
        MIME.put(".xsd",   "application/xml; charset=utf-8");
        MIME.put(".svg",   "image/svg+xml");
        MIME.put(".png",   "image/png");
        MIME.put(".jpg",   "image/jpeg");
        MIME.put(".jpeg",  "image/jpeg");
        MIME.put(".ico",   "image/x-icon");
        MIME.put(".pdf",   "application/pdf");
        MIME.put(".rtf",   "application/rtf");
        MIME.put(".ttf",   "font/ttf");
        MIME.put(".woff",  "font/woff");
        MIME.put(".woff2", "font/woff2");
        MIME.put(".txt",   "text/plain; charset=utf-8");
        MIME.put(".md",    "text/markdown; charset=utf-8");
    }

    static volatile Path WEBROOT;

    public static void main(String[] args) throws Exception {
        int port = args.length > 0 ? Integer.parseInt(args[0]) : 4242;
        String envRoot = System.getenv("SINGINE_WEBROOT");
        if (args.length > 1) {
            WEBROOT = Path.of(args[1]).toAbsolutePath().normalize();
        } else if (envRoot != null) {
            WEBROOT = Path.of(envRoot).toAbsolutePath().normalize();
        } else {
            Path here = Path.of(SingineServe.class.getProtectionDomain()
                    .getCodeSource().getLocation().toURI()).toAbsolutePath().normalize();
            // bin/ → singine/ → ws/ → silkpage/main/silkpage/www
            WEBROOT = here.getParent().getParent()
                    .resolve("../../silkpage/main/silkpage/www")
                    .toAbsolutePath().normalize();
        }

        if (!Files.isDirectory(WEBROOT)) {
            System.err.println("singine-serve: webroot not found: " + WEBROOT);
            System.err.println("  Set SINGINE_WEBROOT or pass as second argument.");
            System.exit(1);
        }

        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", port), 0);
        server.createContext("/api/cv/",  new CvApiHandler());
        server.createContext("/cv/",      new CvPageHandler());
        server.createContext("/",         new StaticHandler());
        server.setExecutor(Executors.newCachedThreadPool());
        server.start();

        System.out.println("singine-serve (Java · XSLT) running");
        System.out.println("  webroot  " + WEBROOT);
        System.out.println("  url      http://localhost:" + port + "/");
        System.out.println("  cv       http://localhost:" + port + "/cv/");
        System.out.println("  api      http://localhost:" + port + "/api/cv/status");
        System.out.println();
        System.out.println("  Ctrl+C to stop");
    }

    // ── CV page handler — applies XSLT on every request ───────────────────

    static class CvPageHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange ex) throws IOException {
            if (!"GET".equalsIgnoreCase(ex.getRequestMethod()) &&
                !"HEAD".equalsIgnoreCase(ex.getRequestMethod())) {
                send(ex, 405, "text/plain", "405 Method Not Allowed".getBytes());
                return;
            }
            Path dataXml = WEBROOT.resolve("cv/cv-data.xml");
            Path stylesheet = WEBROOT.resolve("cv/cv.xsl");

            // Fall back to static index.html if either XSLT file is absent
            if (!Files.isRegularFile(dataXml) || !Files.isRegularFile(stylesheet)) {
                Path idx = WEBROOT.resolve("cv/index.html");
                if (Files.isRegularFile(idx)) {
                    sendFile(ex, idx);
                } else {
                    send(ex, 404, "text/plain; charset=utf-8",
                         "cv/index.html not found".getBytes(StandardCharsets.UTF_8));
                }
                return;
            }

            try {
                byte[] html = applyXslt(dataXml, stylesheet);
                ex.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
                ex.getResponseHeaders().set("Cache-Control", "no-cache");
                ex.sendResponseHeaders(200, html.length);
                if (!"HEAD".equalsIgnoreCase(ex.getRequestMethod())) {
                    try (OutputStream os = ex.getResponseBody()) { os.write(html); }
                } else {
                    ex.getResponseBody().close();
                }
            } catch (TransformerException te) {
                String err = "XSLT error: " + te.getMessage();
                LOG.log(Level.SEVERE, err, te);
                send(ex, 500, "text/plain; charset=utf-8",
                     err.getBytes(StandardCharsets.UTF_8));
            }
        }

        private void sendFile(HttpExchange ex, Path file) throws IOException {
            byte[] body = Files.readAllBytes(file);
            ex.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
            ex.sendResponseHeaders(200, body.length);
            try (OutputStream os = ex.getResponseBody()) { os.write(body); }
        }
    }

    // ── CV API handler ─────────────────────────────────────────────────────

    static class CvApiHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange ex) throws IOException {
            String path = ex.getRequestURI().getPath();

            if (path.endsWith("/status")) {
                handleStatus(ex);
            } else if (path.endsWith("/download")) {
                handleDownload(ex);
            } else if (path.endsWith("/regenerate")) {
                handleRegenerate(ex);
            } else {
                send(ex, 404, "text/plain", "Not found".getBytes());
            }
        }

        private void handleStatus(HttpExchange ex) throws IOException {
            String json = "{\"ok\":true,\"url\":\"http://localhost/cv/\","
                + "\"webroot\":\"" + jsonEscape(WEBROOT.toString()) + "\","
                + "\"xslt\":\"cv.xsl\",\"data\":\"cv-data.xml\","
                + "\"timestamp\":\"" + Instant.now() + "\"}";
            send(ex, 200, "application/json; charset=utf-8",
                 json.getBytes(StandardCharsets.UTF_8));
        }

        private void handleDownload(HttpExchange ex) throws IOException {
            String query = ex.getRequestURI().getRawQuery();
            String format = queryParam(query, "format");
            if (format == null) format = "html";

            try {
                byte[] data;
                String mime;
                String filename;

                switch (format) {
                    case "html": {
                        Path xsl  = WEBROOT.resolve("cv/cv.xsl");
                        Path xml  = WEBROOT.resolve("cv/cv-data.xml");
                        data      = (Files.isRegularFile(xsl) && Files.isRegularFile(xml))
                                    ? applyXslt(xml, xsl)
                                    : Files.readAllBytes(WEBROOT.resolve("cv/index.html"));
                        mime      = "text/html; charset=utf-8";
                        filename  = "cv-sina-heshmati.html";
                        break;
                    }
                    case "pdf": {
                        Path out  = tempFile("cv-sina-heshmati", ".pdf");
                        runSingine("cv", "pdf", "--output", out.toString());
                        data      = Files.readAllBytes(out);
                        mime      = "application/pdf";
                        filename  = "cv-sina-heshmati.pdf";
                        Files.deleteIfExists(out);
                        break;
                    }
                    case "rtf": {
                        Path out  = tempFile("cv-sina-heshmati", ".rtf");
                        runSingine("cv", "rtf", "--output", out.toString());
                        data      = Files.readAllBytes(out);
                        mime      = "application/rtf";
                        filename  = "cv-sina-heshmati.rtf";
                        Files.deleteIfExists(out);
                        break;
                    }
                    case "md": {
                        Path src  = singineResult("cv", "md");
                        data      = Files.readAllBytes(src);
                        mime      = "text/markdown; charset=utf-8";
                        filename  = "cv-sina-heshmati.md";
                        break;
                    }
                    default:
                        send(ex, 400, "text/plain",
                             ("Unknown format: " + format).getBytes());
                        return;
                }

                ex.getResponseHeaders().set("Content-Type", mime);
                ex.getResponseHeaders().set("Content-Disposition",
                        "attachment; filename=\"" + filename + "\"");
                ex.getResponseHeaders().set("Cache-Control", "no-cache");
                ex.sendResponseHeaders(200, data.length);
                try (OutputStream os = ex.getResponseBody()) { os.write(data); }

            } catch (Exception e) {
                String msg = "Generation failed: " + e.getMessage();
                LOG.log(Level.SEVERE, msg, e);
                send(ex, 500, "text/plain; charset=utf-8",
                     msg.getBytes(StandardCharsets.UTF_8));
            }
        }

        private void handleRegenerate(HttpExchange ex) throws IOException {
            // Re-applies XSLT — the CV page already does this on every request,
            // so we just confirm the files are present and return a timestamp.
            boolean ok = Files.isRegularFile(WEBROOT.resolve("cv/cv-data.xml"))
                      && Files.isRegularFile(WEBROOT.resolve("cv/cv.xsl"));
            String ts = Instant.now().toString();
            String json = ok
                ? "{\"ok\":true,\"timestamp\":\"" + ts + "\"}"
                : "{\"ok\":false,\"error\":\"cv-data.xml or cv.xsl not found\",\"timestamp\":\"" + ts + "\"}";
            send(ex, ok ? 200 : 404, "application/json; charset=utf-8",
                 json.getBytes(StandardCharsets.UTF_8));
        }

        /** Run `singine <args>` and return the trimmed stdout as a Path. */
        private Path singineResult(String... args) throws Exception {
            String[] cmd = buildCmd(args);
            Process p = Runtime.getRuntime().exec(cmd);
            String out = new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
            p.waitFor();
            return Path.of(out);
        }

        /** Run `singine <args>` — used for pdf/rtf with --output. */
        private void runSingine(String... args) throws Exception {
            String[] cmd = buildCmd(args);
            Process p = new ProcessBuilder(cmd)
                    .redirectErrorStream(true)
                    .start();
            String out = new String(p.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            int rc = p.waitFor();
            if (rc != 0) throw new RuntimeException("singine exited " + rc + ": " + out);
        }

        private String[] buildCmd(String[] args) {
            String singine = resolveSingine();
            // Wrap as: python3 -m singine.command <args>  when the singine script isn't found
            String[] cmd;
            if (singine.endsWith(".py") || singine.contains("python")) {
                // python3 -m singine.command <args>
                cmd = new String[args.length + 3];
                cmd[0] = singine; cmd[1] = "-m"; cmd[2] = "singine.command";
                System.arraycopy(args, 0, cmd, 3, args.length);
            } else {
                cmd = new String[args.length + 1];
                cmd[0] = singine;
                System.arraycopy(args, 0, cmd, 1, args.length);
            }
            return cmd;
        }

        private static String resolveSingine() {
            // 1. Explicit override
            String env = System.getenv("SINGINE_CMD");
            if (env != null && !env.isEmpty()) return env;
            // 2. Common pip user-install locations
            String home = System.getProperty("user.home");
            for (String candidate : new String[]{
                home + "/Library/Python/3.9/bin/singine",
                home + "/Library/Python/3.11/bin/singine",
                home + "/Library/Python/3.12/bin/singine",
                home + "/.local/bin/singine",
                "/usr/local/bin/singine",
            }) {
                if (new java.io.File(candidate).canExecute()) return candidate;
            }
            // 3. Fall back to PATH lookup
            return "singine";
        }

        private Path tempFile(String prefix, String suffix) throws IOException {
            return Files.createTempFile(prefix, suffix);
        }
    }

    // ── Static file handler (vhost-aware) ─────────────────────────────────

    static class StaticHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange ex) throws IOException {
            if (!"GET".equalsIgnoreCase(ex.getRequestMethod()) &&
                !"HEAD".equalsIgnoreCase(ex.getRequestMethod())) {
                send(ex, 405, "text/plain", "405 Method Not Allowed".getBytes());
                return;
            }
            String raw = ex.getRequestURI().getPath();
            if (raw == null || raw.isEmpty()) raw = "/";
            String decoded = URI.create(raw).getPath();
            if (decoded.endsWith("/")) decoded += "index.html";

            // Vhost routing: if Host header matches a www/<vhost>/ directory,
            // check there first for the requested path before falling back to webroot.
            String host = ex.getRequestHeaders().getFirst("Host");
            if (host != null) {
                host = host.replaceAll(":\\d+$", ""); // strip port
                Path vhostDir = WEBROOT.resolve(host).normalize();
                if (vhostDir.startsWith(WEBROOT) && Files.isDirectory(vhostDir)) {
                    Path vhostFile = vhostDir.resolve("." + decoded).normalize();
                    if (vhostFile.startsWith(vhostDir) && Files.isRegularFile(vhostFile)) {
                        sendFile(ex, vhostFile); return;
                    }
                    // For bare '/' requests on a known vhost, serve vhost/index.html
                    if (decoded.equals("/index.html")) {
                        Path idx = vhostDir.resolve("index.html");
                        if (Files.isRegularFile(idx)) { sendFile(ex, idx); return; }
                    }
                }
            }

            Path abs = WEBROOT.resolve("." + decoded).normalize();
            if (!abs.startsWith(WEBROOT)) {
                send(ex, 403, "text/plain", "403 Forbidden".getBytes()); return;
            }
            if (Files.isDirectory(abs)) abs = abs.resolve("index.html");
            if (!Files.isRegularFile(abs)) {
                byte[] body = ("404 Not Found: " + decoded).getBytes(StandardCharsets.UTF_8);
                send(ex, 404, "text/plain; charset=utf-8", body); return;
            }
            sendFile(ex, abs);
        }

        private void sendFile(HttpExchange ex, Path file) throws IOException {
            String mime = MIME.getOrDefault(ext(file.getFileName().toString()),
                                             "application/octet-stream");
            byte[] body = Files.readAllBytes(file);
            ex.getResponseHeaders().set("Content-Type", mime);
            ex.sendResponseHeaders(200, body.length);
            if (!"HEAD".equalsIgnoreCase(ex.getRequestMethod())) {
                try (OutputStream os = ex.getResponseBody()) { os.write(body); }
            } else {
                ex.getResponseBody().close();
            }
        }
    }

    // ── XSLT helper ────────────────────────────────────────────────────────

    static byte[] applyXslt(Path xml, Path xsl) throws TransformerException {
        TransformerFactory factory = TransformerFactory.newInstance();
        Transformer t = factory.newTransformer(
                new StreamSource(xsl.toFile()));
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        t.transform(new StreamSource(xml.toFile()), new StreamResult(baos));
        return baos.toByteArray();
    }

    // ── Shared helpers ─────────────────────────────────────────────────────

    static void send(HttpExchange ex, int code, String mime, byte[] body) throws IOException {
        ex.getResponseHeaders().set("Content-Type", mime);
        ex.sendResponseHeaders(code, body.length);
        try (OutputStream os = ex.getResponseBody()) { os.write(body); }
    }

    static String ext(String filename) {
        int i = filename.lastIndexOf('.');
        return i < 0 ? "" : filename.substring(i).toLowerCase();
    }

    static String queryParam(String query, String name) {
        if (query == null) return null;
        for (String pair : query.split("&")) {
            String[] kv = pair.split("=", 2);
            try {
                if (kv.length == 2 && URLDecoder.decode(kv[0], "UTF-8").equals(name))
                    return URLDecoder.decode(kv[1], "UTF-8");
            } catch (UnsupportedEncodingException ignored) {}
        }
        return null;
    }

    static String jsonEscape(String s) {
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
