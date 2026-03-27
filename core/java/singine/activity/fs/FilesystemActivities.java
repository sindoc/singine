package singine.activity.fs;

import singine.activity.Activity;
import singine.activity.ActivityTemplate;
import singine.activity.Action;
import singine.activity.BaseAction;
import singine.activity.BaseOutcome;
import singine.activity.Outcome;
import singine.activity.OutcomeType;
import singine.activity.Policy;
import singine.activity.Taxonomy;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * JVM-backed filesystem activities for Singine.
 *
 * <p>This package provides concrete {@link Activity} implementations for the
 * two filesystem actions currently exposed by the shell CLI:
 *
 * <ul>
 *   <li>{@code filesAboutTopic}: search files and directories whose basename
 *   contains a topic fragment.</li>
 *   <li>{@code fileListTo}: move a stdin-provided list of filesystem paths into
 *   a destination directory.</li>
 * </ul>
 *
 * <p>The activities are intentionally implemented in pure JDK code so they can
 * be compiled and executed in Singine's JVM runtime without any additional
 * third-party dependencies.
 */
public final class FilesystemActivities {

    private FilesystemActivities() {
    }

    /**
     * Result row for filesystem discovery.
     */
    public static final class MatchEntry {
        private final String type;
        private final String path;

        /**
         * Create one filesystem discovery match.
         *
         * @param type logical type, typically {@code file} or {@code dir}
         * @param path absolute matched path
         */
        public MatchEntry(String type, String path) {
            this.type = type;
            this.path = path;
        }

        /**
         * Type of matched filesystem object.
         *
         * @return match type, usually {@code file} or {@code dir}
         */
        public String getType() {
            return type;
        }

        /**
         * Absolute matched path.
         *
         * @return matched path string
         */
        public String getPath() {
            return path;
        }
    }

    /**
     * Result row for filesystem move planning or execution.
     */
    public static final class MoveEntry {
        private final String status;
        private final String source;
        private final String target;
        private final String reason;

        /**
         * Create one move result row.
         *
         * @param status execution status such as {@code moved}, {@code planned}, or {@code skipped}
         * @param source source path
         * @param target destination path, when applicable
         * @param reason error or skip reason, when applicable
         */
        public MoveEntry(String status, String source, String target, String reason) {
            this.status = status;
            this.source = source;
            this.target = target;
            this.reason = reason;
        }

        /**
         * Status label for this move event.
         *
         * @return move status
         */
        public String getStatus() {
            return status;
        }

        /**
         * Source path for this move event.
         *
         * @return source path string
         */
        public String getSource() {
            return source;
        }

        /**
         * Target path for this move event.
         *
         * @return target path string
         */
        public String getTarget() {
            return target;
        }

        /**
         * Reason attached to this move event.
         *
         * @return reason string, possibly empty
         */
        public String getReason() {
            return reason;
        }
    }

    /**
     * Local filesystem search taxonomy.
     */
    public static final class FilesystemDiscoveryTaxonomy implements Taxonomy {
        /** Singleton taxonomy instance for filesystem topic discovery. */
        public static final FilesystemDiscoveryTaxonomy INSTANCE = new FilesystemDiscoveryTaxonomy();

        private FilesystemDiscoveryTaxonomy() {
        }

        @Override
        public String getId() {
            return "taxonomy-singine-filesystem-discovery";
        }

        @Override
        public String getName() {
            return "Filesystem Topic Discovery";
        }

        @Override
        public String getDomain() {
            return "singine-core";
        }

        @Override
        public String getCategory() {
            return "filesystem-operations";
        }

        @Override
        public String getSubcategory() {
            return "topic-discovery";
        }

        @Override
        public Map<String, String> getLabels() {
            Map<String, String> labels = new LinkedHashMap<>();
            labels.put("en", "Filesystem Topic Discovery");
            labels.put("fr", "Découverte de sujets dans le système de fichiers");
            labels.put("nl", "Bestandssysteem onderwerp-ontdekking");
            return labels;
        }

        @Override
        public String toXml() {
            return "<taxonomy id=\"" + getId() + "\" domain=\"" + getDomain()
                + "\" category=\"" + getCategory() + "\" subcategory=\"" + getSubcategory()
                + "\"><label lang=\"en\">" + getName() + "</label></taxonomy>";
        }

        @Override
        public String toEdn() {
            return "{:taxonomy/id \"" + getId()
                + "\" :taxonomy/domain \"" + getDomain()
                + "\" :taxonomy/category \"" + getCategory()
                + "\" :taxonomy/subcategory \"" + getSubcategory()
                + "\" :taxonomy/labels {:en \"" + getName() + "\"}}";
        }
    }

    /**
     * Local filesystem mutation taxonomy.
     */
    public static final class FilesystemMutationTaxonomy implements Taxonomy {
        /** Singleton taxonomy instance for controlled filesystem moves. */
        public static final FilesystemMutationTaxonomy INSTANCE = new FilesystemMutationTaxonomy();

        private FilesystemMutationTaxonomy() {
        }

        @Override
        public String getId() {
            return "taxonomy-singine-filesystem-mutation";
        }

        @Override
        public String getName() {
            return "Filesystem Controlled Move";
        }

        @Override
        public String getDomain() {
            return "singine-core";
        }

        @Override
        public String getCategory() {
            return "filesystem-operations";
        }

        @Override
        public String getSubcategory() {
            return "controlled-move";
        }

        @Override
        public Map<String, String> getLabels() {
            Map<String, String> labels = new LinkedHashMap<>();
            labels.put("en", "Filesystem Controlled Move");
            labels.put("fr", "Déplacement contrôlé dans le système de fichiers");
            labels.put("nl", "Gecontroleerde bestandsverplaatsing");
            return labels;
        }

        @Override
        public String toXml() {
            return "<taxonomy id=\"" + getId() + "\" domain=\"" + getDomain()
                + "\" category=\"" + getCategory() + "\" subcategory=\"" + getSubcategory()
                + "\"><label lang=\"en\">" + getName() + "</label></taxonomy>";
        }

        @Override
        public String toEdn() {
            return "{:taxonomy/id \"" + getId()
                + "\" :taxonomy/domain \"" + getDomain()
                + "\" :taxonomy/category \"" + getCategory()
                + "\" :taxonomy/subcategory \"" + getSubcategory()
                + "\" :taxonomy/labels {:en \"" + getName() + "\"}}";
        }
    }

    /**
     * Shared local filesystem execution policy.
     */
    public static final class SecureFilesystemPolicy implements Policy {
        /** Singleton local policy instance used by JVM filesystem activities. */
        public static final SecureFilesystemPolicy INSTANCE = new SecureFilesystemPolicy();

        private SecureFilesystemPolicy() {
        }

        @Override
        public String getId() {
            return "policy-singine-filesystem-local-01";
        }

        @Override
        public String getName() {
            return "Local Filesystem Activity Policy";
        }

        @Override
        public String getDecision() {
            return "approved";
        }

        @Override
        public String getRationale() {
            return "Approved for local filesystem operations executed inside Singine's JVM control boundary.";
        }

        @Override
        public Map<String, Object> apply(Map<String, Object> context) {
            Map<String, Object> out = new LinkedHashMap<>(context);
            out.put(":policy/id", getId());
            out.put(":policy/decision", getDecision());
            out.put(":policy/applied-at", Instant.now().toString());
            out.put(":policy/runtime", "jvm");
            return out;
        }

        @Override
        public String toXml() {
            return "<policy id=\"" + getId() + "\" decision=\"" + getDecision()
                + "\"><name>" + getName() + "</name><rationale>" + getRationale()
                + "</rationale></policy>";
        }

        @Override
        public String toEdn() {
            return "{:policy/id \"" + getId()
                + "\" :policy/decision \"" + getDecision()
                + "\" :policy/rationale \"" + getRationale().replace("\"", "\\\"") + "\"}";
        }
    }

    /**
     * Activity template for filesystem topic search.
     */
    public static final class FilesAboutTopicActivity extends ActivityTemplate {
        /** Singleton activity template for {@code filesAboutTopic}. */
        public static final FilesAboutTopicActivity INSTANCE = new FilesAboutTopicActivity();

        private FilesAboutTopicActivity() {
        }

        @Override
        public String getId() {
            return "activity-filesystem-find-01";
        }

        @Override
        public String getName() {
            return "Find Files About Topic";
        }

        @Override
        public String getDescription() {
            return "Search the local filesystem for files and directories whose basenames contain a requested topic fragment.";
        }

        @Override
        public Taxonomy getTaxonomy() {
            return FilesystemDiscoveryTaxonomy.INSTANCE;
        }

        @Override
        public Policy getPolicy() {
            return SecureFilesystemPolicy.INSTANCE;
        }

        @Override
        public Map<String, Object> getDefaultContext() {
            Map<String, Object> ctx = new LinkedHashMap<>();
            ctx.put(":fs/root-dir", ".");
            ctx.put(":fs/max-depth", 3);
            ctx.put(":fs/path-type", "any");
            return ctx;
        }

        @Override
        public Action instantiate(Map<String, Object> overrides) {
            Map<String, Object> ctx = new LinkedHashMap<>(getDefaultContext());
            if (overrides != null) {
                ctx.putAll(overrides);
            }
            return new FilesAboutTopicAction(this, getPolicy(), ctx);
        }
    }

    /**
     * Activity template for controlled filesystem moves.
     */
    public static final class FileListToActivity extends ActivityTemplate {
        /** Singleton activity template for {@code fileListTo}. */
        public static final FileListToActivity INSTANCE = new FileListToActivity();

        private FileListToActivity() {
        }

        @Override
        public String getId() {
            return "activity-filesystem-move-01";
        }

        @Override
        public String getName() {
            return "Move File List To Directory";
        }

        @Override
        public String getDescription() {
            return "Move a stdin-provided list of filesystem paths into a destination directory under Singine JVM policy control.";
        }

        @Override
        public Taxonomy getTaxonomy() {
            return FilesystemMutationTaxonomy.INSTANCE;
        }

        @Override
        public Policy getPolicy() {
            return SecureFilesystemPolicy.INSTANCE;
        }

        @Override
        public Map<String, Object> getDefaultContext() {
            Map<String, Object> ctx = new LinkedHashMap<>();
            ctx.put(":fs/mkdir", Boolean.FALSE);
            ctx.put(":fs/dry-run", Boolean.FALSE);
            return ctx;
        }

        @Override
        public Action instantiate(Map<String, Object> overrides) {
            Map<String, Object> ctx = new LinkedHashMap<>(getDefaultContext());
            if (overrides != null) {
                ctx.putAll(overrides);
            }
            return new FileListToAction(this, getPolicy(), ctx);
        }
    }

    /**
     * Action implementation for {@code filesAboutTopic}.
     */
    public static final class FilesAboutTopicAction extends BaseAction {
        /**
         * Create a runnable action for topic-oriented filesystem discovery.
         *
         * @param template originating activity template
         * @param policy governing policy
         * @param input action input context
         */
        public FilesAboutTopicAction(Activity template, Policy policy, Map<String, Object> input) {
            super(template, policy, input);
        }

        @Override
        protected Outcome run(Map<String, Object> context) {
            String topic = stringValue(context.get(":fs/topic"), "");
            Path root = resolveUserPath(stringValue(context.get(":fs/root-dir"), "."));
            int maxDepth = intValue(context.get(":fs/max-depth"), 3);
            String pathType = stringValue(context.get(":fs/path-type"), "any");

            List<MatchEntry> matches = findMatches(topic, root, maxDepth, pathType);
            Map<String, Object> measurements = new LinkedHashMap<>(context);
            List<String> paths = new ArrayList<>();
            for (MatchEntry match : matches) {
                paths.add(match.getPath());
            }
            measurements.put(":fs/match-count", matches.size());
            measurements.put(":fs/matches", paths);
            measurements.put(":activity/runtime", "jvm");
            return new BaseOutcome(
                this,
                OutcomeType.SUCCESS,
                measurements,
                matches.size(),
                matches.isEmpty() ? 0.0 : 1.0,
                Math.max(0.1, matches.size() * 0.001)
            );
        }
    }

    /**
     * Action implementation for {@code fileListTo}.
     */
    public static final class FileListToAction extends BaseAction {
        /**
         * Create a runnable action for controlled file movement.
         *
         * @param template originating activity template
         * @param policy governing policy
         * @param input action input context
         */
        public FileListToAction(Activity template, Policy policy, Map<String, Object> input) {
            super(template, policy, input);
        }

        @Override
        protected Outcome run(Map<String, Object> context) {
            @SuppressWarnings("unchecked")
            List<String> rawPaths = context.containsKey(":fs/raw-paths")
                ? new ArrayList<>((List<String>) context.get(":fs/raw-paths"))
                : Collections.emptyList();
            Path dest = resolveUserPath(stringValue(context.get(":fs/dest-dir"), "."));
            boolean mkdir = boolValue(context.get(":fs/mkdir"));
            boolean dryRun = boolValue(context.get(":fs/dry-run"));

            MoveSummary summary = movePaths(rawPaths, dest, mkdir, dryRun);
            Map<String, Object> measurements = new LinkedHashMap<>(context);
            measurements.put(":fs/moved-count", summary.moved.size());
            measurements.put(":fs/skipped-count", summary.skipped.size());
            measurements.put(":fs/error-count", summary.errors.size());
            measurements.put(":activity/runtime", "jvm");
            return new BaseOutcome(
                this,
                summary.errors.isEmpty() ? OutcomeType.SUCCESS : OutcomeType.FAILURE,
                measurements,
                summary.moved.size(),
                summary.errors.isEmpty() ? 1.0 : 0.0,
                Math.max(0.1, rawPaths.size() * 0.001)
            );
        }
    }

    /**
     * Internal move summary used by the CLI bridge.
     */
    public static final class MoveSummary {
        private final Path destination;
        private final boolean dryRun;
        private final List<MoveEntry> moved;
        private final List<MoveEntry> skipped;
        private final List<MoveEntry> errors;

        /**
         * Create a move summary suitable for CLI and publication output.
         *
         * @param destination destination directory
         * @param dryRun whether the move was planned only
         * @param moved moved or planned entries
         * @param skipped skipped entries
         * @param errors failed entries
         */
        public MoveSummary(Path destination, boolean dryRun, List<MoveEntry> moved,
                           List<MoveEntry> skipped, List<MoveEntry> errors) {
            this.destination = destination;
            this.dryRun = dryRun;
            this.moved = moved;
            this.skipped = skipped;
            this.errors = errors;
        }

        /**
         * Destination directory associated with the move summary.
         *
         * @return destination path
         */
        public Path getDestination() {
            return destination;
        }

        /**
         * Whether the operation was a dry run.
         *
         * @return {@code true} when no files were mutated
         */
        public boolean isDryRun() {
            return dryRun;
        }

        /**
         * Successful or planned move entries.
         *
         * @return moved entry list
         */
        public List<MoveEntry> getMoved() {
            return moved;
        }

        /**
         * Skipped move entries.
         *
         * @return skipped entry list
         */
        public List<MoveEntry> getSkipped() {
            return skipped;
        }

        /**
         * Failed move entries.
         *
         * @return error entry list
         */
        public List<MoveEntry> getErrors() {
            return errors;
        }
    }

    /**
     * Search for files or directories whose basename contains the topic fragment.
     *
     * @param topic case-insensitive topic fragment to search for
     * @param root root directory to traverse
     * @param maxDepth maximum depth below the root
     * @param pathType one of {@code any}, {@code file}, or {@code dir}
     * @return ordered list of filesystem matches
     */
    public static List<MatchEntry> findMatches(String topic, Path root, int maxDepth, String pathType) {
        String topicNeedle = topic.toLowerCase(Locale.ROOT);
        List<MatchEntry> matches = new ArrayList<>();
        try (var stream = Files.walk(root, Math.max(0, maxDepth))) {
            stream.filter(path -> !path.equals(root)).forEach(path -> {
                String name = path.getFileName() != null ? path.getFileName().toString() : path.toString();
                if (!name.toLowerCase(Locale.ROOT).contains(topicNeedle)) {
                    return;
                }
                boolean isDir = Files.isDirectory(path);
                if ("file".equals(pathType) && isDir) {
                    return;
                }
                if ("dir".equals(pathType) && !isDir) {
                    return;
                }
                matches.add(new MatchEntry(isDir ? "dir" : "file", path.toAbsolutePath().normalize().toString()));
            });
        } catch (IOException ex) {
            throw new IllegalStateException("Filesystem search failed: " + ex.getMessage(), ex);
        }
        return matches;
    }

    /**
     * Move or plan the movement of a list of filesystem paths into a destination directory.
     *
     * @param rawPaths raw source paths, typically decoded from stdin
     * @param destination destination directory
     * @param mkdir whether to create the destination directory when missing
     * @param dryRun whether to plan only without mutating the filesystem
     * @return structured move summary
     */
    public static MoveSummary movePaths(List<String> rawPaths, Path destination,
                                        boolean mkdir, boolean dryRun) {
        if (mkdir) {
            try {
                Files.createDirectories(destination);
            } catch (IOException ex) {
                throw new IllegalStateException("Could not create destination directory: " + destination, ex);
            }
        }
        if (!Files.isDirectory(destination)) {
            throw new IllegalStateException("Destination is not a directory: " + destination);
        }

        List<MoveEntry> moved = new ArrayList<>();
        List<MoveEntry> skipped = new ArrayList<>();
        List<MoveEntry> errors = new ArrayList<>();

        for (String rawPath : rawPaths) {
            Path source = resolveUserPath(rawPath);
            if (!Files.exists(source)) {
                skipped.add(new MoveEntry("skipped", source.toString(), "", "missing"));
                continue;
            }

            Path target = destination.resolve(source.getFileName().toString());
            if (dryRun) {
                moved.add(new MoveEntry("planned", source.toString(), target.toString(), ""));
                continue;
            }

            try {
                Files.move(source, target);
                moved.add(new MoveEntry("moved", source.toString(), target.toString(), ""));
            } catch (IOException ex) {
                errors.add(new MoveEntry("error", source.toString(), target.toString(), ex.getMessage()));
            }
        }

        return new MoveSummary(destination, dryRun, moved, skipped, errors);
    }

    /**
     * Read filesystem paths from standard input.
     *
     * @param nullDelimited whether stdin is NUL-delimited rather than line-delimited
     * @return decoded list of path strings
     * @throws IOException when stdin cannot be read
     */
    public static List<String> readPathsFromStdin(boolean nullDelimited) throws IOException {
        if (nullDelimited) {
            byte[] bytes = readAllBytes(System.in);
            List<String> items = new ArrayList<>();
            int start = 0;
            for (int i = 0; i < bytes.length; i++) {
                if (bytes[i] == 0) {
                    if (i > start) {
                        items.add(new String(bytes, start, i - start, StandardCharsets.UTF_8));
                    }
                    start = i + 1;
                }
            }
            if (start < bytes.length) {
                items.add(new String(bytes, start, bytes.length - start, StandardCharsets.UTF_8));
            }
            return items;
        }

        List<String> items = new ArrayList<>();
        for (String line : new String(readAllBytes(System.in), StandardCharsets.UTF_8).split("\\R")) {
            if (!line.isEmpty()) {
                items.add(line);
            }
        }
        return items;
    }

    private static byte[] readAllBytes(InputStream input) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        byte[] chunk = new byte[4096];
        int read;
        while ((read = input.read(chunk)) != -1) {
            buffer.write(chunk, 0, read);
        }
        return buffer.toByteArray();
    }

    /**
     * Resolve a user-facing path into a normalized absolute path.
     *
     * <p>This expands {@code ~} and {@code ~/...}, preserves Office temporary
     * names such as {@code ~$foo.xlsx}, and leaves unknown user-home forms as
     * literal paths.
     *
     * @param rawPath user-facing path string
     * @return normalized absolute path
     */
    public static Path resolveUserPath(String rawPath) {
        if (rawPath == null || rawPath.isEmpty()) {
            return Paths.get(".").toAbsolutePath().normalize();
        }
        if (!rawPath.startsWith("~")) {
            return Paths.get(rawPath).toAbsolutePath().normalize();
        }
        String home = System.getProperty("user.home");
        if ("~".equals(rawPath)) {
            return Paths.get(home).toAbsolutePath().normalize();
        }
        if (rawPath.startsWith("~/")) {
            return Paths.get(home, rawPath.substring(2)).toAbsolutePath().normalize();
        }
        // Keep Office temporary files like "~$foo.xlsx" literal.
        if (!rawPath.contains("/")) {
            return Paths.get(rawPath).toAbsolutePath().normalize();
        }
        String rest = rawPath.substring(1);
        int slash = rest.indexOf('/');
        if (slash <= 0) {
            return Paths.get(rawPath).toAbsolutePath().normalize();
        }
        String user = rest.substring(0, slash);
        String suffix = rest.substring(slash + 1);
        if (user.equals(System.getProperty("user.name"))) {
            return Paths.get(home, suffix).toAbsolutePath().normalize();
        }
        return Paths.get(rawPath).toAbsolutePath().normalize();
    }

    private static String stringValue(Object value, String fallback) {
        return value == null ? fallback : value.toString();
    }

    private static int intValue(Object value, int fallback) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value == null) {
            return fallback;
        }
        return Integer.parseInt(value.toString());
    }

    private static boolean boolValue(Object value) {
        if (value instanceof Boolean bool) {
            return bool;
        }
        return value != null && Boolean.parseBoolean(value.toString());
    }
}
