# Singine Docs

This directory holds design notes, operational references, and format-specific assets that explain how Singine is intended to behave.

Current contents are still thin, but this is the right place for:

- architecture notes
- security and privacy model notes
- operational runbooks
- protocol or message-format references

Keep long-form design writing here rather than scattering it through backlog imports.

This directory is also the publication bridge between the runtime model and the
human-facing output formats:

- man pages in `../man/`
- XML Javadoc from the JVM interfaces
- DocBook/spec material generated from the doclet and publication manifest
- SilkPage-rendered HTML
- PDF/man/XML-oriented downstream publication paths

Current notable guide:

- `knowyourai-sparql.md` for the first documented SPARQL query pack against the KnowYourAI RDF corpus through Singine's local bridge
- `auth-and-model-cli.md` for TOTP login bootstrap and the Singine model catalog surface
- `idp-saml-web-sso.md` for the current local/demo SAML 2.0 Web SSO scenario built around humble-idp
- `idp-code-passthrough-architecture.md` for the recommended authorization-code passthrough architecture across Node, Singine core, and XML/SAML services
- `ai-policy-canonify.md` for testing the LDAP-backed policy canonifier and understanding its current boundary
- `ai-access-governance.md` for the governed access gate, persisted approvals, counters, and decision artefacts

Reproducible development workflow:

- Template bootstrap into a new directory:
  `singine template create maven singine-spec-demo`
- Template bootstrap into the current directory:
  `mkdir silkpage-spec-ui && cd silkpage-spec-ui && singine template create npm "Silkpage UI" --dir . --scope my-team`
- Logseq graph discovery:
  `singine logseq graphs --json`
- Logseq to Org:
  `singine logseq export-org --graph kernel --output /tmp/kernel.org`
- Logseq to XML through Emacs and Norman Walsh's `om-to-xml.el`:
  `singine logseq export-xml --graph kernel --org-output /tmp/kernel.org --xml-output /tmp/kernel.xml --om-to-xml-repo /Users/skh/ws/git/codeberg/ndw/org-to-xml`
- Runtime/publication boundary capture:
  `singine server inspect --json && singine snapshot save --json`
- SilkPage-backed publication render:
  `make spec && make spec-html`

Required local configuration/checkouts for the Logseq/XML workflow:

- `om-to-xml.el` checkout at `/Users/skh/ws/git/codeberg/ndw/org-to-xml`
- Emacs-loadable dependencies such as `org-ml`, `dash.el`, and `s.el` available under `/Users/skh/ws/git/github/`
- local Logseq graphs under `~/ws/logseq` or versioned graph material under `~/ws/git/github/sindoc/website/logseq`
- Singine or SilkPage publication commands run from the repo root so `docs/spec-publication.xml` and `docs/xsl/` resolve correctly

Generated publication pipeline:

- `spec-publication.xml` is the publication manifest for Singine and SilkPage specs
- `xsl/spec-doclet-to-docbook.xsl` turns xmldoclet XML into DocBook reference entries
- `xsl/spec-manifest-to-docbook.xsl` turns the manifest into a spec article for HTML publication
- `xsl/spec-manifest-deps.xsl` emits a dependency map for manual pages
- `make spec` generates XML artifacts under `docs/target/spec/`
- `make spec-html` renders the generated article through the SilkPage `spec` theme

Operationally, the easiest way to capture the publication/runtime boundary is:

```bash
singine server inspect --json
singine snapshot save --json
make spec
make spec-html
```

That combination preserves the live server/logseq/git/docker context and the
current generated publication artifacts in one repeatable workflow.
