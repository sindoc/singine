package singine.activity;

import java.util.Map;

/**
 * Policy — execution algorithm attached to an {@link Activity}.
 *
 * A Policy is the "how to execute" specification: it receives a
 * context map, applies its rules, and returns an enriched context
 * that the {@link Action} will use during execution.
 *
 * Design intent
 * ─────────────
 * Policies are stateless rule sets, not stateful workflows.
 * The same Policy may be applied to many Activity instances.
 * Policy identity ({@link #getId()}) is stable across all JVM languages.
 *
 * Governance alignment
 * ────────────────────
 * Each Policy carries a {@code decision} (approved / denied /
 * conditional) and a {@code rationale} that maps directly to
 * the singine governance decision model ({@code singine decide} CLI)
 * and to Collibra policy assets.
 *
 * SBVR mapping
 * ────────────
 * A Policy in SBVR terms is a Business Rule with an associated
 * enforcement level.  The {@code apply} method is the operative
 * part of the rule.
 */
public interface Policy {

    // ── Identity ──────────────────────────────────────────────────

    /** Stable identifier — matches the EDN :policy/id key. */
    String getId();

    /** Human-readable name. */
    String getName();

    // ── Governance ────────────────────────────────────────────────

    /**
     * Governance decision: {@code "approved"}, {@code "denied"},
     * or {@code "conditional"}.
     */
    String getDecision();

    /**
     * Human-readable rationale for the decision.
     * Required; maps to {@code singine decide --reason}.
     */
    String getRationale();

    // ── Execution ─────────────────────────────────────────────────

    /**
     * Apply the policy rules to {@code context} and return an
     * enriched context map.
     *
     * The returned map must contain at minimum:
     * <ul>
     *   <li>{@code :policy/id}     — this policy's id</li>
     *   <li>{@code :policy/decision} — the resolved decision</li>
     *   <li>{@code :policy/applied-at} — ISO-8601 timestamp</li>
     * </ul>
     *
     * @param context input context from the calling {@link Action}
     * @return enriched context; never {@code null}
     */
    Map<String, Object> apply(Map<String, Object> context);

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise to an XML fragment.
     *
     * <pre>{@code
     * <policy id="..." decision="...">
     *   <name>...</name>
     *   <rationale>...</rationale>
     * </policy>
     * }</pre>
     */
    String toXml();

    /**
     * Serialise to an EDN map.
     *
     * <pre>{@code
     * {:policy/id "..."
     *  :policy/decision "approved"
     *  :policy/rationale "..."}
     * }</pre>
     */
    String toEdn();
}
