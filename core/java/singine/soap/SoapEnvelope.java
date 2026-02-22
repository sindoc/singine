package singine.soap;

import org.w3c.dom.*;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.*;
import javax.xml.transform.stream.*;
import java.io.*;

/**
 * SoapEnvelope — builds a SOAP 1.2 envelope DOM for the Singine
 * extension-check response protocol.
 *
 * Namespaces:
 *   SOAP-ENV : http://www.w3.org/2003/05/soap-envelope
 *   singine   : singine:os/extension-check
 */
public class SoapEnvelope {

    private static final String NS_SOAP =
            "http://www.w3.org/2003/05/soap-envelope";
    private static final String NS_SINGINE =
            "singine:os/extension-check";

    private final Document dom;
    private final Element  extensionCheckResponseEl;
    private final Element  probeResultsEl;

    /**
     * Builds the envelope skeleton with header fields populated.
     *
     * @param requestId   value for &lt;singine:RequestId&gt;
     * @param extension   value for &lt;singine:Extension&gt;
     * @param checkedAt   value for &lt;singine:CheckedAt&gt;
     */
    public SoapEnvelope(String requestId, String extension, String checkedAt)
            throws ParserConfigurationException {

        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setNamespaceAware(true);
        DocumentBuilder db = dbf.newDocumentBuilder();
        this.dom = db.newDocument();

        // <SOAP-ENV:Envelope xmlns:SOAP-ENV="..." xmlns:singine="...">
        Element envelope = dom.createElementNS(NS_SOAP, "SOAP-ENV:Envelope");
        envelope.setAttributeNS(
                "http://www.w3.org/2000/xmlns/",
                "xmlns:SOAP-ENV", NS_SOAP);
        envelope.setAttributeNS(
                "http://www.w3.org/2000/xmlns/",
                "xmlns:singine", NS_SINGINE);
        dom.appendChild(envelope);

        // <SOAP-ENV:Header>
        Element header = dom.createElementNS(NS_SOAP, "SOAP-ENV:Header");
        envelope.appendChild(header);

        Element reqIdEl = dom.createElementNS(NS_SINGINE, "singine:RequestId");
        reqIdEl.setTextContent(requestId);
        header.appendChild(reqIdEl);

        Element extensionEl = dom.createElementNS(NS_SINGINE, "singine:Extension");
        extensionEl.setTextContent(extension);
        header.appendChild(extensionEl);

        Element checkedAtEl = dom.createElementNS(NS_SINGINE, "singine:CheckedAt");
        checkedAtEl.setTextContent(checkedAt);
        header.appendChild(checkedAtEl);

        // <SOAP-ENV:Body>
        Element body = dom.createElementNS(NS_SOAP, "SOAP-ENV:Body");
        envelope.appendChild(body);

        // <singine:ExtensionCheckResponse>
        this.extensionCheckResponseEl =
                dom.createElementNS(NS_SINGINE, "singine:ExtensionCheckResponse");
        body.appendChild(extensionCheckResponseEl);

        // <singine:ProbeResults/>  — populated by addProbeResult()
        this.probeResultsEl =
                dom.createElementNS(NS_SINGINE, "singine:ProbeResults");
        extensionCheckResponseEl.appendChild(probeResultsEl);
    }

    /**
     * Creates a &lt;singine:Verdict overall="OVERALL"&gt;TEXT&lt;/singine:Verdict&gt;
     * and inserts it as the first child of ExtensionCheckResponse (before ProbeResults).
     *
     * @param overall attribute value for {@code overall}
     * @param text    text content of the element
     */
    public void setVerdict(String overall, String text) {
        Element verdict = dom.createElementNS(NS_SINGINE, "singine:Verdict");
        verdict.setAttribute("overall", overall);
        verdict.setTextContent(text);
        extensionCheckResponseEl.insertBefore(verdict, probeResultsEl);
    }

    /**
     * Appends a probe result to &lt;singine:ProbeResults&gt;:
     *
     * <pre>{@code
     * <singine:Probe id="N" dimension="DIM" severity="SEV">
     *   <singine:Command>CMD</singine:Command>
     *   <singine:Output>OUT</singine:Output>
     *   <singine:Finding>FINDING</singine:Finding>
     * </singine:Probe>
     * }</pre>
     *
     * @param probeId   numeric probe identifier
     * @param dimension probe dimension label
     * @param severity  severity level
     * @param command   command that was run
     * @param output    raw output of the command
     * @param finding   human-readable finding
     */
    public void addProbeResult(int probeId, String dimension, String severity,
                               String command, String output, String finding) {

        Element probe = dom.createElementNS(NS_SINGINE, "singine:Probe");
        probe.setAttribute("id", Integer.toString(probeId));
        probe.setAttribute("dimension", dimension);
        probe.setAttribute("severity", severity);

        Element commandEl = dom.createElementNS(NS_SINGINE, "singine:Command");
        commandEl.setTextContent(command);
        probe.appendChild(commandEl);

        Element outputEl = dom.createElementNS(NS_SINGINE, "singine:Output");
        outputEl.setTextContent(output);
        probe.appendChild(outputEl);

        Element findingEl = dom.createElementNS(NS_SINGINE, "singine:Finding");
        findingEl.setTextContent(finding);
        probe.appendChild(findingEl);

        probeResultsEl.appendChild(probe);
    }

    /**
     * Creates a &lt;singine:SummaryTable&gt; element whose sole child is a
     * {@code CDATASection} containing {@code table}, and appends it to
     * ExtensionCheckResponse (after ProbeResults).
     *
     * @param table raw text to wrap in CDATA
     */
    public void setSummaryTable(String table) {
        Element summaryTable =
                dom.createElementNS(NS_SINGINE, "singine:SummaryTable");
        CDATASection cdata = dom.createCDATASection(table);
        summaryTable.appendChild(cdata);
        extensionCheckResponseEl.appendChild(summaryTable);
    }

    /**
     * Serializes the DOM to a UTF-8 XML string with 2-space indentation.
     * Uses the exact Transformer pattern from SindocDocument.
     */
    public String toXmlString() throws TransformerException {
        TransformerFactory tf = TransformerFactory.newInstance();
        try { tf.setAttribute("indent-number", 2); } catch (IllegalArgumentException ignored) {}
        Transformer t = tf.newTransformer();
        t.setOutputProperty(OutputKeys.ENCODING, "UTF-8");
        t.setOutputProperty(OutputKeys.INDENT, "yes");
        t.setOutputProperty("{http://xml.apache.org/xslt}indent-amount", "2");
        StringWriter sw = new StringWriter();
        t.transform(new DOMSource(dom), new StreamResult(sw));
        return sw.toString();
    }

    @Override
    public String toString() {
        try { return toXmlString(); }
        catch (TransformerException e) { return "<error>" + e.getMessage() + "</error>"; }
    }
}
