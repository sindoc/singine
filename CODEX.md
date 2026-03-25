# CODEX.md - Singine Repository Boundary

Singine is the secure execution engine, CLI runtime, and documentation shell.

Policy:

1. Keep vendor-specific Collibra implementations in the sibling `collibra/`
   repository.
2. Keep transformation-heavy XML/RDF/XSLT/XPath/SPARQL/SQL/GraphQL logic in the
   sibling `silkpage/` repository when feasible.
3. Use Singine for authn/authz, identity-provider routing, JVM orchestration,
   secure execution, manpage/docbook publication, and thin command hooks.
4. For `singine collibra ...`, prefer dynamic loading from
   `collibra/singine_collibra` via `COLLIBRA_DIR` instead of embedding
   Collibra-aware logic directly here.

Decision rule:

- If removing Collibra would make the code meaningless, it should probably live
  in `collibra/`.
- If the code is about secure execution or runtime plumbing, it belongs here.
- If the code is primarily about transforming payloads or documents, it likely
  belongs in `silkpage/`.
