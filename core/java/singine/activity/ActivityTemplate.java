package singine.activity;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * ActivityTemplate — abstract base implementation of {@link Activity}.
 *
 * Provides default XML and EDN serialisation so that subclasses
 * (in Java, Groovy, or any JVM language) only need to supply
 * identity, taxonomy, and policy.
 *
 * Usage
 * ─────
 * Extend this class and implement the abstract identity and governance
 * methods.
 * {@link #instantiate(Map)} creates a {@link BaseAction} by default;
 * override it if you need a custom Action type.
 *
 * <pre>{@code
 * public class ConfigureEmacsActivity extends ActivityTemplate {
 *     public String getId()          { return "activity-emacs-logseq-01"; }
 *     public String getName()        { return "Configure Emacs Client for Logseq"; }
 *     public String getDescription() { return "Set up emacsclient ..."; }
 *     public Taxonomy getTaxonomy()  { return EmacsLogseqTaxonomy.INSTANCE; }
 *     public Policy getPolicy()      { return ApprovedPolicy.INSTANCE; }
 * }
 * }</pre>
 */
public abstract class ActivityTemplate implements Activity {

    /**
     * Protected constructor for subclass-based activity templates.
     */
    protected ActivityTemplate() {
    }

    // ── Abstract identity ─────────────────────────────────────────

    @Override public abstract String getId();
    @Override public abstract String getName();
    @Override public abstract String getDescription();
    @Override public abstract Taxonomy getTaxonomy();
    @Override public abstract Policy getPolicy();

    // ── Default context ───────────────────────────────────────────

    @Override
    public Map<String, Object> getDefaultContext() {
        return Collections.emptyMap();
    }

    // ── Instantiation ─────────────────────────────────────────────

    @Override
    public Action instantiate(Map<String, Object> overrides) {
        Map<String, Object> ctx = new LinkedHashMap<>(getDefaultContext());
        if (overrides != null) ctx.putAll(overrides);
        return new BaseAction(this, getPolicy(), ctx);
    }

    // ── XML serialisation ─────────────────────────────────────────

    @Override
    public String toXml() {
        StringBuilder sb = new StringBuilder();
        sb.append("<activity id=\"").append(esc(getId())).append("\">\n");
        sb.append("  <name>").append(esc(getName())).append("</name>\n");
        sb.append("  <description>").append(esc(getDescription())).append("</description>\n");
        if (getTaxonomy() != null) {
            sb.append("  <taxonomy ref=\"").append(esc(getTaxonomy().getId())).append("\"/>\n");
        }
        if (getPolicy() != null) {
            sb.append("  <policy ref=\"").append(esc(getPolicy().getId())).append("\"/>\n");
        }
        sb.append("</activity>");
        return sb.toString();
    }

    // ── EDN serialisation ─────────────────────────────────────────

    @Override
    public String toEdn() {
        StringBuilder sb = new StringBuilder();
        sb.append("{:activity/id \"").append(ednStr(getId())).append("\"\n");
        sb.append(" :activity/name \"").append(ednStr(getName())).append("\"\n");
        sb.append(" :activity/description \"").append(ednStr(getDescription())).append("\"\n");
        if (getTaxonomy() != null) {
            sb.append(" :activity/taxonomy-id \"").append(ednStr(getTaxonomy().getId())).append("\"\n");
        }
        if (getPolicy() != null) {
            sb.append(" :activity/policy-id \"").append(ednStr(getPolicy().getId())).append("\"\n");
        }
        sb.append(" :activity/context {}}");
        return sb.toString();
    }

    // ── Helpers ───────────────────────────────────────────────────

    /**
     * XML-escape a string value for generated fragments.
     *
     * @param s raw string value
     * @return XML-escaped value
     */
    protected static String esc(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;");
    }

    /**
     * EDN-escape a string value.
     *
     * @param s raw string value
     * @return EDN-escaped value with backslashes and quotes escaped
     */
    protected static String ednStr(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
