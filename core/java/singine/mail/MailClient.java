package singine.mail;

import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.Base64;

/**
 * MailClient — minimal SMTP send + IMAP4rev1 search/fetch via raw TCP sockets.
 *
 * <p>Design principles:
 * <ul>
 *   <li>JDK 11+ stdlib only — no javax.mail, no external deps.
 *   <li>SMTP: RFC 5321 ESMTP with AUTH LOGIN (base64 credentials).
 *   <li>IMAP4: RFC 3501 — LOGIN, SELECT, SEARCH, FETCH (header fields only for speed).
 *   <li>XML envelope: every message is wrapped in a &lt;mail&gt; element with
 *       &lt;from&gt;, &lt;to&gt;, &lt;subject&gt;, &lt;date&gt;, &lt;uid&gt;,
 *       &lt;body-preview&gt; — minimal payload for efficient processing.
 *   <li>All network I/O uses 30-second timeouts.
 *   <li>Dry-run mode: returns synthetic responses without network connection.
 * </ul>
 *
 * <p>Usage from Clojure:
 * <pre>
 *   (import '[singine.mail MailClient])
 *   (def client (new MailClient "imap.gmail.com" 993 true))
 *   (.send client smtp-host smtp-port tls? user pass from to subject body)
 *   (.search client user pass folder search-term)
 *   (.fetchXml client user pass folder uids)
 * </pre>
 */
public class MailClient {

    private final String host;
    private final int    port;
    private final boolean tls;
    private static final int TIMEOUT_MS = 30_000;

    /** Create a MailClient for IMAP operations on the given host/port. */
    public MailClient(String host, int port, boolean tls) {
        this.host = host;
        this.port = port;
        this.tls  = tls;
    }

    // ── SMTP send ─────────────────────────────────────────────────────────────

    /**
     * Send a plain-text email via ESMTP AUTH LOGIN.
     *
     * @param smtpHost  SMTP server hostname
     * @param smtpPort  SMTP port (587 for STARTTLS, 465 for SMTPS, 25 for plain)
     * @param smtpTls   true if SSL/TLS from the start (port 465); false for STARTTLS or plain
     * @param user      SMTP username (usually the sender email address)
     * @param pass      SMTP password
     * @param from      sender address
     * @param to        recipient address (one; for multiple call multiple times)
     * @param subject   message subject
     * @param body      plain-text message body
     * @param dryRun    if true, return synthetic OK without connecting
     * @return          map-string "{:ok true :smtp-response \"...\"}"-style result map
     */
    public Map<String, Object> send(
            String smtpHost, int smtpPort, boolean smtpTls,
            String user, String pass,
            String from, String to, String subject, String body,
            boolean dryRun) {

        if (dryRun) {
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("ok",            true);
            r.put("dry-run",       true);
            r.put("smtp-host",     smtpHost);
            r.put("smtp-port",     smtpPort);
            r.put("from",          from);
            r.put("to",            to);
            r.put("subject",       subject);
            r.put("smtp-response", "250 OK (synthetic)");
            return r;
        }

        try {
            Socket sock = smtpTls
                ? javax.net.ssl.SSLSocketFactory.getDefault()
                      .createSocket(smtpHost, smtpPort)
                : new Socket();

            if (!smtpTls) {
                sock.connect(new InetSocketAddress(smtpHost, smtpPort), TIMEOUT_MS);
            }
            sock.setSoTimeout(TIMEOUT_MS);

            try (BufferedReader in  = new BufferedReader(
                                         new InputStreamReader(sock.getInputStream(),
                                                               StandardCharsets.UTF_8));
                 PrintWriter     out = new PrintWriter(
                                         new OutputStreamWriter(sock.getOutputStream(),
                                                                StandardCharsets.UTF_8),
                                         true)) {

                // Consume greeting
                String greeting = in.readLine();

                // EHLO
                out.println("EHLO singine.local");
                String ehloResp = readResponse(in);

                // AUTH LOGIN
                out.println("AUTH LOGIN");
                in.readLine(); // 334 VXNlcm5hbWU6
                out.println(base64(user));
                in.readLine(); // 334 UGFzc3dvcmQ6
                out.println(base64(pass));
                String authResp = in.readLine();
                if (!authResp.startsWith("235")) {
                    throw new IOException("SMTP AUTH failed: " + authResp);
                }

                // MAIL FROM
                out.println("MAIL FROM:<" + from + ">");
                String mfResp = in.readLine();

                // RCPT TO
                out.println("RCPT TO:<" + to + ">");
                String rtResp = in.readLine();

                // DATA
                out.println("DATA");
                in.readLine(); // 354 Start input

                // Message headers + body
                out.println("From: " + from);
                out.println("To: " + to);
                out.println("Subject: " + subject);
                out.println("MIME-Version: 1.0");
                out.println("Content-Type: text/plain; charset=UTF-8");
                out.println("X-Mailer: singine/mail-v1");
                out.println("");
                out.println(body);
                out.println(".");  // end of data

                String dataResp = in.readLine();

                // QUIT
                out.println("QUIT");
                in.readLine();

                Map<String, Object> r = new LinkedHashMap<>();
                r.put("ok",            true);
                r.put("smtp-host",     smtpHost);
                r.put("from",          from);
                r.put("to",            to);
                r.put("subject",       subject);
                r.put("smtp-response", dataResp);
                return r;
            } finally {
                sock.close();
            }
        } catch (Exception e) {
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("ok",    false);
            r.put("error", e.getMessage());
            return r;
        }
    }

    // ── IMAP search ───────────────────────────────────────────────────────────

    /**
     * Search a mailbox folder for messages matching a search term.
     *
     * <p>Searches subject, from, and body text (IMAP SEARCH OR FROM ... SUBJECT ...).
     * Returns a list of IMAP UIDs matching the search.
     *
     * @param user        IMAP username
     * @param pass        IMAP password
     * @param folder      mailbox folder (e.g. "INBOX")
     * @param searchTerm  keyword to search for in subject/from/body
     * @param maxResults  maximum number of UIDs to return
     * @param dryRun      if true, return synthetic UID list
     * @return list of UID strings
     */
    public List<String> search(String user, String pass, String folder,
                                String searchTerm, int maxResults, boolean dryRun) {
        if (dryRun) {
            return Arrays.asList("1001", "1002", "1003");
        }
        try {
            Socket sock = tls
                ? javax.net.ssl.SSLSocketFactory.getDefault().createSocket(host, port)
                : new Socket(host, port);
            sock.setSoTimeout(TIMEOUT_MS);

            try (BufferedReader in  = new BufferedReader(
                                         new InputStreamReader(sock.getInputStream(),
                                                               StandardCharsets.UTF_8));
                 PrintWriter    out = new PrintWriter(
                                         new OutputStreamWriter(sock.getOutputStream(),
                                                                StandardCharsets.UTF_8),
                                         true)) {

                String greeting = in.readLine(); // * OK ...

                // LOGIN
                out.println("A001 LOGIN " + quote(user) + " " + quote(pass));
                String loginResp = readUntilTag(in, "A001");

                // SELECT folder
                out.println("A002 SELECT " + quote(folder));
                String selectResp = readUntilTag(in, "A002");

                // SEARCH — OR FROM <term> SUBJECT <term>
                String safeSearchTerm = searchTerm.replaceAll("[\"\\\\]", "");
                out.println("A003 UID SEARCH OR FROM \"" + safeSearchTerm
                            + "\" OR SUBJECT \"" + safeSearchTerm
                            + "\" TEXT \"" + safeSearchTerm + "\"");

                List<String> uids = new ArrayList<>();
                String line;
                while ((line = in.readLine()) != null) {
                    if (line.startsWith("* SEARCH")) {
                        // * SEARCH 1001 1002 1003
                        String[] parts = line.substring(9).trim().split("\\s+");
                        for (int i = 0; i < parts.length && uids.size() < maxResults; i++) {
                            if (!parts[i].isEmpty()) uids.add(parts[i]);
                        }
                    }
                    if (line.startsWith("A003")) break;
                }

                // LOGOUT
                out.println("A004 LOGOUT");
                return uids;
            } finally {
                sock.close();
            }
        } catch (Exception e) {
            return Collections.singletonList("ERROR:" + e.getMessage());
        }
    }

    // ── IMAP fetch → XML ──────────────────────────────────────────────────────

    /**
     * Fetch messages by UID and return an XML document string.
     *
     * <p>Each message is wrapped in a &lt;mail&gt; element:
     * <pre>
     *   &lt;mail uid="1001" folder="INBOX"&gt;
     *     &lt;from&gt;sender@example.com&lt;/from&gt;
     *     &lt;to&gt;me@example.com&lt;/to&gt;
     *     &lt;subject&gt;Subject line&lt;/subject&gt;
     *     &lt;date&gt;Mon, 23 Feb 2026 10:00:00 +0000&lt;/date&gt;
     *     &lt;body-preview&gt;First 256 chars of body...&lt;/body-preview&gt;
     *   &lt;/mail&gt;
     * </pre>
     *
     * @param user    IMAP username
     * @param pass    IMAP password
     * @param folder  mailbox folder
     * @param uids    list of UIDs to fetch
     * @param dryRun  if true, return synthetic XML
     * @return XML string (UTF-8)
     */
    public String fetchXml(String user, String pass, String folder,
                           List<String> uids, boolean dryRun) {
        if (dryRun || uids.isEmpty()) {
            return "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
                 + "<mail-batch xmlns=\"urn:singine:mail\" count=\"" + uids.size() + "\" dry-run=\"true\">\n"
                 + "  <mail uid=\"1001\" folder=\"" + escXml(folder) + "\">\n"
                 + "    <from>sender@example.com</from>\n"
                 + "    <to>me@singine.local</to>\n"
                 + "    <subject>Test email about [[t/1]] governance</subject>\n"
                 + "    <date>Mon, 23 Feb 2026 10:00:00 +0000</date>\n"
                 + "    <body-preview>This is a dry-run synthetic email body preview.</body-preview>\n"
                 + "  </mail>\n"
                 + "</mail-batch>";
        }

        StringBuilder xml = new StringBuilder();
        xml.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n");
        xml.append("<mail-batch xmlns=\"urn:singine:mail\" count=\"")
           .append(uids.size()).append("\">\n");

        try {
            Socket sock = tls
                ? javax.net.ssl.SSLSocketFactory.getDefault().createSocket(host, port)
                : new Socket(host, port);
            sock.setSoTimeout(TIMEOUT_MS);

            try (BufferedReader in  = new BufferedReader(
                                         new InputStreamReader(sock.getInputStream(),
                                                               StandardCharsets.UTF_8));
                 PrintWriter    out = new PrintWriter(
                                         new OutputStreamWriter(sock.getOutputStream(),
                                                                StandardCharsets.UTF_8),
                                         true)) {

                in.readLine(); // greeting

                // LOGIN + SELECT
                out.println("B001 LOGIN " + quote(user) + " " + quote(pass));
                readUntilTag(in, "B001");
                out.println("B002 SELECT " + quote(folder));
                readUntilTag(in, "B002");

                int tagN = 3;
                for (String uid : uids) {
                    String tag = String.format("B%03d", tagN++);
                    // Fetch header fields only — minimal payload
                    out.println(tag + " UID FETCH " + uid
                                + " (BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)]"
                                + " BODY.PEEK[TEXT]<0.256>)");

                    Map<String, String> headers = new LinkedHashMap<>();
                    headers.put("from",    "");
                    headers.put("to",      "");
                    headers.put("subject", "");
                    headers.put("date",    "");
                    String bodyPreview = "";

                    String line;
                    while ((line = in.readLine()) != null) {
                        String lower = line.toLowerCase(Locale.ROOT);
                        if (lower.startsWith("from: "))    headers.put("from",    line.substring(6).trim());
                        if (lower.startsWith("to: "))      headers.put("to",      line.substring(4).trim());
                        if (lower.startsWith("subject: ")) headers.put("subject", line.substring(9).trim());
                        if (lower.startsWith("date: "))    headers.put("date",    line.substring(6).trim());
                        // Body preview: first non-empty line after blank header separator
                        if (line.isEmpty() && bodyPreview.isEmpty()) {
                            String bodyLine = in.readLine();
                            if (bodyLine != null) bodyPreview = bodyLine.substring(
                                0, Math.min(bodyLine.length(), 256));
                        }
                        if (line.startsWith(tag)) break;
                    }

                    xml.append("  <mail uid=\"").append(escXml(uid))
                       .append("\" folder=\"").append(escXml(folder)).append("\">\n");
                    for (Map.Entry<String, String> h : headers.entrySet()) {
                        xml.append("    <").append(h.getKey()).append(">")
                           .append(escXml(h.getValue()))
                           .append("</").append(h.getKey()).append(">\n");
                    }
                    xml.append("    <body-preview>").append(escXml(bodyPreview))
                       .append("</body-preview>\n");
                    xml.append("  </mail>\n");
                }

                out.println("B999 LOGOUT");

            } finally {
                sock.close();
            }
        } catch (Exception e) {
            xml.append("  <error>").append(escXml(e.getMessage())).append("</error>\n");
        }

        xml.append("</mail-batch>");
        return xml.toString();
    }

    // ── forward a message ─────────────────────────────────────────────────────

    /**
     * Forward a message (identified by UID) to one or more recipients.
     *
     * <p>Fetches the original message headers, prepends "Fwd: " to subject,
     * adds "Forwarded by: singine/mail-v1", and sends via SMTP.
     *
     * @param smtpHost  SMTP hostname
     * @param smtpPort  SMTP port
     * @param smtpTls   TLS flag
     * @param user      SMTP + IMAP username
     * @param pass      SMTP + IMAP password
     * @param fromAddr  sender address for the forwarded message
     * @param toAddr    recipient for forwarded message
     * @param uid       IMAP UID of the original message
     * @param folder    IMAP folder
     * @param dryRun    if true, return synthetic result
     * @return result map
     */
    public Map<String, Object> forward(
            String smtpHost, int smtpPort, boolean smtpTls,
            String user, String pass, String fromAddr, String toAddr,
            String uid, String folder, boolean dryRun) {

        if (dryRun) {
            Map<String, Object> r = new LinkedHashMap<>();
            r.put("ok",      true);
            r.put("dry-run", true);
            r.put("uid",     uid);
            r.put("from",    fromAddr);
            r.put("to",      toAddr);
            r.put("action",  "forward");
            r.put("subject", "Fwd: Test email (synthetic)");
            return r;
        }

        // Fetch the original message as XML, then re-send
        List<String> uidList = Collections.singletonList(uid);
        String xml = fetchXml(user, pass, folder, uidList, false);

        // Extract subject from XML (simple regex — no DOM needed)
        String origSubject = extractXmlText(xml, "subject");
        String fwdSubject  = origSubject.isEmpty() ? "Fwd: (no subject)" : "Fwd: " + origSubject;
        String origFrom    = extractXmlText(xml, "from");
        String origDate    = extractXmlText(xml, "date");
        String body        = extractXmlText(xml, "body-preview");

        String fwdBody = "---------- Forwarded message ----------\n"
                       + "From: " + origFrom + "\n"
                       + "Date: " + origDate + "\n"
                       + "\n" + body + "\n"
                       + "----------- Forwarded by singine/mail-v1 -----------";

        return send(smtpHost, smtpPort, smtpTls, user, pass,
                    fromAddr, toAddr, fwdSubject, fwdBody, false);
    }

    // ── git-controlled message versioning ─────────────────────────────────────

    /**
     * Return a git-ready plain-text representation of a fetched XML mail-batch.
     * Format: one file per message, path pattern: mail/&lt;folder&gt;/&lt;uid&gt;.eml.xml
     *
     * <p>Suitable for git-adding with a timestamp commit message.
     * The returned map has keys: path (string) → content (string).
     */
    public Map<String, String> toGitFiles(String xmlBatch, String baseDir) {
        Map<String, String> files = new LinkedHashMap<>();
        // Very simple: split on <mail uid= ... </mail> boundaries
        String[] parts = xmlBatch.split("(?=<mail uid=)");
        for (String part : parts) {
            if (!part.trim().startsWith("<mail")) continue;
            String uid    = extractXmlAttr(part, "uid");
            String folder = extractXmlAttr(part, "folder");
            if (uid.isEmpty()) continue;
            String path = baseDir + "/" + folder.replaceAll("[^a-zA-Z0-9_-]", "_")
                        + "/" + uid + ".eml.xml";
            files.put(path, "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n" + part.trim());
        }
        return files;
    }

    // ── helpers ───────────────────────────────────────────────────────────────

    private static String base64(String s) {
        return Base64.getEncoder().encodeToString(s.getBytes(StandardCharsets.UTF_8));
    }

    private static String quote(String s) {
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static String escXml(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");
    }

    private static String readResponse(BufferedReader in) throws IOException {
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = in.readLine()) != null) {
            sb.append(line).append("\n");
            // Multi-line SMTP responses end when a line has a space after the code
            if (line.length() >= 4 && line.charAt(3) == ' ') break;
        }
        return sb.toString();
    }

    private static String readUntilTag(BufferedReader in, String tag) throws IOException {
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = in.readLine()) != null) {
            sb.append(line).append("\n");
            if (line.startsWith(tag)) break;
        }
        return sb.toString();
    }

    private static String extractXmlText(String xml, String tag) {
        int start = xml.indexOf("<" + tag + ">");
        int end   = xml.indexOf("</" + tag + ">");
        if (start < 0 || end < 0) return "";
        return xml.substring(start + tag.length() + 2, end);
    }

    private static String extractXmlAttr(String xml, String attr) {
        String needle = attr + "=\"";
        int start = xml.indexOf(needle);
        if (start < 0) return "";
        start += needle.length();
        int end = xml.indexOf("\"", start);
        if (end < 0) return "";
        return xml.substring(start, end);
    }
}
