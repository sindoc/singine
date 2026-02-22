package singine.db;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.UUID;

/**
 * IcebergDescriptor — writes an Iceberg-style JSON metadata descriptor for the
 * Singine SQLite-backed table catalogue.
 *
 * No external dependencies; JSON is hand-rolled with StringBuilder.
 * The descriptor is written to {@code <metaDir>/extension_checks.iceberg.json}.
 */
public class IcebergDescriptor {

    private final Path metaDir;

    /**
     * @param metaDir directory that will hold the descriptor file
     *                (created on first write if it does not exist)
     */
    public IcebergDescriptor(Path metaDir) {
        this.metaDir = metaDir;
    }

    /**
     * Builds the JSON descriptor and writes it to {@link #descriptorPath()}.
     * Parent directories are created if they do not already exist.
     *
     * @param dbPath  filesystem path to the SQLite database
     * @param version schema version tag (recorded in the filename's metadata
     *                context; currently embedded via {@code buildJson})
     * @return the path of the written file
     */
    public Path writeDescriptor(String dbPath, int version) throws IOException {
        String json = buildJson(dbPath, version, Instant.now().toString());
        Files.createDirectories(metaDir);
        Path out = descriptorPath();
        Files.writeString(out, json, StandardCharsets.UTF_8);
        return out;
    }

    /**
     * Returns the canonical path for the descriptor file.
     */
    public Path descriptorPath() {
        return metaDir.resolve("extension_checks.iceberg.json");
    }

    /**
     * Hand-builds the Iceberg JSON descriptor.
     * Package-visible so unit tests can call it directly.
     *
     * @param dbPath       filesystem path to the SQLite database
     * @param version      format version (written as {@code "format-version"})
     * @param timestampUtc ISO-8601 UTC timestamp for {@code "generated-at"}
     */
    String buildJson(String dbPath, int version, String timestampUtc) {
        StringBuilder sb = new StringBuilder();

        sb.append("{\n");
        sb.append("  \"format-version\": ").append(version).append(",\n");
        sb.append("  \"table-uuid\": \"").append(escape(UUID.randomUUID().toString())).append("\",\n");
        sb.append("  \"location\": \"sqlite://").append(escape(dbPath)).append("\",\n");
        sb.append("  \"last-updated-ms\": ").append(System.currentTimeMillis()).append(",\n");
        sb.append("  \"generated-at\": \"").append(escape(timestampUtc)).append("\",\n");
        sb.append("  \"schemas\": [\n");

        // schema-id 0: extension_probes
        sb.append("    {\n");
        sb.append("      \"schema-id\": 0,\n");
        sb.append("      \"type\": \"struct\",\n");
        sb.append("      \"name\": \"extension_probes\",\n");
        sb.append("      \"fields\": [\n");
        appendField(sb, 1, "probe_id",    false, "string", false);
        appendField(sb, 2, "probe_name",  false, "string", false);
        appendField(sb, 3, "command_tpl", false, "string", false);
        appendField(sb, 4, "dimension",   false, "string", false);
        appendField(sb, 5, "severity_map",false, "string", true);
        sb.append("      ]\n");
        sb.append("    },\n");

        // schema-id 1: extension_checks
        sb.append("    {\n");
        sb.append("      \"schema-id\": 1,\n");
        sb.append("      \"type\": \"struct\",\n");
        sb.append("      \"name\": \"extension_checks\",\n");
        sb.append("      \"fields\": [\n");
        appendField(sb, 1, "check_id",   false, "string", false);
        appendField(sb, 2, "extension",  false, "string", false);
        appendField(sb, 3, "checked_at", false, "string", false);
        appendField(sb, 4, "verdict",    false, "string", false);
        appendField(sb, 5, "soap_doc",   false, "string", true);
        sb.append("      ]\n");
        sb.append("    },\n");

        // schema-id 2: probe_results
        sb.append("    {\n");
        sb.append("      \"schema-id\": 2,\n");
        sb.append("      \"type\": \"struct\",\n");
        sb.append("      \"name\": \"probe_results\",\n");
        sb.append("      \"fields\": [\n");
        appendField(sb, 1, "result_id",   false, "string", false);
        appendField(sb, 2, "check_id",    false, "string", false);
        appendField(sb, 3, "probe_id",    false, "string", false);
        appendField(sb, 4, "command_run", false, "string", false);
        appendField(sb, 5, "stdout",      false, "string", false);
        appendField(sb, 6, "stderr",      false, "string", false);
        appendField(sb, 7, "exit_code",   false, "int",    false);
        appendField(sb, 8, "severity",    false, "string", false);
        appendField(sb, 9, "finding",     false, "string", true);
        sb.append("      ]\n");
        sb.append("    },\n");

        // schema-id 3: momentum_snapshots
        sb.append("    {\n");
        sb.append("      \"schema-id\": 3,\n");
        sb.append("      \"type\": \"struct\",\n");
        sb.append("      \"name\": \"momentum_snapshots\",\n");
        sb.append("      \"fields\": [\n");
        appendField(sb, 1, "snapshot_id", false, "string", false);
        appendField(sb, 2, "cell_path",   false, "string", false);
        appendField(sb, 3, "instant",     false, "string", false);
        appendField(sb, 4, "kernel_name", false, "string", false);
        appendField(sb, 5, "entropy",     false, "double", false);
        appendField(sb, 6, "mass",        false, "double", false);
        appendField(sb, 7, "velocity",    false, "double", false);
        appendField(sb, 8, "momentum",    false, "double", true);
        sb.append("      ]\n");
        sb.append("    }\n");

        sb.append("  ],\n");

        // properties
        sb.append("  \"properties\": {\n");
        sb.append("    \"table_type\": \"ICEBERG\",\n");
        sb.append("    \"engine\": \"sqlite\",\n");
        sb.append("    \"hiveql-compatible\": \"true\",\n");
        sb.append("    \"write.format.default\": \"orc\"\n");
        sb.append("  }\n");
        sb.append("}\n");

        return sb.toString();
    }

    /**
     * Appends a single field object to the JSON fields array.
     *
     * @param sb       target builder
     * @param id       field id
     * @param name     field name
     * @param required required flag
     * @param type     Iceberg type string
     * @param last     true if this is the last field in the array (no trailing comma)
     */
    private static void appendField(StringBuilder sb, int id, String name,
                                    boolean required, String type, boolean last) {
        sb.append("        {");
        sb.append("\"id\": ").append(id).append(", ");
        sb.append("\"name\": \"").append(escape(name)).append("\", ");
        sb.append("\"required\": ").append(required).append(", ");
        sb.append("\"type\": \"").append(escape(type)).append("\"");
        sb.append("}");
        if (!last) {
            sb.append(",");
        }
        sb.append("\n");
    }

    /**
     * Escapes a string value for embedding inside a JSON double-quoted string.
     * Replaces {@code \} with {@code \\}, {@code "} with {@code \"}, and
     * newlines with {@code \n}.
     */
    private static String escape(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '\\') {
                sb.append("\\\\");
            } else if (c == '"') {
                sb.append("\\\"");
            } else if (c == '\n') {
                sb.append("\\n");
            } else if (c == '\r') {
                sb.append("\\r");
            } else if (c == '\t') {
                sb.append("\\t");
            } else {
                sb.append(c);
            }
        }
        return sb.toString();
    }
}
