package singine.sindoc;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/**
 * MetaLoader — reads .sindoc grammar files from the .meta hierarchy.
 *
 * Resolution order (parent-first, child overrides):
 *   1. <workspace-root>/.meta/sindoc.sindoc   — root grammar
 *   2. <project-root>/.meta/parser.sindoc      — project overrides
 *
 * The loaded rules are returned as a list of {@link MetaRule} records,
 * which SindocParser uses to drive XML production.
 *
 * This class is pure Java; no Clojure dependencies.
 */
public class MetaLoader {

    /** A single grammar rule parsed from a .sindoc meta file. */
    public static class MetaRule {
        public final String kind;       // "rule", "override", "extend", "meta"
        public final String name;       // e.g. "timestamp", "separator"
        public final Map<String, String> props; // key → value pairs

        public MetaRule(String kind, String name, Map<String, String> props) {
            this.kind  = kind;
            this.name  = name;
            this.props = Collections.unmodifiableMap(new LinkedHashMap<>(props));
        }

        /** Return the xml-element name for this rule, defaulting to name. */
        public String xmlElement() {
            return props.getOrDefault("xml-element", name);
        }

        @Override
        public String toString() {
            return kind + ":" + name + props;
        }
    }

    /** @meta directives (non-rule configuration lines). */
    public static class MetaDirective {
        public final String key;
        public final String value;

        public MetaDirective(String key, String value) {
            this.key   = key;
            this.value = value;
        }
    }

    private final List<MetaRule>      rules;
    private final List<MetaDirective> directives;

    public MetaLoader(Path workspaceRoot, Path projectRoot) throws IOException {
        Map<String, MetaRule> ruleMap = new LinkedHashMap<>();
        List<MetaDirective>   dirs    = new ArrayList<>();

        // Load parent (workspace root) first
        Path rootMeta = workspaceRoot.resolve(".meta").resolve("sindoc.sindoc");
        if (Files.exists(rootMeta)) {
            parse(rootMeta, ruleMap, dirs);
        }

        // Load child (project root), overriding/extending parent
        Path projMeta = projectRoot.resolve(".meta").resolve("parser.sindoc");
        if (Files.exists(projMeta)) {
            parse(projMeta, ruleMap, dirs);
        }

        this.rules      = Collections.unmodifiableList(new ArrayList<>(ruleMap.values()));
        this.directives = Collections.unmodifiableList(dirs);
    }

    /** Constructor for a single meta file (used in tests). */
    public MetaLoader(Path singleMetaFile) throws IOException {
        Map<String, MetaRule> ruleMap = new LinkedHashMap<>();
        List<MetaDirective>   dirs    = new ArrayList<>();
        parse(singleMetaFile, ruleMap, dirs);
        this.rules      = Collections.unmodifiableList(new ArrayList<>(ruleMap.values()));
        this.directives = Collections.unmodifiableList(dirs);
    }

    public List<MetaRule>      getRules()      { return rules; }
    public List<MetaDirective> getDirectives() { return directives; }

    /** Find a rule by name, or null. */
    public MetaRule findRule(String name) {
        return rules.stream().filter(r -> r.name.equals(name)).findFirst().orElse(null);
    }

    /** Return the value of a @meta directive, or the default. */
    public String directive(String key, String defaultVal) {
        return directives.stream()
            .filter(d -> d.key.equals(key))
            .map(d -> d.value)
            .findFirst()
            .orElse(defaultVal);
    }

    // ── Internal parser ──────────────────────────────────────────────

    /**
     * Parse a single .sindoc meta file.
     *
     * Lines processed:
     *   @rule <name>          → start of a rule block
     *   @override <name>      → override parent rule
     *   @extend <name>        → extend parent rule
     *   @meta <key>: <value>  → top-level directive
     *   <key>: <value>        → property inside a current rule block
     *   #lang, #version, etc. → header directives (skipped in meta files)
     *   --, <timestamp/>, </> → structural (skipped in meta files)
     *   blank / prose         → ignored
     */
    private void parse(Path file, Map<String, MetaRule> ruleMap,
                       List<MetaDirective> dirs) throws IOException {

        List<String> lines = Files.readAllLines(file);
        String currentKind = null;
        String currentName = null;
        Map<String, String> currentProps = null;

        for (String raw : lines) {
            String line = raw.stripTrailing();

            if (line.isBlank() || line.startsWith("#") ||
                line.equals("--") || line.equals("<timestamp/>") ||
                line.equals("</>") || line.startsWith("This ") ||
                line.startsWith("A ") || line.startsWith("The ") ||
                line.startsWith("Each ") || line.startsWith("This is")) {
                // prose / structural in the meta file itself — flush if in a block
                if (currentName != null && line.isBlank()) {
                    flush(ruleMap, currentKind, currentName, currentProps);
                    currentKind = currentName = null;
                    currentProps = null;
                }
                continue;
            }

            // @meta key: value
            if (line.startsWith("@meta ")) {
                if (currentName != null) {
                    flush(ruleMap, currentKind, currentName, currentProps);
                    currentKind = currentName = null;
                    currentProps = null;
                }
                String rest = line.substring(6).trim();
                int colon = rest.indexOf(':');
                if (colon > 0) {
                    dirs.add(new MetaDirective(
                        rest.substring(0, colon).trim(),
                        rest.substring(colon + 1).trim()));
                }
                continue;
            }

            // @rule / @override / @extend <name>
            if (line.startsWith("@rule ") || line.startsWith("@override ") ||
                line.startsWith("@extend ")) {
                if (currentName != null) {
                    flush(ruleMap, currentKind, currentName, currentProps);
                }
                int sp = line.indexOf(' ');
                currentKind  = line.substring(1, sp);   // rule | override | extend
                currentName  = line.substring(sp + 1).trim();
                currentProps = new LinkedHashMap<>();
                // For extend, seed with parent props if present
                if ("extend".equals(currentKind) && ruleMap.containsKey(currentName)) {
                    currentProps.putAll(ruleMap.get(currentName).props);
                }
                continue;
            }

            // Inside a rule block: "  key: value" (indented)
            if (currentName != null && (line.startsWith("  ") || line.startsWith("\t"))) {
                String stripped = line.strip();
                int colon = stripped.indexOf(':');
                if (colon > 0) {
                    String k = stripped.substring(0, colon).trim();
                    String v = stripped.substring(colon + 1).trim();
                    // xml-attribute can appear multiple times; collect as space-separated
                    if (k.equals("xml-attribute") && currentProps.containsKey(k)) {
                        currentProps.put(k, currentProps.get(k) + " " + v);
                    } else {
                        currentProps.put(k, v);
                    }
                }
                continue;
            }

            // Unindented non-@ line while in a rule block → flush and treat as prose
            if (currentName != null) {
                flush(ruleMap, currentKind, currentName, currentProps);
                currentKind = currentName = null;
                currentProps = null;
            }
        }

        // Flush final rule
        if (currentName != null) {
            flush(ruleMap, currentKind, currentName, currentProps);
        }
    }

    private void flush(Map<String, MetaRule> ruleMap,
                       String kind, String name, Map<String, String> props) {
        ruleMap.put(name, new MetaRule(kind, name, props));
    }
}
