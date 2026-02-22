<?xml version="1.0" encoding="UTF-8"?>
<!--
  singine.sch — ISO Schematron rules for the Singine platform
  URN:  urn:singine:schema:sch:1.0
  URL:  https://github.com/sindoc/singine/schema/singine.sch

  These rules encode business constraints that DTD and RelaxNG
  (structural validators) cannot express.  Every rule has an SCH-NNN id.

  Validation pipeline:
    Phase 1: SchematronValidator.java (inline XPath evaluation)
    Phase 2: iso_svrl_for_xslt1.xsl → full SVRL report

  Namespaces used:
    (none — queryBinding=xslt uses XPath 1.0 without prefixes
     for portability with Phase 1 inline evaluator)

  Rules defined here:
    SCH-001  opcode-format       — asset-type/@opcode must be 4 uppercase ASCII letters
    SCH-002  locp-urn            — LOCP form must carry location-urn starting with urn:singine:location:
    SCH-003  policy-terms-count  — p:policy/@terms-active must equal count of satisfied p:term elements
    SCH-004  form-generated-at   — form/@generated-at must be present and non-empty
    SCH-005  kafka-topic-format  — topic/@name must start with "singine."
-->
<schema xmlns="http://purl.oclc.org/dsdl/schematron"
        queryBinding="xslt">

  <title>Singine Platform Schematron Rules v1.0</title>

  <!-- ── SCH-001: opcode must be exactly 4 uppercase ASCII letters ──────── -->
  <pattern id="opcode-format">
    <rule context="asset-type">
      <assert test="string-length(@opcode) = 4">
        SCH-001: asset-type/@opcode must be exactly 4 characters (got '<value-of select="@opcode"/>').
      </assert>
      <assert test="translate(@opcode,
                    'ABCDEFGHIJKLMNOPQRSTUVWXYZ',
                    'XXXXXXXXXXXXXXXXXXXXXXXXXX') = 'XXXX'">
        SCH-001: asset-type/@opcode must be uppercase ASCII letters only (got '<value-of select="@opcode"/>').
      </assert>
    </rule>
  </pattern>

  <!-- ── SCH-002: LOCP form must carry a valid location-urn ───────────── -->
  <pattern id="locp-urn">
    <rule context="form[@opcode='LOCP']">
      <assert test="@location-urn">
        SCH-002: LOCP form must carry @location-urn attribute.
      </assert>
      <assert test="starts-with(@location-urn, 'urn:singine:location:')">
        SCH-002: LOCP @location-urn must start with 'urn:singine:location:' (got '<value-of select="@location-urn"/>').
      </assert>
    </rule>
  </pattern>

  <!-- ── SCH-003: policy terms-active must match satisfied term count ───── -->
  <!--
    Note: Phase 1 XPath evaluator (inline, no functions) may defer this
    if count() is not supported.  Phase 2 SVRL pipeline evaluates it fully.
  -->
  <pattern id="policy-terms-count">
    <rule context="*[local-name()='policy']">
      <assert test="number(@terms-active) = count(*[local-name()='term'][@satisfied='true'])">
        SCH-003: @terms-active (<value-of select="@terms-active"/>)
        must equal count of satisfied terms
        (<value-of select="count(*[local-name()='term'][@satisfied='true'])"/>).
      </assert>
    </rule>
  </pattern>

  <!-- ── SCH-004: form/@generated-at must be present and non-empty ──────── -->
  <pattern id="form-generated-at">
    <rule context="form">
      <assert test="@generated-at and string-length(@generated-at) &gt; 0">
        SCH-004: form/@generated-at must be present and non-empty.
      </assert>
    </rule>
  </pattern>

  <!-- ── SCH-005: kafka topic/@name must start with 'singine.' ─────────── -->
  <pattern id="kafka-topic-format">
    <rule context="topic">
      <assert test="starts-with(@name, 'singine.')">
        SCH-005: topic/@name must start with 'singine.' (got '<value-of select="@name"/>').
      </assert>
    </rule>
  </pattern>

</schema>
