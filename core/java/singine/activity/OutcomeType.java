package singine.activity;

/**
 * OutcomeType — classification of an {@link Outcome}'s result quality.
 *
 * Combined with the {@link Outcome#getUsageCostBenefitScore()} formula,
 * this type tells consumers whether the action produced the expected
 * business value at the expected cost.
 */
public enum OutcomeType {

    /** All expected measurements were produced at acceptable cost. */
    SUCCESS,

    /** The action produced no usable output; cost was incurred. */
    FAILURE,

    /** Measurements were produced but below the expected threshold. */
    PARTIAL,

    /** The action was not executed; no cost was incurred. */
    SKIPPED,

    /**
     * Execution was pushed to a later cycle.
     * Differs from {@link ActivityStatus#DEFERRED}: an outcome exists
     * (it records that deferral itself as a decision).
     */
    DEFERRED
}
