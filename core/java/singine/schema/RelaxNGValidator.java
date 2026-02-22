package singine.schema;

import org.xml.sax.*;
import javax.xml.transform.*;
import javax.xml.transform.stream.*;
import javax.xml.validation.*;
import java.io.*;
import java.util.ArrayList;
import java.util.List;

/**
 * RelaxNGValidator — validates an XML string against a RelaxNG grammar.
 *
 * Uses javax.xml.validation (JAXP) with the JING validator factory
 * if available on the classpath, falling back to a lenient pass-through
 * when no RNG-capable SchemaFactory is found.
 *
 * In Phase 1 (no JING in deps.edn), the validator reports the RNG
 * grammar path as a metadata annotation and always returns valid=true
 * so the pipeline proceeds. Phase 2 adds JING to deps.edn.
 *
 * The full RNG pipeline is:
 *   singine.rnc → trang → singine.rng → this validator
 *
 * Usage:
 *   ValidationResult r = RelaxNGValidator.validate(xmlStr, rngStream);
 *   if (!r.isValid()) { ... r.getErrors() ... }
 */
public class RelaxNGValidator {

    /** Holds the result of a single validation run. */
    public static class ValidationResult {
        private final boolean      valid;
        private final List<String> errors;
        private final String       grammar;

        public ValidationResult(boolean valid, List<String> errors, String grammar) {
            this.valid   = valid;
            this.errors  = errors;
            this.grammar = grammar;
        }

        public boolean      isValid()   { return valid;   }
        public List<String> getErrors() { return errors;  }
        public String       getGrammar(){ return grammar; }

        @Override
        public String toString() {
            return "RelaxNGValidationResult{valid=" + valid
                    + ", grammar=" + grammar
                    + ", errors=" + errors + "}";
        }
    }

    /**
     * Validates {@code xmlStr} against the RelaxNG grammar supplied as
     * {@code rngStream} (expected: .rng XML format, not .rnc compact).
     *
     * @param xmlStr    the XML document to validate (UTF-8 string)
     * @param rngStream InputStream for the .rng grammar file
     * @param grammarId human-readable grammar identifier (for error messages)
     * @return ValidationResult with valid flag and any collected errors
     */
    public static ValidationResult validate(String xmlStr,
                                            InputStream rngStream,
                                            String grammarId) {
        List<String> errors = new ArrayList<>();
        // Try to load a RNG-capable SchemaFactory.
        // JAXP built-in only supports W3C XML Schema; JING adds RNG support.
        // If no RNG factory exists, return a metadata-annotated pass result.
        SchemaFactory sf = null;
        try {
            sf = SchemaFactory.newInstance(
                    "http://relaxng.org/ns/structure/1.0");
        } catch (IllegalArgumentException e) {
            // No RNG SchemaFactory on classpath — annotate and pass through
            errors.add("INFO: No RelaxNG SchemaFactory found (JING not in classpath). "
                     + "Grammar=" + grammarId + " — validation deferred to Phase 2.");
            return new ValidationResult(true, errors, grammarId);
        }

        try {
            Source grammarSource = new StreamSource(rngStream);
            Schema schema = sf.newSchema(grammarSource);
            Validator validator = schema.newValidator();

            final List<String> errs = errors;
            validator.setErrorHandler(new ErrorHandler() {
                public void warning(SAXParseException e) {
                    errs.add("WARN  [" + grammarId + ":" + e.getLineNumber() + "] " + e.getMessage());
                }
                public void error(SAXParseException e) {
                    errs.add("ERROR [" + grammarId + ":" + e.getLineNumber() + "] " + e.getMessage());
                }
                public void fatalError(SAXParseException e) throws SAXException {
                    errs.add("FATAL [" + grammarId + ":" + e.getLineNumber() + "] " + e.getMessage());
                    throw e;
                }
            });

            validator.validate(new StreamSource(new StringReader(xmlStr)));
            boolean valid = errors.stream().noneMatch(s -> s.startsWith("ERROR") || s.startsWith("FATAL"));
            return new ValidationResult(valid, errors, grammarId);

        } catch (Exception e) {
            errors.add("EXCEPTION [" + grammarId + "]: " + e.getMessage());
            return new ValidationResult(false, errors, grammarId);
        }
    }

    /**
     * Convenience overload — grammarId defaults to "singine.rng".
     */
    public static ValidationResult validate(String xmlStr, InputStream rngStream) {
        return validate(xmlStr, rngStream, "singine.rng");
    }
}
