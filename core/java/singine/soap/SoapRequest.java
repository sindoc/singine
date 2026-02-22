package singine.soap;

import org.w3c.dom.*;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.*;
import javax.xml.transform.stream.*;
import java.io.*;

/**
 * SoapRequest — builds a SOAP 1.2 request envelope for Singine LOCP
 * (Location Probe) operations.
 *
 * Mirrors SoapEnvelope (which handles responses) but is purpose-built
 * for outbound requests from the LOCP opcode.
 *
 * Namespaces:
 *   SOAP-ENV : http://www.w3.org/2003/05/soap-envelope
 *   locp     : urn:singine:pos:locp
 *
 * Wire format:
 *   <SOAP-ENV:Envelope>
 *     <SOAP-ENV:Header>
 *       <locp:RequestId>…</locp:RequestId>
 *       <locp:LocationUrn>…</locp:LocationUrn>
 *       <locp:Subject>…</locp:Subject>
 *       <locp:Calendar gregorian="…" persian="…" chinese="…"/>
 *     </SOAP-ENV:Header>
 *     <SOAP-ENV:Body>
 *       <locp:LocationProbeRequest>
 *         <locp:Query subject="…" location-urn="…"/>
 *       </locp:LocationProbeRequest>
 *     </SOAP-ENV:Body>
 *   </SOAP-ENV:Envelope>
 */
public class SoapRequest {

    private static final String NS_SOAP =
            "http://www.w3.org/2003/05/soap-envelope";
    private static final String NS_LOCP =
            "urn:singine:pos:locp";

    private final Document dom;
    private final Element  calendarEl;

    /**
     * Constructs a LOCP SOAP 1.2 request envelope.
     *
     * @param requestId   unique request identifier (e.g. "locp-2026-02-21-BRU")
     * @param locationUrn resolved location URN (e.g. "urn:singine:location:BE:BRU")
     * @param subject     CDN taxonomy subject (e.g. "standards", "exchange", "market")
     */
    public SoapRequest(String requestId, String locationUrn, String subject)
            throws ParserConfigurationException {

        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setNamespaceAware(true);
        DocumentBuilder db = dbf.newDocumentBuilder();
        this.dom = db.newDocument();

        // <SOAP-ENV:Envelope>
        Element envelope = dom.createElementNS(NS_SOAP, "SOAP-ENV:Envelope");
        envelope.setAttributeNS("http://www.w3.org/2000/xmlns/", "xmlns:SOAP-ENV", NS_SOAP);
        envelope.setAttributeNS("http://www.w3.org/2000/xmlns/", "xmlns:locp", NS_LOCP);
        dom.appendChild(envelope);

        // <SOAP-ENV:Header>
        Element header = dom.createElementNS(NS_SOAP, "SOAP-ENV:Header");
        envelope.appendChild(header);

        Element reqIdEl = dom.createElementNS(NS_LOCP, "locp:RequestId");
        reqIdEl.setTextContent(requestId);
        header.appendChild(reqIdEl);

        Element locUrnEl = dom.createElementNS(NS_LOCP, "locp:LocationUrn");
        locUrnEl.setTextContent(locationUrn);
        header.appendChild(locUrnEl);

        Element subjectEl = dom.createElementNS(NS_LOCP, "locp:Subject");
        subjectEl.setTextContent(subject);
        header.appendChild(subjectEl);

        // <locp:Calendar> — populated by setCalendar()
        this.calendarEl = dom.createElementNS(NS_LOCP, "locp:Calendar");
        header.appendChild(calendarEl);

        // <SOAP-ENV:Body>
        Element body = dom.createElementNS(NS_SOAP, "SOAP-ENV:Body");
        envelope.appendChild(body);

        // <locp:LocationProbeRequest>
        Element probeReq = dom.createElementNS(NS_LOCP, "locp:LocationProbeRequest");
        body.appendChild(probeReq);

        // <locp:Query subject="…" location-urn="…"/>
        Element queryEl = dom.createElementNS(NS_LOCP, "locp:Query");
        queryEl.setAttribute("subject", subject);
        queryEl.setAttribute("location-urn", locationUrn);
        queryEl.setAttribute("request-id", requestId);
        probeReq.appendChild(queryEl);
    }

    /**
     * Sets the triple-calendar attributes on the {@code <locp:Calendar>} header element.
     *
     * @param gregorianIso ISO 8601 date string (e.g. "2026-02-21")
     * @param persianYear  Persian calendar year (e.g. "1878")
     * @param chineseSex   Chinese sexagenary cycle name (e.g. "bǐng-wǔ")
     */
    public void setCalendar(String gregorianIso, String persianYear, String chineseSex) {
        calendarEl.setAttribute("gregorian", gregorianIso);
        calendarEl.setAttribute("persian", persianYear);
        calendarEl.setAttribute("chinese", chineseSex);
        calendarEl.setAttribute("tz", "Europe/London");
    }

    /**
     * Serializes the DOM to a UTF-8 XML string with 2-space indentation.
     * Exact Transformer pattern from SindocDocument / SoapEnvelope.
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
