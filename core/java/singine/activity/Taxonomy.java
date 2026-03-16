package singine.activity;

import java.util.Map;

/**
 * Taxonomy — classification node in the singine activity hierarchy.
 *
 * The taxonomy is the strict classification structure that governs
 * every Activity in the platform.  Each node carries a domain,
 * category, and subcategory so that activities can be grouped,
 * filtered, and compared across systems (Collibra, Logseq, SPARQL).
 *
 * Taxonomy nodes are leaf-serialisable to XML, EDN, and SPARQL
 * fragments via the {@link #toXml()} and {@link #toEdn()} methods.
 *
 * Canonical domain values (non-exhaustive):
 *   emacs-orgmode-logseq, elia-electricity, web-publishing,
 *   data-governance, singine-core
 */
public interface Taxonomy {

    // ── Identity ──────────────────────────────────────────────────

    /**
     * Stable identifier for the taxonomy node.
     *
     * @return stable identifier matching the EDN {@code :taxonomy/id} key
     */
    String getId();

    /**
     * Human-readable taxonomy label in the default locale.
     *
     * @return default English label
     */
    String getName();

    // ── Classification ────────────────────────────────────────────

    /**
     * Top-level domain grouping for this taxonomy node.
     *
     * @return domain identifier, e.g. {@code "emacs-orgmode-logseq"}
     */
    String getDomain();

    /**
     * Category within the domain.
     *
     * @return category identifier, e.g. {@code "integration"}
     */
    String getCategory();

    /**
     * Subcategory, e.g. {@code "api-exposure"}.
     * May be {@code null} when not applicable.
     *
     * @return optional subcategory identifier
     */
    String getSubcategory();

    // ── Multilingual labels ───────────────────────────────────────

    /**
     * Multilingual label map.
     * Keys are BCP 47 language tags ({@code "en"}, {@code "fr"}, {@code "nl"}).
     * At minimum the {@code "en"} key must be present.
     *
     * @return multilingual labels for publication surfaces
     */
    Map<String, String> getLabels();

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise to an XML fragment compatible with the singine
     * domain model and the Elia electricity platform schema.
     *
     * <pre>{@code
     * <taxonomy id="..." domain="..." category="..." subcategory="...">
     *   <label lang="en">...</label>
     * </taxonomy>
     * }</pre>
     *
     * @return XML fragment describing this taxonomy node
     */
    String toXml();

    /**
     * Serialise to an EDN map compatible with Clojure / Logseq queries.
     *
     * <pre>{@code
     * {:taxonomy/id "..."
     *  :taxonomy/domain "..."
     *  :taxonomy/category "..."
     *  :taxonomy/labels {:en "..."}}
     * }</pre>
     *
     * @return EDN map describing this taxonomy node
     */
    String toEdn();
}
