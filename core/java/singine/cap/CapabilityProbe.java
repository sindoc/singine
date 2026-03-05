package singine.cap;

import org.apache.commons.lang3.StringUtils;
import org.apache.commons.lang3.SystemUtils;

import java.io.*;
import java.nio.file.*;
import java.util.*;

/**
 * CapabilityProbe — detect machine capabilities for singine-cli fast-boot.
 *
 * <p>On first run, singine detects what the current machine can do and
 * stores the result in ~/.singine/machine-profile.json. Every subsequent
 * command uses this profile to decide what to deploy and in what order.
 *
 * <p>Detects:
 * <ul>
 *   <li>OS type and architecture (macOS, Linux, Windows, iOS/iSH, Android/Termux)</li>
 *   <li>Java version (if JVM present)</li>
 *   <li>Clojure CLI version (if clojure present)</li>
 *   <li>Python version (python3 / python)</li>
 *   <li>Docker availability and running state</li>
 *   <li>Git version</li>
 *   <li>Package managers: brew, apt, apk (Alpine), dnf/yum</li>
 *   <li>LaTeX installation (pdflatex, lualatex, xelatex)</li>
 *   <li>SSH key presence (~/.ssh/id_rsa.pub or ~/.ssh/id_ed25519.pub)</li>
 *   <li>Singine workspace root (SINGINE_ROOT env or current dir)</li>
 * </ul>
 *
 * <p>Design: all methods are static, no external deps (JDK + Commons only).
 * Uses ProcessBuilder for subprocess checks; catches all exceptions and returns
 * "unavailable" on failure — never throws.
 *
 * <p>URN: urn:singine:cap:probe
 */
public class CapabilityProbe {

    private static final int PROBE_TIMEOUT_MS = 5000;

    // ── runCommand() ─────────────────────────────────────────────────────────

    /**
     * Run a command and return its stdout as a trimmed string.
     * Returns empty string on any error or timeout.
     */
    private static String runCommand(String... cmd) {
        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(true);
            Process proc = pb.start();
            boolean finished = proc.waitFor(PROBE_TIMEOUT_MS,
                    java.util.concurrent.TimeUnit.MILLISECONDS);
            if (!finished) {
                proc.destroyForcibly();
                return "";
            }
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(proc.getInputStream()))) {
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    if (sb.length() > 0) sb.append("\n");
                    sb.append(line);
                }
                return sb.toString().trim();
            }
        } catch (Exception e) {
            return "";
        }
    }

    /**
     * Run a command and return true if exit code is 0.
     */
    private static boolean commandAvailable(String... cmd) {
        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(true);
            Process proc = pb.start();
            boolean finished = proc.waitFor(PROBE_TIMEOUT_MS,
                    java.util.concurrent.TimeUnit.MILLISECONDS);
            if (!finished) { proc.destroyForcibly(); return false; }
            return proc.exitValue() == 0;
        } catch (Exception e) {
            return false;
        }
    }

    // ── detectJava() ─────────────────────────────────────────────────────────

    /**
     * Detect JVM version information.
     * @return Map with keys: available, version, vendor, home
     */
    public static Map<String, Object> detectJava() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("available", true); // We're running in a JVM right now
        result.put("version",   System.getProperty("java.version", "unknown"));
        result.put("vendor",    System.getProperty("java.vendor", "unknown"));
        result.put("home",      System.getProperty("java.home", "unknown"));
        result.put("spec",      System.getProperty("java.specification.version", "unknown"));
        return result;
    }

    // ── detectOs() ───────────────────────────────────────────────────────────

    /**
     * Detect OS and architecture.
     * Also identifies iOS/iSH, Android/Termux environments.
     * @return Map with keys: name, arch, version, family, ish, termux
     */
    public static Map<String, Object> detectOs() {
        Map<String, Object> result = new LinkedHashMap<>();
        String osName    = System.getProperty("os.name", "unknown");
        String osArch    = System.getProperty("os.arch", "unknown");
        String osVersion = System.getProperty("os.version", "unknown");

        result.put("name",    osName);
        result.put("arch",    osArch);
        result.put("version", osVersion);

        // Family detection
        String family;
        if (SystemUtils.IS_OS_MAC_OSX) {
            family = "macOS";
        } else if (SystemUtils.IS_OS_LINUX) {
            // Check for iSH (iOS/iPadOS Alpine Linux environment)
            boolean isIsh = Files.exists(Paths.get("/proc/ish")) ||
                    Files.exists(Paths.get("/etc/ish-release"));
            // Check for Termux (Android)
            boolean isTermux = System.getenv("TERMUX_VERSION") != null ||
                    Files.exists(Paths.get("/data/data/com.termux"));
            family = isIsh ? "iOS/iSH" : (isTermux ? "Android/Termux" : "Linux");
            result.put("ish",    isIsh);
            result.put("termux", isTermux);
        } else if (SystemUtils.IS_OS_WINDOWS) {
            family = "Windows";
        } else {
            family = "Unknown";
        }
        result.put("family", family);
        return result;
    }

    // ── detectGit() ──────────────────────────────────────────────────────────

    /**
     * Detect Git availability and version.
     * @return Map with keys: available, version, remote
     */
    public static Map<String, Object> detectGit() {
        Map<String, Object> result = new LinkedHashMap<>();
        String version = runCommand("git", "--version");
        boolean available = !version.isEmpty();
        result.put("available", available);
        result.put("version", available ? version : "unavailable");
        if (available) {
            // Try to detect the remote of the singine repo
            String remote = runCommand("git", "remote", "get-url", "origin");
            result.put("remote", StringUtils.defaultIfBlank(remote, "none"));
        }
        return result;
    }

    // ── detectPython() ───────────────────────────────────────────────────────

    /**
     * Detect Python version.
     * Tries python3 first, then python.
     * @return Map with keys: available, version, command
     */
    public static Map<String, Object> detectPython() {
        Map<String, Object> result = new LinkedHashMap<>();
        // Try python3 first
        String v3 = runCommand("python3", "--version");
        if (!v3.isEmpty()) {
            result.put("available", true);
            result.put("version",   v3);
            result.put("command",   "python3");
            return result;
        }
        // Fallback to python
        String v = runCommand("python", "--version");
        if (!v.isEmpty()) {
            result.put("available", true);
            result.put("version",   v);
            result.put("command",   "python");
            return result;
        }
        result.put("available", false);
        result.put("version",   "unavailable");
        result.put("command",   "none");
        return result;
    }

    // ── detectClojure() ──────────────────────────────────────────────────────

    /**
     * Detect Clojure CLI availability.
     * Checks standard PATH, then ~/.local/clojure/bin (non-Homebrew install).
     * @return Map with keys: available, version, path
     */
    public static Map<String, Object> detectClojure() {
        Map<String, Object> result = new LinkedHashMap<>();
        // Try standard PATH
        String v = runCommand("clojure", "--version");
        if (!v.isEmpty()) {
            result.put("available", true);
            result.put("version",   v);
            result.put("path",      "clojure");
            return result;
        }
        // Try ~/.local/clojure/bin (common non-Homebrew install on macOS)
        String localPath = System.getProperty("user.home") + "/.local/clojure/bin/clojure";
        if (Files.exists(Paths.get(localPath))) {
            String lv = runCommand(localPath, "--version");
            result.put("available", !lv.isEmpty());
            result.put("version",   StringUtils.defaultIfBlank(lv, "unknown"));
            result.put("path",      localPath);
        } else {
            result.put("available", false);
            result.put("version",   "unavailable");
            result.put("path",      "none");
        }
        return result;
    }

    // ── detectDocker() ───────────────────────────────────────────────────────

    /**
     * Detect Docker availability and whether the daemon is running.
     * @return Map with keys: available, version, running
     */
    public static Map<String, Object> detectDocker() {
        Map<String, Object> result = new LinkedHashMap<>();
        String version = runCommand("docker", "--version");
        boolean available = !version.isEmpty();
        result.put("available", available);
        result.put("version", available ? version : "unavailable");
        if (available) {
            // Check if daemon is running (docker info returns 0 on success)
            boolean running = commandAvailable("docker", "info");
            result.put("running", running);
        } else {
            result.put("running", false);
        }
        return result;
    }

    // ── detectPackageManagers() ───────────────────────────────────────────────

    /**
     * Detect available package managers.
     * @return Map with keys: brew, apt, apk, dnf, yum, npm
     */
    public static Map<String, Object> detectPackageManagers() {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("brew", commandAvailable("brew", "--version"));
        result.put("apt",  commandAvailable("apt",  "--version"));
        result.put("apk",  commandAvailable("apk",  "--version"));
        result.put("dnf",  commandAvailable("dnf",  "--version"));
        result.put("yum",  commandAvailable("yum",  "--version"));
        result.put("npm",  commandAvailable("npm",  "--version"));
        return result;
    }

    // ── detectLatex() ────────────────────────────────────────────────────────

    /**
     * Detect LaTeX installation.
     * Tries pdflatex, lualatex, xelatex, dvisvgm.
     * @return Map with keys: available, engine, version, dvisvgm
     */
    public static Map<String, Object> detectLatex() {
        Map<String, Object> result = new LinkedHashMap<>();
        String[] engines = {"pdflatex", "lualatex", "xelatex"};
        for (String eng : engines) {
            String v = runCommand(eng, "--version");
            if (!v.isEmpty()) {
                result.put("available", true);
                result.put("engine",    eng);
                result.put("version",   v.split("\n")[0]); // first line only
                result.put("dvisvgm",   commandAvailable("dvisvgm", "--version"));
                return result;
            }
        }
        result.put("available", false);
        result.put("engine",    "none");
        result.put("version",   "unavailable");
        result.put("dvisvgm",   false);
        return result;
    }

    // ── detectSsh() ──────────────────────────────────────────────────────────

    /**
     * Detect SSH key presence.
     * Looks for ~/.ssh/id_rsa.pub, ~/.ssh/id_ed25519.pub, ~/.ssh/id_ecdsa.pub.
     * @return Map with keys: available, pubkey-path, pubkey-type, agent-running
     */
    public static Map<String, Object> detectSsh() {
        Map<String, Object> result = new LinkedHashMap<>();
        String home = System.getProperty("user.home", "");
        String[] candidates = {
                home + "/.ssh/id_rsa.pub",
                home + "/.ssh/id_ed25519.pub",
                home + "/.ssh/id_ecdsa.pub"
        };
        for (String candidate : candidates) {
            if (Files.exists(Paths.get(candidate))) {
                result.put("available",   true);
                result.put("pubkey-path", candidate);
                // Detect key type from filename
                String type = candidate.contains("ed25519") ? "ed25519"
                        : candidate.contains("ecdsa") ? "ecdsa" : "rsa";
                result.put("pubkey-type", type);
                // Check if ssh-agent is running
                boolean agentRunning = StringUtils.isNotBlank(
                        System.getenv("SSH_AUTH_SOCK"));
                result.put("agent-running", agentRunning);
                return result;
            }
        }
        // No key found
        result.put("available",    false);
        result.put("pubkey-path",  "none");
        result.put("pubkey-type",  "none");
        result.put("agent-running", false);
        return result;
    }

    // ── detectSingineRoot() ───────────────────────────────────────────────────

    /**
     * Detect the singine workspace root.
     * Priority: SINGINE_ROOT env → parent directories containing CLAUDE.md.
     * @return Absolute path string, or current directory if not found
     */
    public static String detectSingineRoot() {
        String envRoot = System.getenv("SINGINE_ROOT");
        if (StringUtils.isNotBlank(envRoot) && Files.exists(Paths.get(envRoot))) {
            return envRoot;
        }
        // Walk up from current directory looking for CLAUDE.md
        try {
            Path current = Paths.get("").toAbsolutePath();
            while (current != null) {
                if (Files.exists(current.resolve("CLAUDE.md"))) {
                    return current.toString();
                }
                current = current.getParent();
            }
        } catch (Exception e) {
            // Fall through
        }
        return Paths.get("").toAbsolutePath().toString();
    }

    // ── deriveCapabilities() ─────────────────────────────────────────────────

    /**
     * Derive the list of singine capability keywords from the probe results.
     * Returns a list of strings: "mail", "broker", "kg", "sec", "render", etc.
     */
    public static List<String> deriveCapabilities(Map<String, Object> profile) {
        List<String> caps = new ArrayList<>();
        caps.add("mail");  // always available (Python CLI + dry-run)
        caps.add("cli");   // always available
        Map<?, ?> pyMap  = (Map<?, ?>) profile.get("python");
        Map<?, ?> jvmMap = (Map<?, ?>) profile.get("java");
        Map<?, ?> dkrMap = (Map<?, ?>) profile.get("docker");
        Map<?, ?> ltxMap = (Map<?, ?>) profile.get("latex");
        Map<?, ?> sshMap = (Map<?, ?>) profile.get("ssh");
        if (pyMap != null && Boolean.TRUE.equals(pyMap.get("available"))) {
            caps.add("python");
        }
        if (jvmMap != null && Boolean.TRUE.equals(jvmMap.get("available"))) {
            caps.add("java");
            caps.add("broker");  // Kafka/RabbitMQ via Camel needs JVM
            caps.add("kg");      // Knowledge graph needs Jena (JVM)
            caps.add("sec");     // Crypto needs JVM
        }
        if (dkrMap != null && Boolean.TRUE.equals(dkrMap.get("running"))) {
            caps.add("docker");
            caps.add("edge");    // singine-edge Docker service
        }
        if (ltxMap != null && Boolean.TRUE.equals(ltxMap.get("available"))) {
            caps.add("render");  // LaTeX→SVG pipeline
        }
        if (sshMap != null && Boolean.TRUE.equals(sshMap.get("available"))) {
            caps.add("ssh");
        }
        return caps;
    }

    // ── probeAll() ───────────────────────────────────────────────────────────

    /**
     * Run all probes and return the full machine profile as a Map.
     * This is the entry point for singine-cli fast-boot capability detection.
     * @return Map with keys: hostname, user, singine-root, java, os, git,
     *         python, clojure, docker, package-managers, latex, ssh,
     *         capabilities, deploy-order
     */
    public static Map<String, Object> probeAll() {
        Map<String, Object> profile = new LinkedHashMap<>();

        // Machine identity
        profile.put("hostname",     StringUtils.defaultIfBlank(
                runCommand("hostname", "-s"), "unknown"));
        profile.put("user",         System.getProperty("user.name", "unknown"));
        profile.put("singine-root", detectSingineRoot());
        profile.put("probed-at",    java.time.Instant.now().toString());

        // Component probes
        profile.put("java",            detectJava());
        profile.put("os",              detectOs());
        profile.put("git",             detectGit());
        profile.put("python",          detectPython());
        profile.put("clojure",         detectClojure());
        profile.put("docker",          detectDocker());
        profile.put("package-managers", detectPackageManagers());
        profile.put("latex",           detectLatex());
        profile.put("ssh",             detectSsh());

        // Derived capabilities and deploy order
        List<String> caps = deriveCapabilities(profile);
        profile.put("capabilities", caps);

        // Deploy order (always starts with mail, then broker if available, etc.)
        List<String> deployOrder = new ArrayList<>();
        deployOrder.add("mail");
        if (caps.contains("broker")) deployOrder.add("broker");
        if (caps.contains("kg"))     deployOrder.add("kg");
        if (caps.contains("render")) deployOrder.add("render");
        deployOrder.add("checkin");
        profile.put("deploy-order", deployOrder);

        return profile;
    }
}
