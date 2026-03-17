package singine.activity;

/**
 * ActivityStatus — lifecycle states of an {@link Action}.
 *
 * The state machine is linear; only forward transitions are valid:
 *
 *   PENDING → RUNNING → COMPLETED
 *                     ↘ FAILED
 *   PENDING → CANCELLED
 *
 * {@code DEFERRED} is a holding state used when the action cannot
 * start immediately but has not been cancelled.
 */
public enum ActivityStatus {

    /** Action is queued but not yet started. */
    PENDING,

    /** Action is currently executing. */
    RUNNING,

    /** Action finished successfully; {@link Outcome} is available. */
    COMPLETED,

    /** Action terminated with an error; {@link Outcome} carries the reason. */
    FAILED,

    /** Action was abandoned before completion. */
    CANCELLED,

    /**
     * Action is waiting on a dependency or external event.
     * Valid transition: DEFERRED → PENDING → RUNNING.
     */
    DEFERRED
}
