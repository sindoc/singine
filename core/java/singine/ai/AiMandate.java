package singine.ai;

import java.time.Instant;
import java.util.List;

/**
 * AiMandate — a delegated authority issued by a third party.
 *
 * A Mandate extends singine's authorised scope by allowing a trusted
 * third party (e.g. Collibra) to grant permissions on behalf of the
 * user or organisation.
 *
 * Design intent
 * ─────────────
 * Mandates are the governance mechanism for cross-system trust:
 *
 *   Collibra → issues AiMandate → singine → acts within mandate scope
 *
 * The mandate is serialised to:
 *   singine/ai/mandates/{grantor}-{date}.edn
 * and git-committed so it is auditable.
 *
 * ODRL alignment
 * ──────────────
 * An AiMandate maps to an {@code odrl:Policy} of type {@code odrl:Agreement}
 * between the grantor ({@code odrl:assigner}) and grantee ({@code odrl:assignee}).
 *
 * Collibra usage
 * ──────────────
 * Collibra issues mandates when it has pre-approved a scope of actions for
 * the singine agent.  The mandate ID corresponds to a Collibra asset ID
 * of type "Governance Policy".
 */
public interface AiMandate {

    // ── Identity ──────────────────────────────────────────────────

    /** Stable URN identifier, e.g. {@code urn:singine:mandate:collibra:20260315}. */
    String getId();

    // ── Parties ───────────────────────────────────────────────────

    /**
     * Grantor — the party issuing the mandate.
     * Examples: {@code "collibra"}, {@code "user:skh"}, {@code "system"}.
     */
    String getGrantor();

    /**
     * Grantee — the party receiving the mandate.
     * Typically {@code "singine"} or a specific session ID.
     */
    String getGrantee();

    // ── Scope ─────────────────────────────────────────────────────

    /** The set of permissions this mandate grants. */
    List<AiPermission> getPermissions();

    /**
     * Optional Collibra asset ID linking this mandate to a
     * Governance Policy asset in the Collibra catalog.
     * {@code null} when no Collibra link exists.
     */
    String getCollibraAssetId();

    // ── Temporal bounds ───────────────────────────────────────────

    /** When the mandate was issued. */
    Instant getIssuedAt();

    /**
     * When the mandate expires.  {@code null} = no expiry.
     * Expired mandates must not be honoured.
     */
    Instant getExpiresAt();

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise to EDN for storage in
     * {@code singine/ai/mandates/{grantor}-{date}.edn}.
     *
     * <pre>{@code
     * {:mandate/id "urn:singine:mandate:collibra:20260315"
     *  :mandate/grantor "collibra"
     *  :mandate/grantee "singine"
     *  :mandate/collibra-asset-id ""
     *  :mandate/issued-at "2026-03-15T00:00:00Z"
     *  :mandate/expires-at nil
     *  :mandate/permissions [...]}
     * }</pre>
     */
    String toEdn();

    /** Serialise to ODRL XML for Collibra policy export. */
    String toXml();
}
