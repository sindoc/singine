package singine.sindoc;

import org.w3c.dom.*;
import javax.xml.parsers.*;
import javax.xml.transform.*;
import javax.xml.transform.dom.*;
import javax.xml.transform.stream.*;
import java.io.*;
import java.util.*;

/**
 * SindocDocument — the parsed representation of a .sindoc file as a DOM tree.
 *
 * The root element is &lt;document&gt; (or whatever the metamodel specifies via
 * {@code @meta output-root-element}).  All content is structured under it.
 *
 * Exposes helpers used by the Clojure bridge:
 *   - {@link #toXmlString()}   — serialize to indented XML string
 *   - {@link #getRoot()}       — the DOM root Element
 *   - {@link #getDocument()}   — the underlying org.w3c.dom.Document
 */
public class SindocDocument {

    private final Document dom;
    private final Element  root;

    /** Package-visible constructor; built exclusively by SindocParser. */
    SindocDocument(String rootElementName, Map<String, String> rootAttributes)
        throws ParserConfigurationException {

        DocumentBuilderFactory dbf = DocumentBuilderFactory.newInstance();
        dbf.setNamespaceAware(true);
        DocumentBuilder db = dbf.newDocumentBuilder();
        this.dom  = db.newDocument();
        this.root = dom.createElement(rootElementName);

        for (Map.Entry<String, String> e : rootAttributes.entrySet()) {
            root.setAttribute(e.getKey(), e.getValue());
        }
        dom.appendChild(root);
    }

    /** Append a child element under the root. */
    public Element appendToRoot(String tagName, Map<String, String> attributes,
                                String textContent) {
        return appendChild(root, tagName, attributes, textContent);
    }

    /** Append a child element under {@code parent}. */
    public Element appendChild(Element parent, String tagName,
                               Map<String, String> attributes, String textContent) {
        Element el = dom.createElement(tagName);
        if (attributes != null) {
            for (Map.Entry<String, String> e : attributes.entrySet()) {
                el.setAttribute(e.getKey(), e.getValue());
            }
        }
        if (textContent != null && !textContent.isEmpty()) {
            el.setTextContent(textContent);
        }
        parent.appendChild(el);
        return el;
    }

    /** Open a new child element under root, returning it for further appending. */
    public Element openSection(String tagName, Map<String, String> attributes) {
        Element el = dom.createElement(tagName);
        if (attributes != null) {
            for (Map.Entry<String, String> e : attributes.entrySet()) {
                el.setAttribute(e.getKey(), e.getValue());
            }
        }
        root.appendChild(el);
        return el;
    }

    public Element getRoot()     { return root; }
    public Document getDocument() { return dom; }

    /**
     * Serialize the DOM to a UTF-8 XML string with 2-space indentation.
     */
    public String toXmlString() throws TransformerException {
        TransformerFactory tf = TransformerFactory.newInstance();
        try {
            tf.setAttribute("indent-number", 2);
        } catch (IllegalArgumentException ignored) { /* not all impls support it */ }

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
