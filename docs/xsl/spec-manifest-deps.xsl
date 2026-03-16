<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:spec="https://markupware.com/ns/spec"
                version="1.0">

  <xsl:output method="xml" indent="yes" encoding="UTF-8"/>
  <xsl:strip-space elements="*"/>

  <xsl:template match="/spec:publication">
    <manpages generated-from="spec-publication.xml">
      <xsl:for-each select="spec:manpages/spec:page">
        <page name="{@name}" section="{@section}">
          <purpose><xsl:value-of select="@purpose"/></purpose>
          <xsl:for-each select="spec:see-also">
            <depends-on><xsl:value-of select="."/></depends-on>
          </xsl:for-each>
        </page>
      </xsl:for-each>
    </manpages>
  </xsl:template>
</xsl:stylesheet>
