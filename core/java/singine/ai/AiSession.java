package singine.ai;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * AiSession — a governed, recorded interaction session with an AI provider.
 *
 * A session is the unit of governance: every command, permission grant,
 * and outcome is scoped to a session.  Sessions are serialised to the
 * git-managed directory:
 *   singine/ai/sessions/{session-id}/
 *     manifest.edn     — session metadata
 *     commands.edn     — ordered list of AiCommand records
 *     permissions.edn  — granted and denied permissions
 *     outcomes.edn     — produced outcomes with activity taxonomy refs
 *
 * Session lifecycle
 * ─────────────────
 * OPEN → (commands recorded) → CLOSED → (flushed to git)
 *
 * Mandate context
 * ───────────────
 * A session may operate under an {@link AiMandate} issued by a third
 * party (e.g. Collibra).  The mandate pre-authorises a set of
 * {@link AiPermission}s; any command exceeding the mandate scope is
 * denied unless the user explicitly grants an additional permission.
 *
 * Flush behaviour
 * ───────────────
 * On {@link #close()}, the session is flushed to its EDN files.
 * The caller is responsible for git-adding and committing those files.
 * The recommended command is:
 *
 * <pre>
 *   singine ai flush --session {id} --commit
 * </pre>
 */
public interface AiSession {

    // ── Identity ──────────────────────────────────────────────────

    /** Stable session identifier — UUID or slug form. */
    String getId();

    /** Provider this session is using. */
    AiProviderType getProviderType();

    /** Model or API version in use (e.g. {@code "claude-sonnet-4-6"}). */
    String getModelVersion();

    // ── Temporal ──────────────────────────────────────────────────

    /** When the session started. */
    Instant getStartedAt();

    /** When the session was closed.  {@code null} if still open. */
    Instant getEndedAt();

    // ── Governance ────────────────────────────────────────────────

    /** All permissions granted during this session. */
    List<AiPermission> getGrantedPermissions();

    /**
     * Active mandate for this session.
     * {@code null} if no mandate is in effect.
     */
    AiMandate getMandate();

    // ── Commands ──────────────────────────────────────────────────

    /** All commands recorded in order of execution. */
    List<AiCommand> getCommands();

    /**
     * Record a new command in this session.
     *
     * @param command  the command string
     * @param input    input context
     * @param required required permission actions
     * @return the recorded AiCommand
     * @throws SecurityException if a required permission is not granted
     */
    AiCommand record(String command, Map<String, Object> input,
                     List<String> required);

    /**
     * Grant a permission in this session.
     * The permission is appended to the in-memory list and will be
     * flushed to {@code permissions.edn} on {@link #close()}.
     */
    void grant(String action, String resource, String rationale);

    // ── Lifecycle ─────────────────────────────────────────────────

    /**
     * Close the session and flush all records to the session directory.
     * After closing, no further commands may be recorded.
     */
    void close();

    /** {@code true} if the session has been closed. */
    boolean isClosed();

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise the session manifest to EDN.
     *
     * <pre>{@code
     * {:session/id "..."
     *  :session/provider :CLAUDE
     *  :session/model "claude-sonnet-4-6"
     *  :session/started-at "2026-03-15T00:00:00Z"
     *  :session/ended-at "2026-03-15T01:00:00Z"
     *  :session/command-count 12
     *  :session/mandate-id nil}
     * }</pre>
     */
    String toEdn();

    /** Serialise to XML for Collibra catalog or ODRL policy export. */
    String toXml();
}
