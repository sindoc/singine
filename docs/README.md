# Singine Docs

This directory holds design notes, operational references, and format-specific assets that explain how Singine is intended to behave.

Current contents are still thin, but this is the right place for:

- architecture notes
- security and privacy model notes
- operational runbooks
- protocol or message-format references

Keep long-form design writing here rather than scattering it through backlog imports.

Current notable guide:

- `knowyourai-sparql.md` for the first documented SPARQL query pack against the KnowYourAI RDF corpus through Singine's local bridge
- `auth-and-model-cli.md` for TOTP login bootstrap and the Singine model catalog surface
- `idp-saml-web-sso.md` for the current local/demo SAML 2.0 Web SSO scenario built around humble-idp
- `idp-code-passthrough-architecture.md` for the recommended authorization-code passthrough architecture across Node, Singine core, and XML/SAML services
- `ai-policy-canonify.md` for testing the LDAP-backed policy canonifier and understanding its current boundary
- `ai-access-governance.md` for the governed access gate, persisted approvals, counters, and decision artefacts

Generated publication pipeline:

- `spec-publication.xml` is the publication manifest for Singine and SilkPage specs
- `xsl/spec-doclet-to-docbook.xsl` turns xmldoclet XML into DocBook reference entries
- `xsl/spec-manifest-to-docbook.xsl` turns the manifest into a spec article for HTML publication
- `xsl/spec-manifest-deps.xsl` emits a dependency map for manual pages
- `make spec` generates XML artifacts under `docs/target/spec/`
- `make spec-html` renders the generated article through the SilkPage `spec` theme
