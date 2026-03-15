package singine.activity;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * BaseOutcome — default {@link Outcome} implementation.
 *
 * Carries the three ultimate-metric components and exposes the
 * derived {@link #getUsageCostBenefitScore()} score.
 *
 * Measurements map is immutable after construction.
 */
public class BaseOutcome implements Outcome {

    // ── Fields ────────────────────────────────────────────────────

    private final String id;
    private final Action action;
    private final OutcomeType type;
    private final Map<String, Object> measurements;
    private final double usageValue;
    private final double businessValue;
    private final double platformCost;

    // ── Construction ──────────────────────────────────────────────

    public BaseOutcome(Action action,
                       OutcomeType type,
                       Map<String, Object> measurements,
                       double usageValue,
                       double businessValue,
                       double platformCost) {
        this.id           = java.util.UUID.randomUUID().toString();
        this.action       = action;
        this.type         = type;
        this.measurements = Collections.unmodifiableMap(
                                new LinkedHashMap<>(measurements != null ? measurements
                                                                         : Collections.emptyMap()));
        this.usageValue    = usageValue;
        this.businessValue = businessValue;
        this.platformCost  = platformCost;
    }

    // ── Identity + provenance ─────────────────────────────────────

    @Override public String getId()                    { return id; }
    @Override public Action getAction()                { return action; }
    @Override public OutcomeType getType()             { return type; }
    @Override public Map<String, Object> getMeasurements() { return measurements; }

    // ── Ultimate metric ───────────────────────────────────────────

    @Override public double getUsageValue()    { return usageValue; }
    @Override public double getBusinessValue() { return businessValue; }
    @Override public double getPlatformCost()  { return platformCost; }

    // ── Serialisation ─────────────────────────────────────────────

    @Override
    public String toXml() {
        double score = getUsageCostBenefitScore();
        return "<outcome id=\"" + id + "\" type=\"" + type + "\">\n" +
               "  <ultimate-metric id=\"usage-cost-benefit-score\">\n" +
               "    <usage-value>"    + usageValue    + "</usage-value>\n" +
               "    <business-value>" + businessValue + "</business-value>\n" +
               "    <platform-cost>"  + platformCost  + "</platform-cost>\n" +
               "    <score>"          + score         + "</score>\n" +
               "  </ultimate-metric>\n" +
               "</outcome>";
    }

    @Override
    public String toEdn() {
        return "{:outcome/id \""             + ednStr(id) + "\"\n" +
               " :outcome/type :"            + type + "\n" +
               " :outcome/usage-value "      + usageValue    + "\n" +
               " :outcome/business-value "   + businessValue + "\n" +
               " :outcome/platform-cost "    + platformCost  + "\n" +
               " :outcome/score "            + getUsageCostBenefitScore() + "}";
    }

    // ── Helper ────────────────────────────────────────────────────

    private static String ednStr(String s) {
        if (s == null) return "";
        return s.replace("\\","\\\\").replace("\"","\\\"");
    }
}
