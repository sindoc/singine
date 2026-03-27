<?xml version="1.0" encoding="UTF-8"?>
<!--
  datatech-site.xpl — XProc 3.0 site build pipeline
  ────────────────────────────────────────────────────
  Builds the datatech-wiki-kg static website from XML sources.

  Source layout
  ─────────────
    datatech-wiki-kg/site/src/xml/en/layout.xml   site structure + TOC
    datatech-wiki-kg/site/src/xml/en/*.xml         article XML files
    datatech-wiki-kg/site/src/css/*.css            stylesheets

  Output
  ──────
    datatech-wiki-kg/site/build/en/index.html
    datatech-wiki-kg/site/build/en/about/index.html
    datatech-wiki-kg/site/build/en/docs/index.html
    datatech-wiki-kg/site/build/en/plan/index.html
    datatech-wiki-kg/site/build/en/backlog/index.html
    datatech-wiki-kg/site/build/en/roadmap/index.html
    datatech-wiki-kg/site/build/en/process/index.html
    datatech-wiki-kg/site/build/en/css/foss-wikipedia.css
    datatech-wiki-kg/site/build/build-report.xml

  Design note: page-dir is injected into each article root element via
  p:add-attribute before XSLT, avoiding the need for xslt parameters.
  The XSLT reads /*/@page-dir directly from the source document.

  XProc 3.0 idioms used
  ─────────────────────
    p:load          load XML and text artifacts
    p:for-each      iterate over toc|tocentry nodes from layout.xml
    p:add-attribute inject page-dir into article before XSLT
    p:xslt          transform each article to HTML5
    p:store         write HTML and CSS to build output
    p:wrap-sequence collect per-page results into build-report
    p:add-attribute add timestamp to report

  Invocation
  ──────────
    make site
    mvn exec:java -Dpipeline=pipelines/datatech-site.xpl

  Processor: XML Calabash 3.0.42 / Saxon-HE 12.9
-->
<p:declare-step
  xmlns:p="http://www.w3.org/ns/xproc"
  xmlns:c="http://www.w3.org/ns/xproc-step"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  version="3.0"
  name="datatech-site-build">

  <p:output port="result" primary="true"/>

  <!-- ── Path roots (relative to this pipeline file) ────────── -->
  <!--
    From pipelines/ up three levels reaches sindoc/, then down into
    datatech-wiki-kg/:
      pipelines/ -> schema/ -> singine/ -> sindoc/ -> datatech-wiki-kg/
  -->
  <p:variable name="src-root"
    select="'../../../datatech-wiki-kg/site/src/xml/en'"/>
  <p:variable name="build-root"
    select="'../../../datatech-wiki-kg/site/build/en'"/>

  <!-- ── Load site layout ────────────────────────────────────── -->
  <p:load name="load-layout"
          message="[datatech-site] Loading layout.xml …">
    <p:with-option name="href" select="concat($src-root, '/layout.xml')"/>
  </p:load>

  <!-- ── Copy stylesheet to build output ─────────────────────── -->
  <p:load name="load-css"
          content-type="text/plain"
          message="[datatech-site] Copying foss-wikipedia.css …">
    <p:with-option name="href"
      select="'../../../datatech-wiki-kg/site/src/css/foss-wikipedia.css'"/>
  </p:load>

  <p:store name="store-css"
           serialization="map{'method': 'text'}"
           message="[datatech-site] Wrote build/en/css/foss-wikipedia.css">
    <p:with-option name="href"
      select="concat($build-root, '/css/foss-wikipedia.css')"/>
  </p:store>

  <!-- ── Build each page in the TOC ──────────────────────────── -->
  <!--
    p:for-each iterates over every toc and tocentry element in layout.xml.
    Each iteration receives the element as the current document (/*).

    toc      -> root page     (no @dir, filename="index.html")
    tocentry -> subdirectory  (@dir="about" etc.)
  -->
  <p:for-each name="build-pages">
    <p:with-input select="//(toc|tocentry)" pipe="result@load-layout"/>

    <!-- Extract attributes for this page -->
    <p:variable name="el-name"   select="local-name(/*)"/>
    <p:variable name="page-src"  select="string(/*/@page)"/>
    <p:variable name="page-dir"  select="if ($el-name = 'toc') then '' else string(/*/@dir)"/>
    <p:variable name="page-file" select="string(/*/@filename)"/>
    <p:variable name="out-href"  select="
      if ($page-dir = '')
      then concat($build-root, '/', $page-file)
      else concat($build-root, '/', $page-dir, '/', $page-file)
    "/>

    <p:try>
      <p:group>

        <!-- Load the article XML source -->
        <p:load name="load-article"
                message="[datatech-site] Building {$page-src} …">
          <p:with-option name="href"
            select="concat($src-root, '/', $page-src)"/>
        </p:load>

        <!--
          Inject page-dir into the article root as @page-dir.
          The XSLT reads collection()[1]/*/@page-dir (global variable context)
          to avoid the absent-context-item error.
        -->
        <p:add-attribute name="inject-page-dir"
                         attribute-name="page-dir"
                         match="/*">
          <p:with-input pipe="result@load-article"/>
          <p:with-option name="attribute-value" select="$page-dir"/>
        </p:add-attribute>

        <!--
          Transform: article (primary, with injected @page-dir)
                   + layout  (secondary, collection()[2] in XSLT)
                   -> HTML5
        -->
        <p:xslt name="transform-article">
          <p:with-input port="source">
            <p:pipe step="inject-page-dir" port="result"/>
            <p:pipe step="load-layout"     port="result"/>
          </p:with-input>
          <p:with-input port="stylesheet" href="datatech-site.xsl"/>
        </p:xslt>

        <!-- Write HTML file (Calabash creates parent directories) -->
        <p:store name="store-page"
                 serialization="map{'method': 'html', 'html-version': 5, 'indent': true()}"
                 message="[datatech-site] Wrote {$out-href}">
          <p:with-option name="href" select="$out-href"/>
        </p:store>

        <!-- Emit pass record -->
        <p:identity>
          <p:with-input>
            <p:inline expand-text="true">
              <page src="{$page-src}"
                    dir="{$page-dir}"
                    out="{$out-href}"
                    status="built"/>
            </p:inline>
          </p:with-input>
        </p:identity>

      </p:group>
      <p:catch name="catch-page-error">
        <!-- errors port is the implicit default readable port inside p:catch -->
        <p:identity/>
      </p:catch>
    </p:try>

  </p:for-each>

  <!-- ── Collect results into a build report ─────────────────── -->
  <p:wrap-sequence name="wrap-report" wrapper="build-report"/>

  <p:add-attribute name="add-timestamp"
                   attribute-name="generated"
                   match="build-report">
    <p:with-option name="attribute-value" select="string(current-dateTime())"/>
  </p:add-attribute>

  <!-- ── Store build report ───────────────────────────────────── -->
  <p:store name="store-report"
           serialization="map{'indent': true(), 'method': 'xml'}"
           message="[datatech-site] Writing build-report.xml">
    <p:with-option name="href"
      select="'../../../datatech-wiki-kg/site/build/build-report.xml'"/>
  </p:store>

  <!-- ── Emit to primary output port ─────────────────────────── -->
  <p:identity name="emit-result">
    <p:with-input pipe="result@add-timestamp"/>
  </p:identity>

</p:declare-step>
