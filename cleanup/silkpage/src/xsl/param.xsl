<?xml version="1.0" encoding="UTF-8"?>
<!--
  param.xsl — silkpage build parameters for the cleanup site.
  Override any param by passing -Dparam.name=value to the Ant build.
-->
<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    version="1.0">

  <!-- CDN host — all static assets (CSS, JS, images) are served from here -->
  <xsl:param name="cdn"            select="'//cdn.example.org'"/>

  <!-- API endpoint returning report/latest.json -->
  <xsl:param name="api.url"        select="'/api/report'"/>

  <!-- Relative path to the generated scan XML (used at XSL build time) -->
  <xsl:param name="report.xml"     select="'../../../../report/cleanup.xml'"/>

  <!-- Site metadata -->
  <xsl:param name="site.id"        select="'Cleanup Report'"/>
  <xsl:param name="site.author"    select="'singine cleanup'"/>
  <xsl:param name="site.copyright" select="'lutino.io'"/>

</xsl:stylesheet>
