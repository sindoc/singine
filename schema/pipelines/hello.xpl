<?xml version="1.0" encoding="UTF-8"?>
<!--
  pipelines/hello.xpl — XProc 3.0 smoke test
  ────────────────────────────────────────────
  Minimal end-to-end test verifying:
    1. Calabash 3.x loads and interprets XProc 3.0 correctly
    2. Saxon-HE 12 executes XSLT 3.0 (via p:xslt)
    3. XML Catalog resolution is active (xmlresolver 6.x)
    4. p:load, p:xslt, p:store, p:identity all work correctly

  What it does
  ────────────
  Loads schema/catalog.xml as an XML document, applies the
  catalog-report.xsl XSLT 3.0 transform to produce a structured
  <catalog-report> summary, writes it to output/catalog-report.xml,
  and emits it to the primary output port (stdout by default).

  Invocation (via Makefile / Maven)
  ─────────────────────────────────
    make test
    mvn exec:exec -Dpipeline=pipelines/hello.xpl

  Direct invocation (after Calabash is on PATH)
  ──────────────────────────────────────────────
    calabash -catalog:schema/catalog.xml pipelines/hello.xpl

  Ports
  ─────
  Primary output: the catalog-report XML document.
  No primary input required (p:empty is the implicit source).

  Processor: XML Calabash 3.0.42 (Norman Walsh)
  XSLT:      Saxon-HE 12.9 (via Calabash transitive dep)
  Catalog:   xmlresolver 6.0.21 (set via JVM system property)
  XProc:     3.0  (namespace: http://www.w3.org/ns/xproc)
-->
<p:declare-step
  xmlns:p="http://www.w3.org/ns/xproc"
  xmlns:cx="http://xmlcalabash.com/ns/extensions"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns:sg="urn:singine:"
  version="3.0"
  name="singine-hello">

  <!-- ── Ports ────────────────────────────────────────────────────────── -->

  <!-- Primary output: catalog-report XML -->
  <p:output port="result" primary="true"/>

  <!-- ── Options ──────────────────────────────────────────────────────── -->

  <!-- Path to the master catalog (relative to pipeline file) -->
  <p:option name="catalog-path"  as="xs:string"
            select="'../catalog.xml'"/>

  <!-- Output path for the catalog report -->
  <p:option name="report-path"   as="xs:string"
            select="'../output/catalog-report.xml'"/>

  <!-- ── Step 1: Load catalog.xml ─────────────────────────────────────── -->
  <!--
    p:load with a relative URI: Calabash resolves relative to the pipeline
    file's base URI.  The document is loaded as an XML document.
    Catalog resolution is active (xmlresolver system property).
  -->
  <p:load name="load-catalog"
          href="../catalog.xml"
          message="[singine] Loading master catalog: catalog.xml"/>

  <!-- ── Step 2: XSLT 3.0 transform (Saxon-HE 12.9) ───────────────────── -->
  <!--
    Apply catalog-report.xsl to produce a structured catalog-report document.
    This step exercises:
      • p:xslt with an inline stylesheet reference
      • Saxon-HE 12.9 XSLT 3.0 processing (expand-text, xsl:mode, for-each-group)
      • XPath 3.1 functions (current-dateTime, starts-with, contains)
      • Custom function (sg:namespace-family)
  -->
  <p:xslt name="apply-catalog-report">
    <p:with-input port="source"     pipe="result@load-catalog"/>
    <p:with-input port="stylesheet" href="catalog-report.xsl"/>
  </p:xslt>

  <!-- ── Step 3: Store result to output/catalog-report.xml ─────────────── -->
  <!--
    Write the catalog-report document to disk so it can be inspected
    independently of the pipeline run.  The p:store step does NOT
    consume the document; the result continues to flow downstream.
  -->
  <p:store name="store-report"
           serialization="map{'indent': true(), 'method': 'xml'}"
           message="[singine] Writing report to output/catalog-report.xml">
    <p:with-input pipe="result@apply-catalog-report"/>
    <p:with-option name="href" select="$report-path"/>
  </p:store>

  <!-- ── Step 4: Emit to primary output port ───────────────────────────── -->
  <!--
    Forward the catalog-report document to the primary output port.
    When run via `mvn exec:exec`, Calabash serializes this to stdout.
    p:identity is a no-op step that just routes the document.
  -->
  <p:identity name="emit-result">
    <p:with-input pipe="result@apply-catalog-report"/>
  </p:identity>

</p:declare-step>
