package singine.activity;

import java.util.Map;

/**
 * Action — a concrete execution instance of an {@link Activity}.
 *
 * An Action is the runtime materialisation of an Activity template.
 * It follows a {@link Policy} (the execution algorithm) and produces
 * an {@link Outcome} (the measurement).
 *
 * Lifecycle
 * ─────────
 * PENDING → RUNNING → COMPLETED | FAILED | CANCELLED | DEFERRED
 *
 * Every Action is traceable back to:
 *   1. Its Activity template ({@link #getTemplate()})
 *   2. Its governing Policy ({@link #getPolicy()})
 *   3. Its produced Outcome ({@link #execute()})
 *
 * Shell sourcing
 * ──────────────
 * Before executing, the runtime must source the activity's shell
 * initialisation files.  The convention is:
 *
 * <pre>
 *   source ~/.singine/activity.sh
 *   source ~/.singine/activity.bash   # if bash is available
 * </pre>
 *
 * The action context map ({@link #getInput()}) is serialised to
 * environment variables prefixed with {@code SINGINE_} before
 * the shell files are sourced.
 *
 * Polyglot note
 * ─────────────
 * This interface is implemented identically on the JVM (Java, Groovy,
 * Clojure) and via subprocess/IPC adapters in Python, Node.js, Go,
 * and Rust.  All language bindings must produce the same XML/EDN
 * serialisation.
 */
public interface Action {

    // ── Identity ──────────────────────────────────────────────────

    /**
     * Stable identifier for this action instance.
     *
     * @return stable identifier matching the EDN {@code :action/id} key
     */
    String getId();

    // ── Provenance ────────────────────────────────────────────────

    /**
     * Activity template from which this action was instantiated.
     *
     * @return originating activity template
     */
    Activity getTemplate();

    /**
     * Policy that governed this action execution.
     *
     * @return governing policy
     */
    Policy getPolicy();

    // ── State ─────────────────────────────────────────────────────

    /**
     * Current lifecycle status of the action.
     *
     * @return action lifecycle status
     */
    ActivityStatus getStatus();

    /**
     * Input context provided to this action.
     * Keys are EDN-compatible namespaced strings.
     *
     * @return immutable execution input map
     */
    Map<String, Object> getInput();

    // ── Execution ─────────────────────────────────────────────────

    /**
     * Execute the action and return the measured {@link Outcome}.
     *
     * <ol>
     *   <li>Apply the Policy to the input context.</li>
     *   <li>Run the activity logic.</li>
     *   <li>Measure usage value, business value, and platform cost.</li>
     *   <li>Return an Outcome with all measurements populated.</li>
     * </ol>
     *
     * @return the outcome; never {@code null}
     * @throws IllegalStateException if status is not {@code PENDING}
     */
    Outcome execute();

    // ── Serialisation ─────────────────────────────────────────────

    /**
     * Serialise to an XML fragment.
     *
     * <pre>{@code
     * <action id="..." status="PENDING">
     *   <template ref="..."/>
     *   <policy ref="..."/>
     * </action>
     * }</pre>
     *
     * @return XML fragment describing this action
     */
    String toXml();

    /**
     * Serialise to an EDN map.
     *
     * <pre>{@code
     * {:action/id "..."
     *  :action/status :PENDING
     *  :action/template-id "..."
     *  :action/policy-id "..."}
     * }</pre>
     *
     * @return EDN map describing this action
     */
    String toEdn();
}
