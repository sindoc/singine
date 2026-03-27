<?xml version="1.0" encoding="UTF-8"?>
<!--
  datatech-site.xsl — XSLT 3.0 transform: article XML → HTML5
  ──────────────────────────────────────────────────────────────
  Primary input:  article XML  (root = <article>)
  Secondary input: layout.xml  (accessible via collection()[2])
  Parameter:
    page-dir   ""        root page  (index.html)
               "about"  subdirectory page (about/index.html) etc.

  Output: HTML5 page with header, nav, main, footer.

  Vocabulary handled
  ──────────────────
    article / title / subtitle
    section / title
    para
    itemizedlist / listitem / para
-->
<xsl:stylesheet version="3.0"
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  expand-text="yes">

  <xsl:output method="html" html-version="5" encoding="UTF-8" indent="yes"/>
  <xsl:mode on-no-match="shallow-skip"/>

  <!-- ── Derived values ─────────────────────────────────────── -->
  <!--
    page-dir is injected into the article root as @page-dir by the XProc
    pipeline (p:add-attribute) before XSLT is invoked.
    Access via collection()[1]/* to avoid the absent context-item error
    that occurs in global xsl:variable evaluation.
    Empty string = root page; non-empty = one-level subdirectory.
  -->
  <xsl:variable name="page-dir" as="xs:string"
    select="string(collection()[1]/*/@page-dir)"/>

  <!-- Path prefix to reach site root from this page -->
  <xsl:variable name="root" as="xs:string"
    select="if ($page-dir = '') then '' else '../'"/>

  <!-- Layout document: second item in source collection -->
  <xsl:variable name="layout" select="collection()[2]/layout"/>

  <!-- Site title from layout config -->
  <xsl:variable name="site-title" as="xs:string"
    select="string($layout/config[@param='title']/@value)"/>

  <!-- CSS href, adjusted for depth -->
  <xsl:variable name="css-href" as="xs:string"
    select="concat($root, string($layout/style/@src))"/>

  <!-- Copyright -->
  <xsl:variable name="copy-year"   select="string($layout/copyright/year)"/>
  <xsl:variable name="copy-holder" select="string($layout/copyright/holder)"/>

  <!-- ── Root template ──────────────────────────────────────── -->
  <xsl:template match="/article">
    <html lang="en">
      <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        <title>
          <xsl:choose>
            <xsl:when test="title and string(title) != $site-title"
              >{title} — {$site-title}</xsl:when>
            <xsl:otherwise>{$site-title}</xsl:otherwise>
          </xsl:choose>
        </title>
        <link rel="stylesheet" href="{$css-href}"/>
      </head>
      <body>
        <header>
          <div class="page-wrap">
            <a class="site-name" href="{$root}index.html">{$site-title}</a>
            <nav>
              <xsl:call-template name="site-nav"/>
            </nav>
          </div>
        </header>

        <main>
          <h1>{title}</h1>
          <xsl:if test="subtitle">
            <p class="subtitle">{subtitle}</p>
          </xsl:if>
          <xsl:apply-templates select="para | section"/>
        </main>

        <footer>
          <p>&#169; {$copy-year} {$copy-holder}</p>
        </footer>
      </body>
    </html>
  </xsl:template>

  <!-- ── Navigation ─────────────────────────────────────────── -->
  <xsl:template name="site-nav">
    <ul>
      <xsl:for-each select="$layout/toc/tocentry">
        <xsl:variable name="dir"  select="string(@dir)"/>
        <xsl:variable name="file" select="string(@filename)"/>
        <xsl:variable name="label" as="xs:string"
          select="concat(upper-case(substring($dir,1,1)), substring($dir,2))"/>
        <li>
          <a href="{$root}{$dir}/{$file}">{$label}</a>
          <xsl:if test="tocentry">
            <ul>
              <xsl:for-each select="tocentry">
                <xsl:variable name="sdir"  select="string(@dir)"/>
                <xsl:variable name="sfile" select="string(@filename)"/>
                <xsl:variable name="slabel" as="xs:string"
                  select="concat(upper-case(substring($sdir,1,1)), substring($sdir,2))"/>
                <li>
                  <a href="{$root}{$sdir}/{$sfile}">{$slabel}</a>
                </li>
              </xsl:for-each>
            </ul>
          </xsl:if>
        </li>
      </xsl:for-each>
    </ul>
  </xsl:template>

  <!-- ── Article body elements ──────────────────────────────── -->
  <xsl:template match="para">
    <p><xsl:apply-templates/></p>
  </xsl:template>

  <xsl:template match="section">
    <section>
      <h2>{title}</h2>
      <xsl:apply-templates select="para | itemizedlist"/>
    </section>
  </xsl:template>

  <xsl:template match="itemizedlist">
    <ul>
      <xsl:apply-templates select="listitem"/>
    </ul>
  </xsl:template>

  <xsl:template match="listitem">
    <li><xsl:apply-templates select="para"/></li>
  </xsl:template>

  <!-- Inline text passthrough -->
  <xsl:template match="text()">
    <xsl:value-of select="."/>
  </xsl:template>

</xsl:stylesheet>
