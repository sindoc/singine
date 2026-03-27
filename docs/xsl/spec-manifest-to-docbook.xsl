<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:spec="https://markupware.com/ns/spec"
                xmlns:doclet="https://saxonica.com/ns/doclet"
                version="1.0">

  <xsl:output method="xml" indent="yes" encoding="UTF-8"/>
  <xsl:strip-space elements="*"/>

  <xsl:param name="doclet.path" select="/spec:publication/@doclet"/>

  <xsl:template match="/spec:publication">
    <article id="{@xml:id}">
      <title><xsl:value-of select="@title"/></title>
      <subtitle>Architecture, command topology, and publication metadata</subtitle>
      <articleinfo>
        <releaseinfo role="edition"><xsl:value-of select="@edition"/></releaseinfo>
        <author>
          <orgname><xsl:value-of select="@owner"/></orgname>
        </author>
      </articleinfo>
      <abstract>
        <para><xsl:value-of select="normalize-space(spec:abstract)"/></para>
      </abstract>

      <section xml:id="architecture-overview">
        <title>Architecture Overview</title>
        <xsl:for-each select="spec:project">
          <section id="{concat('project-', @name)}">
            <title><xsl:value-of select="@name"/></title>
            <para><xsl:value-of select="normalize-space(spec:description)"/></para>
            <xsl:if test="spec:stack/spec:technology">
              <itemizedlist>
                <xsl:for-each select="spec:stack/spec:technology">
                  <listitem><para><xsl:value-of select="."/></para></listitem>
                </xsl:for-each>
              </itemizedlist>
            </xsl:if>
          </section>
        </xsl:for-each>
      </section>

      <section xml:id="publication-feeds">
        <title>Publication Feeds</title>
        <itemizedlist>
          <xsl:for-each select="spec:publication-feeds/spec:feed">
            <listitem>
              <para>
                <literal><xsl:value-of select="@type"/></literal>
                <xsl:text> </xsl:text>
                <ulink url="{@href}"><xsl:value-of select="@href"/></ulink>
              </para>
            </listitem>
          </xsl:for-each>
        </itemizedlist>
      </section>

      <section xml:id="jvm-surface">
        <title>JVM Surface</title>
        <para>
          <xsl:text>Packages published by xmldoclet: </xsl:text>
          <xsl:value-of select="count(document($doclet.path)/doclet:doclet/doclet:package)"/>
          <xsl:text>; types: </xsl:text>
          <xsl:value-of select="count(document($doclet.path)/doclet:doclet/doclet:interface | document($doclet.path)/doclet:doclet/doclet:class)"/>
          <xsl:text>.</xsl:text>
        </para>
        <itemizedlist>
          <xsl:for-each select="document($doclet.path)/doclet:doclet/doclet:package">
            <listitem><para><literal><xsl:value-of select="@name"/></literal></para></listitem>
          </xsl:for-each>
        </itemizedlist>
      </section>

      <section xml:id="manpage-topology">
        <title>Manpage Topology</title>
        <table frame="all">
          <title>Singine command pages and dependencies</title>
          <tgroup cols="3">
            <thead>
              <row>
                <entry>Manpage</entry>
                <entry>Purpose</entry>
                <entry>See Also</entry>
              </row>
            </thead>
            <tbody>
              <xsl:for-each select="spec:manpages/spec:page">
                <row>
                  <entry><literal><xsl:value-of select="@name"/></literal></entry>
                  <entry><xsl:value-of select="@purpose"/></entry>
                  <entry>
                    <xsl:for-each select="spec:see-also">
                      <literal><xsl:value-of select="."/></literal>
                      <xsl:if test="position() != last()">
                        <xsl:text>, </xsl:text>
                      </xsl:if>
                    </xsl:for-each>
                  </entry>
                </row>
              </xsl:for-each>
            </tbody>
          </tgroup>
        </table>
      </section>
    </article>
  </xsl:template>
</xsl:stylesheet>
