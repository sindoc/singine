package singine.soap;

import org.w3c.dom.*;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.*;
import javax.xml.transform.stream.*;
import java.io.*;

/**
 * SoapFault — static utility for building SOAP 1.2 Fault envelopes.
 *
 * All methods are static; this class is not meant to be instantiated.
 */
public class SoapFault {

    private static final String NS_SOAP =
            "http://www.w3.org/2003/05/soap-envelope";

    private SoapFault() {}

    /**
     * Builds a SOAP 1.2 Fault envelope and serializes it to an XML string.
     *
     * <pre>{@code
     * <SOAP-ENV:Envelope xmlns:SOAP-ENV="http://www.w3.org/2003/05/soap-envelope">
     *   <SOAP-ENV:Body>
     *     <SOAP-ENV:Fault>
     *       <SOAP-ENV:Code>
     *         <SOAP-ENV:Value>CODE</SOAP-ENV:Value>
     *       </SOAP-ENV:Code>
     *       <SOAP-ENV:Reason>
     *         <SOAP-ENV:Text xml:lang="en">REASON</SOAP-ENV:Text>
     *       </SOAP-ENV:Reason>
     *       <SOAP-ENV:Detail>DETAIL</SOAP-ENV:Detail>
     *     </SOAP-ENV:Fault>
     *   </SOAP-ENV:Body>
     * </SOAP-ENV:Envelope>
     * }</pre>
     *
     * @param code   fault code (e.g. {@code "SOAP-ENV:Sender"})
     * @param reason human-readable fault reason
     * @param detail additional fault detail
     * @return indented UTF-8 XML string
     */
    public static String buildFault(String code, String reason, String detail)
            throws Exception {

        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setNamespaceAware(true);
        DocumentBuilder db = dbf.newDocumentBuilder();
        Document dom = db.newDocument();

        // <SOAP-ENV:Envelope xmlns:SOAP-ENV="...">
        Element envelope = dom.createElementNS(NS_SOAP, "SOAP-ENV:Envelope");
        envelope.setAttributeNS(
                "http://www.w3.org/2000/xmlns/",
                "xmlns:SOAP-ENV", NS_SOAP);
        dom.appendChild(envelope);

        // <SOAP-ENV:Body>
        Element body = dom.createElementNS(NS_SOAP, "SOAP-ENV:Body");
        envelope.appendChild(body);

        // <SOAP-ENV:Fault>
        Element fault = dom.createElementNS(NS_SOAP, "SOAP-ENV:Fault");
        body.appendChild(fault);

        // <SOAP-ENV:Code><SOAP-ENV:Value>CODE</SOAP-ENV:Value></SOAP-ENV:Code>
        Element codeEl = dom.createElementNS(NS_SOAP, "SOAP-ENV:Code");
        fault.appendChild(codeEl);
        Element valueEl = dom.createElementNS(NS_SOAP, "SOAP-ENV:Value");
        valueEl.setTextContent(code);
        codeEl.appendChild(valueEl);

        // <SOAP-ENV:Reason><SOAP-ENV:Text xml:lang="en">REASON</SOAP-ENV:Text></SOAP-ENV:Reason>
        Element reasonEl = dom.createElementNS(NS_SOAP, "SOAP-ENV:Reason");
        fault.appendChild(reasonEl);
        Element textEl = dom.createElementNS(NS_SOAP, "SOAP-ENV:Text");
        textEl.setAttributeNS(
                "http://www.w3.org/XML/1998/namespace",
                "xml:lang", "en");
        textEl.setTextContent(reason);
        reasonEl.appendChild(textEl);

        // <SOAP-ENV:Detail>DETAIL</SOAP-ENV:Detail>
        Element detailEl = dom.createElementNS(NS_SOAP, "SOAP-ENV:Detail");
        detailEl.setTextContent(detail);
        fault.appendChild(detailEl);

        // Serialize — exact Transformer pattern from SindocDocument
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
}
