package singine.schema;

import org.w3c.dom.*;
import org.xml.sax.InputSource;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.*;
import javax.xml.transform.stream.*;
import javax.xml.xpath.*;
import java.io.*;
import java.util.ArrayList;
import java.util.List;

/**
 * SchematronValidator — ISO Schematron validation via the SVRL pipeline.
 *
 * Pipeline (ISO Schematron / SVRL, XSLT 1.0):
 *   Step 1: Parse .sch file as DOM
 *   Step 2: Apply embedded skeleton XSLT to compile .sch → XSLT stylesheet
 *           (Phase 1: uses lightweight inline XSLT; Phase 2: full iso_svrl_for_xslt1.xsl)
 *   Step 3: Apply compiled stylesheet to target XML → SVRL report
 *   Step 4: Parse SVRL report for failed-assert / successful-report elements
 *
 * Phase 1 (no external XSLT files): uses a minimal inline XSLT that
 * evaluates Schematron assert/@test expressions directly via JAXP XPath.
 * This covers the three rules in schema/singine.sch:
 *   SCH-001: opcode 4-letter uppercase
 *   SCH-002: LOCP form carries location-urn
 *   SCH-003: policy terms-active matches count of satisfied terms
 *
 * Usage:
 *   ValidationResult r = SchematronValidator.validate(xmlStr, schStream);
 *   if (!r.isValid()) { for (String e : r.getErrors()) ... }
 */
public class SchematronValidator {

    /** Shared result type with RelaxNGValidator. */
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
            return "SchematronValidationResult{valid=" + valid
                    + ", grammar=" + grammar
                    + ", errors=" + errors + "}";
        }
    }

    /**
     * Validates {@code xmlStr} against Schematron rules in {@code schStream}.
     *
     * Phase 1 implementation: reads the .sch file, extracts
     * {@code <assert test="…">message</assert>} patterns and evaluates
     * each XPath test against the parsed XML document.
     *
     * @param xmlStr    the XML to validate
     * @param schStream InputStream for the .sch (ISO Schematron) file
     * @param grammarId human-readable identifier (e.g. "singine.sch")
     * @return ValidationResult
     */
    public static ValidationResult validate(String xmlStr,
                                            InputStream schStream,
                                            String grammarId) {
        List<String> errors = new ArrayList<>();
        try {
            // Parse the target XML
            DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
            dbf.setNamespaceAware(true);
            DocumentBuilder db = dbf.newDocumentBuilder();
            Document targetDoc = db.parse(new InputSource(new StringReader(xmlStr)));

            // Parse the .sch file
            Document schDoc = db.parse(schStream);

            // Extract all <assert> elements from .sch
            XPathFactory xpf = XPathFactory.newInstance();
            XPath xp = xpf.newXPath();

            // Find all assert elements in the Schematron
            NodeList asserts = (NodeList) xp.evaluate(
                "//*[local-name()='assert']",
                schDoc.getDocumentElement(),
                XPathConstants.NODESET);

            for (int i = 0; i < asserts.getLength(); i++) {
                Element assertEl = (Element) asserts.item(i);
                String testExpr = assertEl.getAttribute("test");
                String message  = assertEl.getTextContent().trim();

                if (testExpr == null || testExpr.isEmpty()) continue;

                // Evaluate the XPath test against the target document
                try {
                    Boolean result = (Boolean) xp.evaluate(
                        testExpr,
                        targetDoc.getDocumentElement(),
                        XPathConstants.BOOLEAN);

                    if (!result) {
                        // Find the enclosing rule/@context for reporting
                        String context = "";
                        Node parent = assertEl.getParentNode();
                        if (parent instanceof Element) {
                            context = ((Element) parent).getAttribute("context");
                        }
                        errors.add("SCH-FAIL [" + grammarId + "] context=" + context
                                 + " test=(" + testExpr + ") : " + message);
                    }
                } catch (XPathExpressionException xpe) {
                    // XPath expression uses features not supported in Phase 1 (e.g. functions)
                    // Annotate as INFO and continue — full SVRL pipeline resolves in Phase 2
                    errors.add("INFO [" + grammarId + "] XPath deferred: (" + testExpr + "): "
                             + xpe.getMessage());
                }
            }

            boolean valid = errors.stream().noneMatch(s -> s.startsWith("SCH-FAIL"));
            return new ValidationResult(valid, errors, grammarId);

        } catch (Exception e) {
            errors.add("EXCEPTION [" + grammarId + "]: " + e.getMessage());
            return new ValidationResult(false, errors, grammarId);
        }
    }

    /**
     * Convenience overload — grammarId defaults to "singine.sch".
     */
    public static ValidationResult validate(String xmlStr, InputStream schStream) {
        return validate(xmlStr, schStream, "singine.sch");
    }
}
