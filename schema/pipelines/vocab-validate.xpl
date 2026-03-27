<?xml version="1.0" encoding="UTF-8"?>
<!--
  pipelines/vocab-validate.xpl — XProc 3.0 schema validation pipeline
  ─────────────────────────────────────────────────────────────────────
  Tests that the core singine schema artifacts are loadable and
  well-formed.  Each file gets one iteration via p:for-each; a
  p:try / p:catch within each iteration catches load failures
  gracefully.  All results are collected into a <validation-report>
  and written to output/validation-report.xml.

  Files tested
  ────────────
    catalog.xml          OASIS XML Catalog (XML)
    singine.rnc          RELAX NG Compact (text)
    singine.sch          ISO Schematron (XML)
    singine.dtd          DTD (text)
    vocab/knowyourai.ttl KnowYourAI SKOS vocabulary (text)
    sinedge-api.yaml     sinedge OpenAPI spec (text)

  XProc 3.0 idioms used
  ─────────────────────
    p:for-each      iterate over a sequence of inline <file> descriptors
    p:try/p:catch   per-file error isolation
    p:choose        select content-type for p:load based on file descriptor
    p:wrap-sequence wrap the result sequence in <validation-report>
    p:add-attribute add timestamp and processor metadata to report

  Invocation
  ──────────
    make validate
    mvn exec:java -Dpipeline=pipelines/vocab-validate.xpl

  Processor: XML Calabash 3.0.42 (Norman Walsh)
  XProc:     3.0 / Saxon-HE 12.9
-->
<p:declare-step
  xmlns:p="http://www.w3.org/ns/xproc"
  xmlns:c="http://www.w3.org/ns/xproc-step"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  version="3.0"
  name="vocab-validate">

  <p:output port="result" primary="true"/>

  <!-- ── Test manifest: one <file> element per artifact to test ──────── -->
  <!--
    p:for-each iterates once per document in the input sequence.
    Each <file> element is its own document, so we get one iteration
    per file descriptor.

    Attributes:
      name         display name for the test report
      href         path relative to the pipeline file
      ct           content-type for p:load
                     application/xml  → load as XML, verifies well-formedness
                     text/plain       → load as text (RNC, TTL, YAML, DTD)
      type         test category label in the report
      ns           namespace URN declared in catalog.xml (informational)
  -->
  <p:for-each name="run-all-tests">
    <p:with-input>
      <p:inline>
        <file name="catalog.xml"
              href="../catalog.xml"
              ct="application/xml"
              type="xml-well-formed"
              ns="urn:oasis:names:tc:entity:xmlns:xml:catalog"/>
      </p:inline>
      <p:inline>
        <file name="singine.rnc"
              href="../singine.rnc"
              ct="text/plain"
              type="rnc-loadable"
              ns="urn:singine:schema:rnc:1.0"/>
      </p:inline>
      <p:inline>
        <file name="singine.sch"
              href="../singine.sch"
              ct="application/xml"
              type="schematron-well-formed"
              ns="urn:singine:schema:sch:1.0"/>
      </p:inline>
      <p:inline>
        <file name="singine.dtd"
              href="../singine.dtd"
              ct="text/plain"
              type="dtd-loadable"
              ns="urn:singine:dtd:1.0"/>
      </p:inline>
      <p:inline>
        <file name="vocab/knowyourai.ttl"
              href="../../vocab/knowyourai.ttl"
              ct="text/plain"
              type="ttl-loadable"
              ns="urn:knowyourai:vocab#"/>
      </p:inline>
      <p:inline>
        <file name="sinedge-api.yaml"
              href="../sinedge-api.yaml"
              ct="text/plain"
              type="yaml-loadable"
              ns="urn:singine:api:sinedge:v1"/>
      </p:inline>
    </p:with-input>

    <!-- Extract file attributes as variables for this iteration -->
    <p:variable name="file-name" select="string(/*/@name)"/>
    <p:variable name="file-href" select="string(/*/@href)"/>
    <p:variable name="file-ct"   select="string(/*/@ct)"/>
    <p:variable name="file-type" select="string(/*/@type)"/>
    <p:variable name="file-ns"   select="string(/*/@ns)"/>

    <!-- Try loading the file; catch any error and report it -->
    <p:try>
      <p:group>
        <p:load name="load-file" message="[validate] {$file-name} …">
          <p:with-option name="href"         select="$file-href"/>
          <p:with-option name="content-type" select="$file-ct"/>
        </p:load>
        <!-- Discard the loaded document; emit a pass result -->
        <p:identity>
          <p:with-input>
            <p:inline expand-text="true">
              <test name="{$file-name}"
                    status="pass"
                    type="{$file-type}"
                    ns="{$file-ns}">
                <note>Loaded successfully as {$file-ct}</note>
              </test>
            </p:inline>
          </p:with-input>
        </p:identity>
      </p:group>
      <p:catch name="catch-error">
        <!-- Emit a fail result with the error code from the catch -->
        <p:identity>
          <p:with-input>
            <p:inline expand-text="true">
              <test name="{$file-name}"
                    status="fail"
                    type="{$file-type}"
                    ns="{$file-ns}">
                <error>Could not load {$file-href} as {$file-ct}</error>
              </test>
            </p:inline>
          </p:with-input>
        </p:identity>
      </p:catch>
    </p:try>

  </p:for-each>
  <!-- p:for-each produces a sequence of <test> documents (one per iteration) -->

  <!-- ── Wrap the sequence in <validation-report> ─────────────────────── -->
  <p:wrap-sequence name="wrap-report" wrapper="validation-report"/>

  <!-- ── Add report metadata ──────────────────────────────────────────── -->
  <p:add-attribute name="add-timestamp"
                   attribute-name="generated"
                   match="validation-report">
    <p:with-option name="attribute-value" select="string(current-dateTime())"/>
  </p:add-attribute>

  <p:add-attribute name="add-processor"
                   attribute-name="processor"
                   attribute-value="XML Calabash 3.0.42 / Saxon-HE 12.9 (Norman Walsh)"
                   match="validation-report"/>

  <!-- ── Add summary counts ───────────────────────────────────────────── -->
  <p:insert name="add-summary" match="validation-report" position="first-child">
    <p:with-input port="insertion">
      <p:inline expand-text="false">
        <summary/>
      </p:inline>
    </p:with-input>
  </p:insert>

  <!-- ── Store validation report ──────────────────────────────────────── -->
  <p:store name="store-report"
           serialization="map{'indent': true(), 'method': 'xml'}"
           message="[validate] Writing report → output/validation-report.xml">
    <p:with-option name="href" select="'../output/validation-report.xml'"/>
  </p:store>

  <!-- ── Emit to primary output port ─────────────────────────────────── -->
  <p:identity name="emit-result">
    <p:with-input pipe="result@add-summary"/>
  </p:identity>

</p:declare-step>
