package singine.ai;

import java.time.Instant;

/**
 * AiPermission — a single permission grant or denial in the governance layer.
 *
 * Aligned with ODRL (Open Digital Rights Language):
 *   - {@code action}   maps to {@code odrl:action}
 *   - {@code resource} maps to {@code odrl:target}
 *   - {@code decision} maps to {@code odrl:permission} / {@code odrl:prohibition}
 *
 * Collibra alignment
 * ──────────────────
 * Permissions are flushed to the git-managed file:
 *   singine/ai/permissions/granted.edn
 * and referenced in each session manifest.
 *
 * Standard action values (non-exhaustive)
 * ────────────────────────────────────────
 *   read       — read a file, API response, or data asset
 *   write      — write or create a file or record
 *   execute    — run a command or shell script
 *   commit     — git commit to a repository
 *   push       — git push to a remote
 *   delegate   — forward a mandate to another agent
 *   api-call   — call an external API endpoint
 *   model-call — invoke an AI model (counted, rate-limited)
 */
public interface AiPermission {

    // ── Identity ──────────────────────────────────────────────────

    /** Stable identifier — URN form preferred. */
    String getId();

    // ── ODRL fields ───────────────────────────────────────────────

    /** Action: {@code read}, {@code write}, {@code commit}, etc. */
    String getAction();

    /** Resource: file path, URL, repository, or Collibra asset ID. */
    String getResource();

    /** Decision: {@code granted}, {@code denied}, {@code conditional}. */
    String getDecision();

    /** Human-readable rationale. Maps to {@code odrl:constraint}. */
    String getRationale();

    // ── Temporal bounds ───────────────────────────────────────────

    /** When the permission was recorded. */
    Instant getGrantedAt();

    /**
     * Expiry time.  {@code null} means no expiry.
     * Expired permissions must not be honoured.
     */
    Instant getExpiresAt();

    // ── Provenance ────────────────────────────────────────────────

    /** Session ID this permission belongs to. */
    String getSessionId();

    /** Provider that required this permission. */
    String getProviderId();

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise to EDN for appending to
     * {@code singine/ai/permissions/granted.edn}.
     *
     * <pre>{@code
     * {:permission/id "..."
     *  :permission/action "write"
     *  :permission/resource "/path/to/file"
     *  :permission/decision "granted"
     *  :permission/session-id "..."
     *  :permission/granted-at "2026-03-15T00:00:00Z"}
     * }</pre>
     */
    String toEdn();

    /** Serialise to XML for Collibra asset link or ODRL policy export. */
    String toXml();
}
