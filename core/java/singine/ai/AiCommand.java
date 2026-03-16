package singine.ai;

import java.time.Instant;
import java.util.Map;

/**
 * AiCommand — a single recorded command within an {@link AiSession}.
 *
 * Every interaction sent to an AI provider (prompt, API call, tool use)
 * is captured as an AiCommand so the full session history is auditable.
 *
 * PROV-O alignment
 * ────────────────
 * An AiCommand is a {@code prov:Activity}:
 *   - {@code prov:startedAtTime} = {@link #getExecutedAt()}
 *   - {@code prov:wasAssociatedWith} = the {@link AiSession} agent
 *   - {@code prov:used} = the input resource
 *   - {@code prov:generated} = the output resource
 *
 * Storage
 * ───────
 * Commands are appended to the session's EDN log:
 *   singine/ai/sessions/{session-id}/commands.edn
 * and optionally to {@code ~/.singine/decisions/} in the existing
 * decision format for backward compatibility.
 */
public interface AiCommand {

    // ── Identity ──────────────────────────────────────────────────

    /** Stable identifier — UUID form. */
    String getId();

    /** The session this command belongs to. */
    String getSessionId();

    // ── Command body ──────────────────────────────────────────────

    /**
     * The command string as issued.
     * For CLI invocations: the full command line.
     * For API calls: the operation name (e.g. {@code "chat.completions"}).
     * For file operations: the action + path (e.g. {@code "write singine/activity/Activity.java"}).
     */
    String getCommand();

    /**
     * Input context for this command.
     * Keys are EDN-namespaced strings.
     */
    Map<String, Object> getInput();

    /**
     * Output / result of the command.
     * May be {@code null} if the command is still executing.
     */
    Map<String, Object> getOutput();

    // ── Temporal + status ─────────────────────────────────────────

    /** When the command was executed. */
    Instant getExecutedAt();

    /**
     * Status using the activity status model.
     * Reuses {@link singine.activity.ActivityStatus} for consistency.
     */
    singine.activity.ActivityStatus getStatus();

    // ── Permissions ───────────────────────────────────────────────

    /**
     * Permissions required by this command.
     * These are checked against the session's granted permissions and
     * any active {@link AiMandate} before execution.
     */
    java.util.List<String> getRequiredPermissions();

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise to EDN for appending to the session's commands log.
     *
     * <pre>{@code
     * {:command/id "..."
     *  :command/session-id "..."
     *  :command/command "write singine/activity/Activity.java"
     *  :command/executed-at "2026-03-15T00:00:00Z"
     *  :command/status :COMPLETED}
     * }</pre>
     */
    String toEdn();
}
