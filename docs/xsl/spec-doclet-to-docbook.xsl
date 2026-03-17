<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:doclet="https://saxonica.com/ns/doclet"
                xmlns:h="http://www.w3.org/1999/xhtml"
                version="1.0">

  <xsl:output method="xml" indent="yes" encoding="UTF-8"/>
  <xsl:strip-space elements="*"/>

  <xsl:param name="project.title" select="'Singine JVM Activity Reference'"/>

  <xsl:template match="/doclet:doclet">
    <reference>
      <title><xsl:value-of select="$project.title"/></title>
      <subtitle>Generated from xmldoclet output</subtitle>
      <abstract>
        <para>
          This reference is generated from Java interfaces and classes published by the
          Singine JVM core. It is designed to serve both HTML specifications and
          DocBook-derived manpage workflows.
        </para>
      </abstract>
      <xsl:apply-templates select="doclet:interface | doclet:class" mode="refentry"/>
    </reference>
  </xsl:template>

  <xsl:template match="doclet:interface | doclet:class" mode="refentry">
    <refentry id="{translate(translate(@fullname, '.', '-'), '$', '-') }">
      <refmeta>
        <refentrytitle><xsl:value-of select="@fullname"/></refentrytitle>
        <manvolnum>3</manvolnum>
        <refmiscinfo class="source">singine-core</refmiscinfo>
        <refmiscinfo class="manual">Singine JVM Reference</refmiscinfo>
      </refmeta>
      <refnamediv>
        <refname><xsl:value-of select="@name"/></refname>
        <refpurpose>
          <xsl:choose>
            <xsl:when test="doclet:purpose/h:body">
              <xsl:value-of select="normalize-space(doclet:purpose/h:body)"/>
            </xsl:when>
            <xsl:otherwise>JVM type published by the Singine core.</xsl:otherwise>
          </xsl:choose>
        </refpurpose>
      </refnamediv>
      <refsynopsisdiv>
        <para>
          <literal><xsl:value-of select="@access"/></literal>
          <xsl:text> </xsl:text>
          <literal><xsl:value-of select="local-name()"/></literal>
          <xsl:text> </xsl:text>
          <literal><xsl:value-of select="@fullname"/></literal>
        </para>
      </refsynopsisdiv>
      <refsect1>
        <title>Description</title>
        <para>
          <xsl:choose>
            <xsl:when test="doclet:description/h:body">
              <xsl:value-of select="normalize-space(doclet:description/h:body)"/>
            </xsl:when>
            <xsl:otherwise>
              No extended description is present in the source Javadoc.
            </xsl:otherwise>
          </xsl:choose>
        </para>
      </refsect1>
      <xsl:if test="doclet:method">
        <refsect1>
          <title>Methods</title>
          <variablelist>
            <xsl:for-each select="doclet:method">
              <varlistentry>
                <term><literal><xsl:value-of select="@name"/></literal></term>
                <listitem>
                  <para>
                    <xsl:choose>
                      <xsl:when test="doclet:purpose/h:body">
                        <xsl:value-of select="normalize-space(doclet:purpose/h:body)"/>
                      </xsl:when>
                      <xsl:otherwise>No method purpose documented.</xsl:otherwise>
                    </xsl:choose>
                  </para>
                  <xsl:if test="doclet:parameter">
                    <para>
                      Parameters:
                      <xsl:for-each select="doclet:parameter">
                        <literal><xsl:value-of select="@name"/></literal>
                        <xsl:if test="position() != last()">
                          <xsl:text>, </xsl:text>
                        </xsl:if>
                      </xsl:for-each>
                    </para>
                  </xsl:if>
                  <xsl:if test="doclet:return/doclet:purpose/h:body">
                    <para>
                      Returns:
                      <xsl:text> </xsl:text>
                      <xsl:value-of select="normalize-space(doclet:return/doclet:purpose/h:body)"/>
                    </para>
                  </xsl:if>
                </listitem>
              </varlistentry>
            </xsl:for-each>
          </variablelist>
        </refsect1>
      </xsl:if>
    </refentry>
  </xsl:template>
</xsl:stylesheet>
