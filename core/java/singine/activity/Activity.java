package singine.activity;

import java.util.Map;

/**
 * Activity — template for an action in the singine taxonomy.
 *
 * An Activity defines "what should be done": it carries a
 * {@link Taxonomy} classification, a governing {@link Policy},
 * and the context map that any {@link Action} instantiating it
 * will inherit.
 *
 * Activity is never executed directly; it is instantiated into
 * an {@link Action} via {@link #instantiate(Map)}.
 *
 * Taxonomy
 * ────────
 * Activities form a strict taxonomy with four levels:
 *
 *   domain → category → subcategory → activity
 *
 * This taxonomy is the canonical classification used by Collibra,
 * Logseq, SPARQL queries, and the XML domain model.
 *
 * Multi-language generation
 * ─────────────────────────
 * The Activity's EDN representation ({@link #toEdn()}) is the single
 * source of truth from which the following artefacts are generated:
 *
 *   • XML (domain model, API request/response schemas)
 *   • LaTeX (documentation)
 *   • SVG (diagrams and logos)
 *   • HTML (published pages via SilkPage)
 *   • GraphQL query templates
 *   • SPARQL query templates
 *   • Logseq Clojure queries
 *
 * Shell initialisation
 * ────────────────────
 * Every Activity carries a reference to its shell init files.
 * The runtime sources these before executing any Action:
 *
 * <pre>
 *   source ~/.singine/activity.sh
 *   source ~/.singine/activity.bash
 * </pre>
 *
 * See also: {@code singine decide} CLI command for governance decisions.
 */
public interface Activity {

    // ── Identity ──────────────────────────────────────────────────

    /** Stable identifier — matches the EDN :activity/id key. */
    String getId();

    /** Human-readable name (English). */
    String getName();

    /** One-paragraph description of the activity's purpose. */
    String getDescription();

    // ── Classification ────────────────────────────────────────────

    /** Taxonomy node classifying this activity. */
    Taxonomy getTaxonomy();

    // ── Governance ────────────────────────────────────────────────

    /** Policy that governs execution of actions from this template. */
    Policy getPolicy();

    // ── Context ───────────────────────────────────────────────────

    /**
     * Default context map for actions instantiated from this template.
     * Actions may override individual keys but not remove required ones.
     * Keys are EDN-compatible namespaced strings.
     */
    Map<String, Object> getDefaultContext();

    // ── Instantiation ─────────────────────────────────────────────

    /**
     * Create a new {@link Action} from this template, merging
     * {@code overrides} on top of {@link #getDefaultContext()}.
     *
     * @param overrides caller-supplied context overrides; may be empty
     * @return a new Action in {@code PENDING} status
     */
    Action instantiate(Map<String, Object> overrides);

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise to an XML fragment.
     *
     * <pre>{@code
     * <activity id="...">
     *   <name>...</name>
     *   <description>...</description>
     *   <taxonomy ref="..."/>
     *   <policy ref="..."/>
     * </activity>
     * }</pre>
     */
    String toXml();

    /**
     * Serialise to an EDN map — the canonical source for all
     * generated artefacts (XML, SPARQL, GraphQL, Logseq queries).
     *
     * <pre>{@code
     * {:activity/id "..."
     *  :activity/name "..."
     *  :activity/description "..."
     *  :activity/taxonomy-id "..."
     *  :activity/policy-id "..."
     *  :activity/context {}}
     * }</pre>
     */
    String toEdn();
}
