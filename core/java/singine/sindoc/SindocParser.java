package singine.sindoc;

import org.w3c.dom.Element;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;

/**
 * SindocParser — parses a .sindoc file into a {@link SindocDocument}.
 *
 * The parser is data-driven: its behaviour is determined by the rules
 * loaded from the .meta hierarchy via {@link MetaLoader}.
 *
 * Parsing model
 * ─────────────
 * A .sindoc file is divided into:
 *
 *   HEADER  — leading #-directives (@lang, @version, @namespace)
 *   BODY    — prose lines and @-annotations until the first separator (--)
 *   SECTION — a separator + content (timestamp or close) + optional separator
 *
 * Each line is classified against the meta rules in priority order:
 *   1. separator    (#pattern: "--\n")
 *   2. close        (#pattern: "</>")
 *   3. timestamp    (#pattern: "<timestamp/>")
 *   4. directive    (#pattern: "#<identifier>")
 *   5. annotation   (#pattern: "@<identifier>")
 *   6. prose-line   (everything else)
 *
 * The resulting DOM looks like:
 *
 *   &lt;document lang="..." version="..." namespace="..." source-file="..."&gt;
 *     &lt;header&gt;
 *       &lt;lang name="racket"/&gt;
 *       &lt;version value="1.0"/&gt;
 *     &lt;/header&gt;
 *     &lt;body&gt;
 *       &lt;line n="3"&gt;prose text&lt;/line&gt;
 *       &lt;annotation name="rule"&gt;lang-declaration&lt;/annotation&gt;
 *     &lt;/body&gt;
 *     &lt;section type="timestamp"&gt;
 *       &lt;separator/&gt;
 *       &lt;timestamp value="" format="iso8601"/&gt;
 *       &lt;separator/&gt;
 *     &lt;/section&gt;
 *     &lt;section type="close"&gt;
 *       &lt;separator/&gt;
 *       &lt;close/&gt;
 *     &lt;/section&gt;
 *   &lt;/document&gt;
 */
public class SindocParser {

    // ── Compiled patterns ──────────────────────────────────────────

    private static final Pattern P_SEPARATOR   = Pattern.compile("^--\\s*$");
    private static final Pattern P_CLOSE       = Pattern.compile("^</>\\s*$");
    private static final Pattern P_TIMESTAMP   = Pattern.compile("^<timestamp(?:\\s+value=[\"']([^\"']*)[\"'])?/>\\s*$");
    private static final Pattern P_DIRECTIVE   = Pattern.compile("^(#\\w+)(.*)$");
    private static final Pattern P_ANNOTATION  = Pattern.compile("^(@\\w+)(.*)$");
    private static final Pattern P_ARABIC      = Pattern.compile("^[\\u0622-\\u06CC]");  // آ-ی
    private static final Pattern P_LATIN_AX    = Pattern.compile("^[a-x]");

    // ── Parser state ───────────────────────────────────────────────

    private final MetaLoader meta;

    /** Accumulated document-level attributes for the root &lt;document&gt; element. */
    private final Map<String, String> docAttrs = new LinkedHashMap<>();

    public SindocParser(MetaLoader meta) {
        this.meta = meta;
    }

    // ── Public API ─────────────────────────────────────────────────

    /**
     * Parse a .sindoc file from the given path.
     *
     * @param file       path to the .sindoc file
     * @param sourceHint a display name used as source-file attribute
     */
    public SindocDocument parse(Path file, String sourceHint) throws Exception {
        List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
        return parse(lines, sourceHint != null ? sourceHint : file.toString());
    }

    /**
     * Parse .sindoc content from a string.
     */
    public SindocDocument parseString(String content, String sourceHint) throws Exception {
        List<String> lines = Arrays.asList(content.split("\\r?\\n", -1));
        return parse(lines, sourceHint != null ? sourceHint : "<inline>");
    }

    // ── Core parsing ───────────────────────────────────────────────

    private SindocDocument parse(List<String> lines, String sourceHint) throws Exception {

        // Pass 1: collect header directives to populate root attributes
        extractHeaderAttrs(lines);
        docAttrs.put("source-file", sourceHint);

        String rootTag = meta.directive("output-root-element", "document");
        SindocDocument doc = new SindocDocument(rootTag, docAttrs);

        // Pass 2: full structural parse
        Element headerEl = doc.appendToRoot("header", null, null);
        Element bodyEl   = doc.appendToRoot("body",   null, null);

        // Parsing automaton
        enum Zone { HEADER, BODY, SECTION }
        Zone zone = Zone.HEADER;
        Element currentSection = null;

        int lineNo = 0;
        int bodyLineNo = 0;

        for (String raw : lines) {
            lineNo++;
            String line = raw.stripTrailing();

            // ── SEPARATOR ──────────────────────────────────────────
            if (P_SEPARATOR.matcher(line).matches()) {
                if (zone == Zone.HEADER || zone == Zone.BODY) {
                    // First separator: transition to SECTION zone; open pending section
                    zone = Zone.SECTION;
                    currentSection = openSection(doc, null); // type set when content seen
                } else if (currentSection != null) {
                    // Closing separator after section content
                    appendSeparator(doc, currentSection);
                    currentSection = null; // next content opens a fresh section
                } else {
                    // Opening separator for a new section
                    currentSection = openSection(doc, null);
                }
                continue;
            }

            // ── CLOSE ──────────────────────────────────────────────
            if (P_CLOSE.matcher(line).matches()) {
                if (currentSection == null) {
                    currentSection = openSection(doc, "close");
                } else {
                    currentSection.setAttribute("type", "close");
                }
                appendClose(doc, currentSection);
                zone = Zone.SECTION;
                currentSection = null;
                continue;
            }

            // ── TIMESTAMP ─────────────────────────────────────────
            Matcher ts = P_TIMESTAMP.matcher(line);
            if (ts.matches()) {
                if (currentSection == null) {
                    currentSection = openSection(doc, "timestamp");
                } else {
                    currentSection.setAttribute("type", "timestamp");
                }
                appendTimestamp(doc, currentSection, ts.group(1));
                zone = Zone.SECTION;
                continue;
            }

            // ── Header / body zone ─────────────────────────────────
            if (zone == Zone.HEADER) {
                Matcher dm = P_DIRECTIVE.matcher(line);
                if (dm.matches()) {
                    String keyword = dm.group(1);  // e.g. "#lang"
                    String rest    = dm.group(2).trim();
                    appendHeaderDirective(doc, headerEl, keyword, rest);
                    continue;
                }
                // Non-directive in header → transition to body
                zone = Zone.BODY;
                // fall through to BODY handling
            }

            if (zone == Zone.BODY) {
                Matcher am = P_ANNOTATION.matcher(line);
                if (am.matches()) {
                    String name = am.group(1).substring(1); // strip @
                    String rest = am.group(2).trim();
                    appendAnnotation(doc, bodyEl, name, rest);
                    continue;
                }
                Matcher dm = P_DIRECTIVE.matcher(line);
                if (dm.matches()) {
                    String keyword = dm.group(1);
                    String rest    = dm.group(2).trim();
                    appendBodyDirective(doc, bodyEl, keyword, rest);
                    continue;
                }
                bodyLineNo++;
                appendProseLine(doc, bodyEl, bodyLineNo, line);
                continue;
            }

            // ── Inside a section: treat as prose ──────────────────
            if (zone == Zone.SECTION && !line.isEmpty()) {
                if (currentSection == null) {
                    currentSection = openSection(doc, "prose");
                }
                bodyLineNo++;
                Map<String, String> attrs = new LinkedHashMap<>();
                attrs.put("n", String.valueOf(bodyLineNo));
                decorateScriptAttrs(line, attrs);
                doc.appendChild(currentSection, "line", attrs, line);
            }
        }

        return doc;
    }

    // ── Element builders ──────────────────────────────────────────

    private void extractHeaderAttrs(List<String> lines) {
        for (String raw : lines) {
            String line = raw.strip();
            if (line.startsWith("#lang ")) {
                docAttrs.put("lang", line.substring(6).trim());
            } else if (line.startsWith("#version ")) {
                docAttrs.put("version", line.substring(9).trim());
            } else if (line.startsWith("#namespace ")) {
                docAttrs.put("namespace", line.substring(11).trim());
            } else if (!line.isEmpty() && !line.startsWith("#")) {
                break; // end of header
            }
        }
    }

    private Element openSection(SindocDocument doc, String type) {
        Map<String, String> attrs = new LinkedHashMap<>();
        if (type != null) attrs.put("type", type);
        return doc.openSection("section", attrs);
    }

    private void appendSeparator(SindocDocument doc, Element section) {
        MetaLoader.MetaRule rule = meta.findRule("separator");
        String tag = rule != null ? rule.xmlElement() : "separator";
        if (section != null) {
            doc.appendChild(section, tag, null, null);
        }
    }

    private void appendTimestamp(SindocDocument doc, Element section, String value) {
        MetaLoader.MetaRule rule = meta.findRule("timestamp");
        String tag    = rule != null ? rule.xmlElement() : "timestamp";
        String format = rule != null ? rule.props.getOrDefault("content", "iso8601") : "iso8601";
        Map<String, String> attrs = new LinkedHashMap<>();
        attrs.put("value",  value != null ? value : "");
        attrs.put("format", format);
        if (section != null) {
            doc.appendChild(section, tag, attrs, null);
        }
    }

    private void appendClose(SindocDocument doc, Element section) {
        MetaLoader.MetaRule rule = meta.findRule("close");
        String tag = rule != null ? rule.xmlElement() : "close";
        if (section != null) {
            doc.appendChild(section, tag, null, null);
        }
    }

    private void appendHeaderDirective(SindocDocument doc, Element header,
                                       String keyword, String value) {
        // #lang → <lang name="racket"/>
        // #version → <version value="1.0"/>
        // #namespace → <namespace uri="..."/>
        // #anything → <directive name="anything">value</directive>
        String bare = keyword.substring(1); // strip #
        MetaLoader.MetaRule rule = meta.findRule(bare + "-declaration");
        if (rule == null) rule = meta.findRule("directive");

        String tag = rule != null ? rule.xmlElement() : "directive";
        Map<String, String> attrs = new LinkedHashMap<>();
        String attrKey = (rule != null)
            ? rule.props.getOrDefault("xml-attribute", "name")
            : "name";
        // xml-attribute may be space-separated list; use first for the value
        String firstAttr = attrKey.split(" ")[0];
        attrs.put(firstAttr, value.isEmpty() ? bare : value);
        if (rule == null || !rule.props.containsKey("xml-attribute") ||
                rule.props.get("xml-attribute").contains("name")) {
            // "directive" rule: put keyword name as attribute
            if (!attrs.containsKey("name")) attrs.put("name", bare);
        }
        doc.appendChild(header, tag, attrs, null);
    }

    private void appendBodyDirective(SindocDocument doc, Element body,
                                     String keyword, String value) {
        String bare = keyword.substring(1);
        Map<String, String> attrs = new LinkedHashMap<>();
        attrs.put("name", bare);
        doc.appendChild(body, "directive", attrs, value.isEmpty() ? null : value);
    }

    private void appendAnnotation(SindocDocument doc, Element body,
                                  String name, String rest) {
        MetaLoader.MetaRule rule = meta.findRule("annotation");
        String tag = rule != null ? rule.xmlElement() : "annotation";
        Map<String, String> attrs = new LinkedHashMap<>();
        attrs.put("name", name);
        doc.appendChild(body, tag, attrs, rest.isEmpty() ? null : rest);
    }

    private void appendProseLine(SindocDocument doc, Element parent,
                                 int lineNo, String text) {
        MetaLoader.MetaRule rule = meta.findRule("prose-line");
        String tag = rule != null ? rule.xmlElement() : "line";
        Map<String, String> attrs = new LinkedHashMap<>();
        attrs.put("n", String.valueOf(lineNo));
        decorateScriptAttrs(text, attrs);
        doc.appendChild(parent, tag, attrs, text.isEmpty() ? null : text);
    }

    /**
     * Detect Arabic or Latin-a-x character range and add a script attribute,
     * as defined by the char-range-arabic / char-range-latin rules.
     */
    private void decorateScriptAttrs(String text, Map<String, String> attrs) {
        if (P_ARABIC.matcher(text).find()) {
            attrs.put("script", "arabic");
        } else if (P_LATIN_AX.matcher(text).find()) {
            attrs.put("script", "latin");
        }
    }
}
