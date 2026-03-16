package singine.activity;

import java.time.Instant;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicReference;

/**
 * BaseAction — default {@link Action} implementation.
 *
 * Created by {@link ActivityTemplate#instantiate(Map)}.
 * Override {@link #run(Map)} to provide domain-specific execution logic.
 *
 * Thread safety: the status field uses an AtomicReference; the
 * input context map is copied at construction time and is immutable.
 */
public class BaseAction implements Action {

    // ── Fields ────────────────────────────────────────────────────

    private final String id;
    private final Activity template;
    private final Policy policy;
    private final Map<String, Object> input;
    private final AtomicReference<ActivityStatus> status;

    // ── Construction ──────────────────────────────────────────────

    /**
     * Create a concrete action instance from an activity template.
     *
     * @param template originating activity template
     * @param policy governing policy applied at execution time
     * @param input immutable action input context
     */
    public BaseAction(Activity template, Policy policy, Map<String, Object> input) {
        this.id       = UUID.randomUUID().toString();
        this.template = template;
        this.policy   = policy;
        this.input    = Collections.unmodifiableMap(new LinkedHashMap<>(input));
        this.status   = new AtomicReference<>(ActivityStatus.PENDING);
    }

    // ── Identity ──────────────────────────────────────────────────

    @Override public String getId()            { return id; }
    @Override public Activity getTemplate()    { return template; }
    @Override public Policy getPolicy()        { return policy; }
    @Override public ActivityStatus getStatus(){ return status.get(); }
    @Override public Map<String, Object> getInput() { return input; }

    // ── Execution ─────────────────────────────────────────────────

    @Override
    public final Outcome execute() {
        if (!status.compareAndSet(ActivityStatus.PENDING, ActivityStatus.RUNNING)) {
            throw new IllegalStateException(
                "Action " + id + " is not PENDING (current: " + status.get() + ")");
        }
        try {
            Map<String, Object> policyCtx = policy.apply(input);
            Outcome outcome = run(policyCtx);
            status.set(ActivityStatus.COMPLETED);
            return outcome;
        } catch (Exception ex) {
            status.set(ActivityStatus.FAILED);
            return failureOutcome(ex);
        }
    }

    /**
     * Domain-specific execution logic.
     * Override this method in subclasses.
     *
     * @param context the policy-enriched context
     * @return the measured Outcome
     */
    protected Outcome run(Map<String, Object> context) {
        // Default: return a zero-cost success outcome.
        return new BaseOutcome(this, OutcomeType.SUCCESS, context, 0.0, 0.0, 0.0);
    }

    // ── Serialisation ─────────────────────────────────────────────

    @Override
    public String toXml() {
        return "<action id=\"" + id + "\" status=\"" + status.get() + "\">\n" +
               "  <template ref=\"" + (template != null ? esc(template.getId()) : "") + "\"/>\n" +
               "  <policy ref=\""   + (policy   != null ? esc(policy.getId())   : "") + "\"/>\n" +
               "</action>";
    }

    @Override
    public String toEdn() {
        return "{:action/id \"" + ednStr(id) + "\"\n" +
               " :action/status :" + status.get() + "\n" +
               " :action/template-id \"" + (template != null ? ednStr(template.getId()) : "") + "\"\n" +
               " :action/policy-id \""   + (policy   != null ? ednStr(policy.getId())   : "") + "\"}";
    }

    // ── Helpers ───────────────────────────────────────────────────

    private Outcome failureOutcome(Exception ex) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put(":error/message", ex.getMessage());
        m.put(":error/class",   ex.getClass().getName());
        m.put(":error/at",      Instant.now().toString());
        return new BaseOutcome(this, OutcomeType.FAILURE, m, 0.0, 0.0, 0.0);
    }

    private static String esc(String s) {
        if (s == null) return "";
        return s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\"","&quot;");
    }

    private static String ednStr(String s) {
        if (s == null) return "";
        return s.replace("\\","\\\\").replace("\"","\\\"");
    }
}
