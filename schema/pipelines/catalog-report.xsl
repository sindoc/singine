<?xml version="1.0" encoding="UTF-8"?>
<!--
  catalog-report.xsl — XSLT 3.0 catalog introspection transform
  ────────────────────────────────────────────────────────────────
  Reads an OASIS XML Catalog v1.1 document and produces a structured
  <catalog-report> XML summary with:
    • URI mapping count and entries
    • Public identifier mappings
    • Next-catalog delegation chain
    • Namespace prefix/URI alignment table

  Invoked by pipelines/hello.xpl via p:xslt.

  Processor: Saxon-HE 12.9 (via XML Calabash 3.0.42)
  XSLT version: 3.0
  XPath version: 3.1

  Norman Walsh pattern:
    expand-text="yes" for string interpolation
    xsl:mode on-no-match="shallow-copy" for identity baseline
-->
<xsl:stylesheet
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:cat="urn:oasis:names:tc:entity:xmlns:xml:catalog"
  xmlns:xs="http://www.w3.org/2001/XMLSchema"
  xmlns:sg="urn:singine:"
  version="3.0"
  expand-text="yes">

  <!-- Identity baseline: copy anything not otherwise matched -->
  <xsl:mode on-no-match="shallow-copy"/>

  <!-- ── Output: XML, indented ───────────────────────────────────────── -->
  <xsl:output method="xml" indent="yes" encoding="UTF-8"/>

  <!-- ── Main entry: / ───────────────────────────────────────────────── -->
  <xsl:template match="/">
    <xsl:variable name="uri-entries"    select="//cat:uri"/>
    <xsl:variable name="public-entries" select="//cat:public"/>
    <xsl:variable name="next-entries"   select="//cat:nextCatalog"/>

    <catalog-report
      xmlns:cat="urn:oasis:names:tc:entity:xmlns:xml:catalog"
      generated="{current-dateTime()}"
      processor="Saxon-HE 12 via XML Calabash 3.0.42 (Norman Walsh)"
      catalog-spec="OASIS XML Catalogs V1.1">

      <!-- ── Summary counts ─────────────────────────────────────────── -->
      <summary>
        <uri-mappings    count="{count($uri-entries)}"/>
        <public-mappings count="{count($public-entries)}"/>
        <next-catalogs   count="{count($next-entries)}"/>
        <total-entries   count="{count($uri-entries)
                                  + count($public-entries)
                                  + count($next-entries)}"/>
      </summary>

      <!-- ── URI mappings ──────────────────────────────────────────── -->
      <uri-mappings>
        <xsl:for-each select="$uri-entries">
          <xsl:sort select="@name"/>
          <uri
            name="{@name}"
            target="{@uri}">
            <xsl:choose>
              <xsl:when test="starts-with(@name, 'urn:singine:')">
                <xsl:attribute name="namespace">singine</xsl:attribute>
              </xsl:when>
              <xsl:when test="starts-with(@name, 'urn:knowyourai:')">
                <xsl:attribute name="namespace">knowyourai</xsl:attribute>
              </xsl:when>
              <xsl:when test="starts-with(@name, 'urn:urfm:')">
                <xsl:attribute name="namespace">urfm</xsl:attribute>
              </xsl:when>
              <xsl:when test="starts-with(@name, 'http://www.w3.org/')
                           or starts-with(@name, 'http://purl.org/')">
                <xsl:attribute name="namespace">w3c</xsl:attribute>
              </xsl:when>
              <xsl:otherwise>
                <xsl:attribute name="namespace">other</xsl:attribute>
              </xsl:otherwise>
            </xsl:choose>
          </uri>
        </xsl:for-each>
      </uri-mappings>

      <!-- ── Public ID mappings ────────────────────────────────────── -->
      <public-mappings>
        <xsl:for-each select="$public-entries">
          <xsl:sort select="@publicId"/>
          <public publicId="{@publicId}" target="{@uri}"/>
        </xsl:for-each>
      </public-mappings>

      <!-- ── Next-catalog delegation chain ─────────────────────────── -->
      <delegation-chain>
        <xsl:for-each select="$next-entries">
          <next-catalog href="{@catalog}"/>
        </xsl:for-each>
      </delegation-chain>

      <!-- ── Namespace prefix table ────────────────────────────────── -->
      <!--
        Groups URI entries by namespace family.
        This makes it easy to audit which vocabularies are covered.
      -->
      <namespace-table>
        <xsl:for-each-group select="$uri-entries"
                            group-by="sg:namespace-family(@name)">
          <xsl:sort select="current-grouping-key()"/>
          <family name="{current-grouping-key()}"
                  count="{count(current-group())}">
            <xsl:for-each select="current-group()">
              <xsl:sort select="@name"/>
              <entry name="{@name}" target="{@uri}"/>
            </xsl:for-each>
          </family>
        </xsl:for-each-group>
      </namespace-table>

    </catalog-report>
  </xsl:template>

  <!-- ── Helper: classify a URI by namespace family ──────────────────── -->
  <xsl:function name="sg:namespace-family" as="xs:string">
    <xsl:param name="uri" as="xs:string"/>
    <xsl:choose>
      <xsl:when test="starts-with($uri, 'urn:singine:')">singine</xsl:when>
      <xsl:when test="starts-with($uri, 'urn:knowyourai:')">knowyourai</xsl:when>
      <xsl:when test="starts-with($uri, 'urn:urfm:')">urfm</xsl:when>
      <xsl:when test="contains($uri, 'w3.org/2004/02/skos')">skos</xsl:when>
      <xsl:when test="contains($uri, 'w3.org/ns/dcat')">dcat</xsl:when>
      <xsl:when test="contains($uri, 'w3.org/ns/prov')">prov-o</xsl:when>
      <xsl:when test="contains($uri, 'w3.org/ns/shacl')">shacl</xsl:when>
      <xsl:when test="contains($uri, 'w3.org/ns/odrl')">odrl</xsl:when>
      <xsl:when test="contains($uri, 'w3.org/2002/07/owl')">owl</xsl:when>
      <xsl:when test="contains($uri, '1999/02/22-rdf')">rdf</xsl:when>
      <xsl:when test="contains($uri, 'purl.org/dc/')">dublin-core</xsl:when>
      <xsl:when test="contains($uri, 'w3.org/2005/Atom')">atom</xsl:when>
      <xsl:when test="contains($uri, 'omg.org/spec/SBVR')">sbvr</xsl:when>
      <xsl:when test="contains($uri, 'docbook.org')">docbook</xsl:when>
      <xsl:when test="contains($uri, 'collibra')">collibra</xsl:when>
      <xsl:otherwise>other</xsl:otherwise>
    </xsl:choose>
  </xsl:function>

</xsl:stylesheet>
