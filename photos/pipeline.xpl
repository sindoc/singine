<?xml version="1.0" encoding="UTF-8"?>
<!--
  photos/pipeline.xpl — Google Photos ↔ Apple Photos transfer pipeline
  ──────────────────────────────────────────────────────────────────────
  XProc 3.0 pipeline.

  This is the top-level XPL (XProc Pipeline Language) script.
  It uses XProc's inclusion mechanism to load the dependency graph and
  compliance documents, resolves batch dependencies, and routes each
  batch to the appropriate processing step.

  How inclusion works
  ───────────────────
  XProc 3.0 does not use xi:include directly for step inclusion;
  instead, sub-pipelines are referenced via p:import and p:document.
  xi:include is used in the XML *data documents* (dependency-graph.xml,
  compliance.xml).  This pipeline loads those documents as p:document
  inputs and passes them through XPath-driven routing steps.

  Entry points
  ────────────
  Run a specific sprint:
    xproc pipeline.xpl --input dependency-graph=dependency-graph.xml \
                       --option sprint-id=s01

  Run all pending batches:
    xproc pipeline.xpl --input dependency-graph=dependency-graph.xml \
                       --option sprint-id=ALL

  Two-entity dialog
  ─────────────────
  Every transfer step is wrapped in a <sg:dialog> envelope (see dialog.xml).
  The pipeline emits one request document per batch and expects one
  response document.  The dialog:request-id attribute ties the pair.

  XPath queries used throughout
  ──────────────────────────────
  Find pending batches for a sprint:
    $graph//batch[@sprint=$sprint-id][@status='pending']

  Find batches blocked by incomplete dependencies:
    $graph//batch[some $dep in tokenize(@depends-on,' ') satisfies
                  $graph//batch[@id=$dep][@status != 'done']]

  Find high-risk countries in compliance:
    $compliance//country[@risk=('high','prohibited')]/@code
-->
<p:declare-step
    xmlns:p="http://www.w3.org/ns/xproc"
    xmlns:sg="https://singine.local/photos/1.0"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:cx="http://xmlcalabash.com/ns/extensions"
    version="3.0"
    name="photos-transfer-pipeline">


  <!-- ══════════════════════════════════════════════════
       §1  PORTS
       ══════════════════════════════════════════════════ -->

  <!--
    Primary input: the dependency graph (dependency-graph.xml).
    XPL resolves xi:include at load time, so compliance.xml is
    already merged into this document when it arrives here.
  -->
  <p:input port="dependency-graph" primary="true"/>

  <!--
    Results port: emits one XML document per processed batch
    containing the dialog response (see §5 DIALOG).
  -->
  <p:output port="results" primary="true" sequence="true"/>


  <!-- ══════════════════════════════════════════════════
       §2  OPTIONS
       ══════════════════════════════════════════════════ -->

  <!-- Sprint to process.  "ALL" processes every pending batch. -->
  <p:option name="sprint-id"    as="xs:string" required="true"/>

  <!-- Dry-run: log actions but do not call external APIs. -->
  <p:option name="dry-run"      as="xs:boolean" select="false()"/>

  <!-- Maximum parallel transfers within a batch. -->
  <p:option name="parallelism"  as="xs:integer" select="4"/>

  <!-- Output directory for batch reports. -->
  <p:option name="report-dir"   as="xs:string"  select="'batches/'"/>

  <!-- Compliance quarantine directory. -->
  <p:option name="quarantine-dir" as="xs:string" select="'batches/quarantine/'"/>


  <!-- ══════════════════════════════════════════════════
       §3  IMPORTS (sub-pipelines)
       Each sub-pipeline corresponds to one processing phase.
       ══════════════════════════════════════════════════ -->

  <p:import href="steps/resolve-dependencies.xpl"/>
  <p:import href="steps/compliance-screen.xpl"/>
  <p:import href="steps/google-export.xpl"/>
  <p:import href="steps/compress.xpl"/>
  <p:import href="steps/apple-import.xpl"/>
  <p:import href="steps/validate.xpl"/>
  <p:import href="steps/reconcile.xpl"/>
  <p:import href="steps/emit-dialog.xpl"/>


  <!-- ══════════════════════════════════════════════════
       §4  STEP 1: LOAD AND VALIDATE DEPENDENCY GRAPH
       ══════════════════════════════════════════════════ -->

  <!--
    Load the dependency graph document.  xi:include has already merged
    compliance.xml into the graph; no further inclusion needed here.
    Validate against the schema to catch malformed compliance data early.
  -->
  <p:load name="load-graph" href="dependency-graph.xml">
    <p:with-option name="dtd-validate" select="false()"/>
  </p:load>

  <!--
    Validate the merged document against the XML Schema.
    Validation failures are fatal; the pipeline will not proceed
    with an invalid compliance or graph document.
  -->
  <p:validate-with-xml-schema name="validate-graph"
                               assert-valid="true">
    <p:with-input port="source"  pipe="result@load-graph"/>
    <p:with-input port="schema">
      <p:document href="schema/photo-transfer.xsd"/>
    </p:with-input>
  </p:validate-with-xml-schema>


  <!-- ══════════════════════════════════════════════════
       §5  STEP 2: RESOLVE BATCH DEPENDENCIES
       ══════════════════════════════════════════════════ -->

  <!--
    The dependency resolver identifies which batches are eligible
    to run in the selected sprint (status=pending, all depends-on
    batches are done, no compliance hold).

    XPath logic (executed inside resolve-dependencies.xpl):
      $graph//batch
        [@status = 'pending']
        [not(@sprint) or @sprint = $sprint-id or $sprint-id = 'ALL']
        [every $dep in tokenize(@depends-on, '\s+') satisfies
           $graph//batch[@id = $dep]/@status = 'done']
  -->
  <sg:resolve-dependencies name="resolve-deps">
    <p:with-input port="graph"  pipe="result@validate-graph"/>
    <p:with-option name="sprint-id" select="$sprint-id"/>
  </sg:resolve-dependencies>


  <!-- ══════════════════════════════════════════════════
       §6  STEP 3: COMPLIANCE SCREENING
       ══════════════════════════════════════════════════ -->

  <!--
    For each eligible batch, screen photos for GPS provenance
    against the compliance rules embedded in the graph.

    XPath inside compliance-screen.xpl:
      for $photo in $batch/photos/photo
      let $code := reverse-geocode($photo/exif/gps)
      let $country := $graph//country[@code = $code]
      return
        if ($country/@risk = 'prohibited')
        then quarantine($photo)
        else if ($country/@risk = 'high')
        then flag-for-review($photo)
        else clear($photo)
  -->
  <sg:compliance-screen name="screen">
    <p:with-input port="eligible-batches" pipe="result@resolve-deps"/>
    <p:with-input port="compliance"       pipe="result@validate-graph"/>
    <p:with-option name="quarantine-dir"  select="$quarantine-dir"/>
    <p:with-option name="dry-run"         select="$dry-run"/>
  </sg:compliance-screen>


  <!-- ══════════════════════════════════════════════════
       §7  STEP 4: EXPORT FROM GOOGLE PHOTOS
       ══════════════════════════════════════════════════ -->

  <!--
    Calls the Google Photos Library API to export originals.
    Produces a local staging directory of raw photo files.
    Skips photos quarantined in step 3.
  -->
  <sg:google-export name="export">
    <p:with-input port="cleared-batches" pipe="cleared@screen"/>
    <p:with-option name="dry-run"        select="$dry-run"/>
    <p:with-option name="parallelism"    select="$parallelism"/>
  </sg:google-export>


  <!-- ══════════════════════════════════════════════════
       §8  STEP 5: COMPRESSION
       ══════════════════════════════════════════════════ -->

  <!--
    Re-encodes photos according to the compression-params declared
    in each batch.  Supported codecs: lossless-heic, lossy-avif-qN, none.

    Compression is the highest-volume step.  Parallelism applies here.
  -->
  <sg:compress name="compress">
    <p:with-input port="exported-batches" pipe="result@export"/>
    <p:with-option name="dry-run"         select="$dry-run"/>
    <p:with-option name="parallelism"     select="$parallelism"/>
  </sg:compress>


  <!-- ══════════════════════════════════════════════════
       §9  STEP 6: IMPORT INTO APPLE PHOTOS
       ══════════════════════════════════════════════════ -->

  <!--
    Calls osxphotos (macOS) to import compressed photos into
    Apple Photos, preserving album structure from the Google manifest.
  -->
  <sg:apple-import name="import">
    <p:with-input port="compressed-batches" pipe="result@compress"/>
    <p:with-option name="dry-run"           select="$dry-run"/>
  </sg:apple-import>


  <!-- ══════════════════════════════════════════════════
       §10  STEP 7: VALIDATION
       ══════════════════════════════════════════════════ -->

  <!--
    SHA-256 hash verification of every imported photo.
    Produces a validation report.
  -->
  <sg:validate name="validate">
    <p:with-input port="imported-batches" pipe="result@import"/>
    <p:with-option name="report-dir"      select="$report-dir"/>
  </sg:validate>


  <!-- ══════════════════════════════════════════════════
       §11  STEP 8: EMIT DIALOG ENVELOPE
       Wraps results in the XML request/response dialog format.
       ══════════════════════════════════════════════════ -->

  <!--
    Every processing result is wrapped in the <sg:dialog> envelope
    (see dialog.xml for the schema).  The dialog ties the Google
    entity (requester) to the Apple entity (responder) via
    matching request-id attributes.
  -->
  <sg:emit-dialog name="wrap-dialog">
    <p:with-input port="validation-results" pipe="result@validate"/>
    <p:with-input port="quarantine-report"  pipe="quarantined@screen"/>
  </sg:emit-dialog>

  <!-- Route all dialog documents to the results port -->
  <p:identity>
    <p:with-input port="source" pipe="result@wrap-dialog"/>
  </p:identity>


</p:declare-step>
