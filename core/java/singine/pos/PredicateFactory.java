package singine.pos;

import java.util.Map;
import java.util.function.Predicate;

/**
 * PredicateFactory — generates SingingPredicate instances for singine POS Category C.
 *
 * Each predicate is "poetified" by carrying a {@code #lang singine} header
 * as a String field, so it can be serialised back as a governed lambda
 * in the .sindoc document format.
 *
 * Factory method:
 *   PredicateFactory.make(String name, String condition) -> SingingPredicate
 *
 * Credit lineage: factory pattern in the Sun/Oracle tradition,
 * poetified via #lang singine (Racket/XML-aligned Lisp variant).
 */
public class PredicateFactory {

    /** A Predicate<Map> that also carries a #lang singine poetified header. */
    public static final class SingingPredicate implements Predicate<Map> {
        private final String name;
        private final String condition;
        private final Predicate<Map> impl;

        SingingPredicate(String name, String condition, Predicate<Map> impl) {
            this.name      = name;
            this.condition = condition;
            this.impl      = impl;
        }

        /** Test the predicate against a subject map. */
        @Override
        public boolean test(Map subject) {
            return impl.test(subject);
        }

        /**
         * Returns the #lang singine poetified header for this predicate.
         * The header is a valid .sindoc preamble — parseable by SindocParser.
         */
        public String header() {
            return "#lang singine\n#predicate " + name + "\n;; " + condition;
        }

        public String name()      { return name; }
        public String condition() { return condition; }

        @Override
        public String toString() {
            return "SingingPredicate{name='" + name + "', condition='" + condition + "'}";
        }
    }

    /**
     * Factory method: create a named predicate from a condition string.
     *
     * Recognised conditions:
     *   "has-opcode"    subject map must contain key "opcode"
     *   "is-agent"      subject map must have "type" = "conscious-agent"
     *   "is-governed"   subject map must have "governed" = true (Boolean)
     *   "has-mime"      subject map must contain key "mime-type"
     *   "is-material"   subject map must contain key "material-cat"
     *   "is-signed"     subject map must have "contract-signed" = true
     *   default         always-true (open-world assumption)
     *
     * @param name      logical name for the predicate (used in #predicate header)
     * @param condition one of the recognised condition strings
     * @return          a SingingPredicate ready for use as a Clojure Predicate<Map>
     */
    public static SingingPredicate make(String name, String condition) {
        Predicate<Map> impl;
        switch (condition) {
            case "has-opcode":
                impl = m -> m.containsKey("opcode");
                break;
            case "is-agent":
                impl = m -> "conscious-agent".equals(m.get("type"));
                break;
            case "is-governed":
                impl = m -> Boolean.TRUE.equals(m.get("governed"));
                break;
            case "has-mime":
                impl = m -> m.containsKey("mime-type");
                break;
            case "is-material":
                impl = m -> m.containsKey("material-cat");
                break;
            case "is-signed":
                impl = m -> Boolean.TRUE.equals(m.get("contract-signed"));
                break;
            default:
                impl = m -> true;
        }
        return new SingingPredicate(name, condition, impl);
    }
}
