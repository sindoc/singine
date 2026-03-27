package singine.activity.fs;

import singine.activity.Action;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * JVM entry point for Singine filesystem activities.
 *
 * <p>This class exists so the Python CLI and shell tooling can invoke the
 * concrete JVM implementations of {@code filesAboutTopic} and
 * {@code fileListTo} without embedding any non-JDK argument parsing
 * dependencies.
 */
public final class FilesystemActivityMain {

    private FilesystemActivityMain() {
    }

    /**
     * CLI entry point for JVM-backed filesystem activities.
     *
     * @param args command-line arguments
     * @throws Exception when argument parsing or activity execution fails
     */
    public static void main(String[] args) throws Exception {
        int exit = run(args);
        if (exit != 0) {
            System.exit(exit);
        }
    }

    static int run(String[] args) throws Exception {
        if (args.length < 2) {
            usage();
            return 2;
        }

        String command = args[0];
        String activity = args[1];
        if ("find".equals(command) && "filesAboutTopic".equals(activity)) {
            return runFind(args);
        }
        if ("mv".equals(command) && "fileListTo".equals(activity)) {
            return runMove(args);
        }

        usage();
        return 2;
    }

    private static int runFind(String[] args) {
        if (args.length < 3) {
            usage();
            return 2;
        }

        String topic = args[2];
        String rootDir = ".";
        int maxDepth = 3;
        String pathType = "any";
        boolean nullDelimited = false;
        boolean json = false;

        for (int i = 3; i < args.length; i++) {
            String arg = args[i];
            switch (arg) {
                case "--root-dir":
                    rootDir = requireValue(args, ++i, arg);
                    break;
                case "--max-depth":
                    maxDepth = Integer.parseInt(requireValue(args, ++i, arg));
                    break;
                case "--type":
                    pathType = requireValue(args, ++i, arg);
                    break;
                case "-0":
                case "--null":
                    nullDelimited = true;
                    break;
                case "--json":
                    json = true;
                    break;
                default:
                    throw new IllegalArgumentException("Unknown option: " + arg);
            }
        }

        Map<String, Object> ctx = new LinkedHashMap<>();
        ctx.put(":fs/topic", topic);
        ctx.put(":fs/root-dir", rootDir);
        ctx.put(":fs/max-depth", maxDepth);
        ctx.put(":fs/path-type", pathType);

        Action action = FilesystemActivities.FilesAboutTopicActivity.INSTANCE.instantiate(ctx);
        action.execute();
        List<FilesystemActivities.MatchEntry> matches = FilesystemActivities.findMatches(
            topic,
            FilesystemActivities.resolveUserPath(rootDir),
            maxDepth,
            pathType
        );

        if (json) {
            System.out.print(findAsJson(topic, rootDir, maxDepth, pathType, matches));
            return 0;
        }
        if (nullDelimited) {
            for (FilesystemActivities.MatchEntry match : matches) {
                System.out.write(match.getPath().getBytes(StandardCharsets.UTF_8), 0, match.getPath().getBytes(StandardCharsets.UTF_8).length);
                System.out.write(0);
            }
            return 0;
        }
        for (FilesystemActivities.MatchEntry match : matches) {
            System.out.println(match.getPath());
        }
        return 0;
    }

    private static int runMove(String[] args) throws IOException {
        if (args.length < 3) {
            usage();
            return 2;
        }

        String destDir = args[2];
        boolean nullDelimited = false;
        boolean mkdir = false;
        boolean dryRun = false;
        boolean json = false;

        for (int i = 3; i < args.length; i++) {
            String arg = args[i];
            switch (arg) {
                case "-0":
                case "--null":
                    nullDelimited = true;
                    break;
                case "--mkdir":
                    mkdir = true;
                    break;
                case "--dry-run":
                    dryRun = true;
                    break;
                case "--json":
                    json = true;
                    break;
                default:
                    throw new IllegalArgumentException("Unknown option: " + arg);
            }
        }

        List<String> rawPaths = FilesystemActivities.readPathsFromStdin(nullDelimited);
        Map<String, Object> ctx = new LinkedHashMap<>();
        ctx.put(":fs/raw-paths", rawPaths);
        ctx.put(":fs/dest-dir", destDir);
        ctx.put(":fs/mkdir", mkdir);
        ctx.put(":fs/dry-run", dryRun);

        Action action = FilesystemActivities.FileListToActivity.INSTANCE.instantiate(ctx);
        action.execute();
        FilesystemActivities.MoveSummary summary = FilesystemActivities.movePaths(
            rawPaths,
            FilesystemActivities.resolveUserPath(destDir),
            mkdir,
            dryRun
        );

        if (json) {
            System.out.print(moveAsJson(summary));
            return summary.getErrors().isEmpty() ? 0 : 1;
        }

        for (FilesystemActivities.MoveEntry entry : summary.getMoved()) {
            System.out.println(entry.getStatus() + ": " + entry.getSource() + " -> " + entry.getTarget());
        }
        for (FilesystemActivities.MoveEntry entry : summary.getSkipped()) {
            System.err.println("skipped: " + entry.getSource() + " (" + entry.getReason() + ")");
        }
        for (FilesystemActivities.MoveEntry entry : summary.getErrors()) {
            System.err.println("error: " + entry.getSource() + " -> " + entry.getTarget()
                + " (" + entry.getReason() + ")");
        }
        System.out.println("activity=fileListTo moved=" + summary.getMoved().size()
            + " skipped=" + summary.getSkipped().size()
            + " errors=" + summary.getErrors().size());
        return summary.getErrors().isEmpty() ? 0 : 1;
    }

    private static String requireValue(String[] args, int index, String option) {
        if (index >= args.length) {
            throw new IllegalArgumentException("Missing value for " + option);
        }
        return args[index];
    }

    private static void usage() {
        System.err.println("Usage:");
        System.err.println("  java -cp core/classes singine.activity.fs.FilesystemActivityMain find filesAboutTopic TOPIC [--root-dir DIR] [--max-depth N] [--type any|file|dir] [--null|-0] [--json]");
        System.err.println("  java -cp core/classes singine.activity.fs.FilesystemActivityMain mv fileListTo DEST_DIR [--null|-0] [--mkdir] [--dry-run] [--json]");
    }

    private static String findAsJson(String topic, String rootDir, int maxDepth,
                                     String pathType, List<FilesystemActivities.MatchEntry> matches) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"ok\":true,");
        sb.append("\"activity\":\"filesAboutTopic\",");
        sb.append("\"topic\":\"").append(jsonEscape(topic)).append("\",");
        sb.append("\"root_dir\":\"").append(jsonEscape(FilesystemActivities.resolveUserPath(rootDir).toString())).append("\",");
        sb.append("\"max_depth\":").append(maxDepth).append(",");
        sb.append("\"path_type\":\"").append(jsonEscape(pathType)).append("\",");
        sb.append("\"count\":").append(matches.size()).append(",");
        sb.append("\"matches\":[");
        for (int i = 0; i < matches.size(); i++) {
            var match = matches.get(i);
            if (i > 0) {
                sb.append(",");
            }
            sb.append("{\"type\":\"").append(jsonEscape(match.getType()))
                .append("\",\"path\":\"").append(jsonEscape(match.getPath())).append("\"}");
        }
        sb.append("]}");
        return sb.toString();
    }

    private static String moveAsJson(FilesystemActivities.MoveSummary summary) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        sb.append("\"ok\":").append(summary.getErrors().isEmpty()).append(",");
        sb.append("\"activity\":\"fileListTo\",");
        sb.append("\"dest_dir\":\"").append(jsonEscape(summary.getDestination().toString())).append("\",");
        sb.append("\"dry_run\":").append(summary.isDryRun()).append(",");
        sb.append("\"moved_count\":").append(summary.getMoved().size()).append(",");
        sb.append("\"skipped_count\":").append(summary.getSkipped().size()).append(",");
        sb.append("\"error_count\":").append(summary.getErrors().size()).append(",");
        sb.append("\"moved\":").append(entriesAsJson(summary.getMoved())).append(",");
        sb.append("\"skipped\":").append(entriesAsJson(summary.getSkipped())).append(",");
        sb.append("\"errors\":").append(entriesAsJson(summary.getErrors()));
        sb.append("}");
        return sb.toString();
    }

    private static String entriesAsJson(List<FilesystemActivities.MoveEntry> entries) {
        List<String> parts = new ArrayList<>();
        for (FilesystemActivities.MoveEntry entry : entries) {
            parts.add("{\"status\":\"" + jsonEscape(entry.getStatus())
                + "\",\"source\":\"" + jsonEscape(entry.getSource())
                + "\",\"target\":\"" + jsonEscape(entry.getTarget())
                + "\",\"reason\":\"" + jsonEscape(entry.getReason()) + "\"}");
        }
        return "[" + String.join(",", parts) + "]";
    }

    private static String jsonEscape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
