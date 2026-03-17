# IdP Code Passthrough Architecture

This note defines the practical path for finishing the Singine IdP work
without discarding the code that already exists in this repo.

## Decision

Use a Node.js identity edge as the primary browser-facing IdP surface and keep
Singine's existing Clojure and XML code as the policy, token, and XML/SAML
integration layer behind it.

Preferred implementation order:

1. OpenAuth-style OAuth 2.1 / OIDC authorization-code flow at the edge
2. Singine policy and token issuance behind that edge
3. Existing SAML/XML path extended for signed and encrypted assertions
4. Spring Boot only where transaction orchestration or Java XML stacks are
   materially better than Node
5. Keycloak only if the requirement becomes "run a full external IAM product"
   rather than "finish Singine's own IdP"

## Why this path fits the current repo

The repo already contains:

- a Python CLI that treats the IdP as a thin HTTP service in
  `singine/idp.py`
- a local SAML Web SSO guide in `docs/idp-saml-web-sso.md`
- an in-repo OIDC discovery and JWT implementation in
  `core/src/singine/pos/idp.clj`
- OIDC discovery and token probes in
  `core/src/singine/pos/identity.clj`
- a governed token lifecycle in `core/src/singine/auth/token.clj`
- an activity and taxonomy model in `core/java/singine/activity/*` that
  already treats XML, EDN, SPARQL, GraphQL, Logseq, and Collibra as part of
  one semantic surface

That means the missing piece is not "invent identity from scratch". The
missing piece is a stable authorization-code bridge between browser flows and
the existing Singine identity core.

## Activity taxonomy alignment

The identity layer should not invent a separate classification system for
authorization and federation events.

The existing Java activity model already provides:

- `Taxonomy` for domain, category, and subcategory classification
- `Activity` for canonical, serialisable intent
- `Action` for runtime execution
- `Outcome` for measured results
- `Policy` for governance

That package is already documented as serialisable across XML and EDN and as a
source for SPARQL, GraphQL, Logseq, and Collibra-aligned views.

For the IdP work, treat these as first-class semantic anchors for:

- login
- authorization request handling
- authorization-code issuance
- token exchange
- SAML assertion projection
- metadata publication
- key rotation
- audit and consent outcomes

In practice, each externally visible identity operation should map to:

- a taxonomy node
- an activity template
- a governing policy
- an outcome record

That keeps the IdP aligned with the KnowYourAI and SKOS-oriented semantic
infrastructure already present in Singine instead of becoming a standalone auth
subsystem.

## Architecture

### 1. Identity edge

The Node layer owns:

- `/.well-known/openid-configuration`
- `/authorize`
- `/token`
- `/userinfo`
- `/jwks.json`
- browser session cookies
- PKCE, `state`, nonce, redirect URI validation
- login UI and consent UI when needed

This layer should stay thin. It is the protocol adapter and browser state
manager, not the long-term source of truth for policy.

### 2. Singine identity core

The Clojure layer owns:

- governed token issuance and verification
- subject resolution and internal claims shaping
- policy decisions and scopes
- transaction-safe persistence where needed
- XML and SAML processing hooks
- key material lifecycle if you keep Singine as issuer

This aligns with the current code in
`core/src/singine/pos/idp.clj` and `core/src/singine/auth/token.clj`.

### 3. XML and SAML bridge

The XML-first path remains a first-class concern:

- SAML assertions and metadata stay XML-native
- XML signature and encryption should use a mature XML security stack
- XML catalogs, schema validation, and request/response transforms remain
  separate from OAuth/OIDC browser flow code

The clean boundary is:

- OAuth/OIDC code flow for browser authorization and delegated access
- SAML/XML layer for enterprise federation and signed assertion handling

The semantic source of truth for both should be kept compatible with:

- EDN for internal and Clojure-facing canonical structures
- XML for signed and schema-governed interchange
- SKOS/RDF for taxonomy publication and query
- JSON/YAML for operational configuration exchange
- SQL, SPARQL, GraphQL, `jq`, and `yq` as query and transformation surfaces

That matches the direction already visible in the activity model and the wider
Singine bridge stack.

### 4. Optional transaction service

Use Spring Boot only for the parts that actually need:

- durable relational transactions
- Java XML security libraries
- JPA-based state transitions
- JMS, Camel, or existing Java ecosystem integration

Do not make Spring Boot the browser-facing IdP unless you decide to abandon
the current Node-based IdP shell.

## OpenAuth vs Keycloak

### OpenAuth-style approach

Best fit when you want:

- Singine to remain the product
- protocol correctness without surrendering the core model
- a codebase you can embed and shape
- inversion of control around your own policy and XML logic

Use this when the IdP is part of Singine, not a separate platform bet.

### Keycloak

Best fit when you want:

- a full admin console
- standard federation features immediately
- realm/client/user management from an existing IAM product
- less custom protocol code in your repo

Cost:

- heavier operational model
- harder fit with Singine-specific XML, schema, and governed-token semantics
- higher risk that Singine becomes an adapter around Keycloak instead of the
  system of record

## Recommended passthrough flow

The target flow should be:

1. Browser hits Singine `/authorize`
2. Node edge validates client, redirect URI, PKCE, `state`, and requested scopes
3. Node edge authenticates the operator using the current local mechanism
   or delegated upstream login
4. Node edge calls Singine core for subject resolution and claims policy
5. Singine core issues authorization-code state or a signed exchange artifact
6. Browser is redirected back with `code`
7. Client posts `code` and verifier to `/token`
8. Node edge redeems the code via Singine core
9. Singine core issues access token, ID token, and optional refresh token
10. If the target is SAML, the same authenticated subject can be projected into
    an XML assertion path rather than a JWT-only path

The important design point is that the browser protocol state lives at the
edge, while identity semantics live in Singine core.

## Inversion of control boundary

Define a small internal interface between the Node edge and Singine core.

Suggested operations:

- `begin_authorization`
- `resolve_subject`
- `approve_scopes`
- `issue_authorization_code`
- `redeem_authorization_code`
- `issue_tokens`
- `project_saml_assertion`
- `publish_metadata`

The Node side should depend on this interface, not on storage internals.

Each operation should also carry semantic hooks for:

- taxonomy identifier
- activity identifier
- policy identifier
- content type and MIME mapping when documents or assertions are exchanged
- provenance identifiers for later SPARQL, SQL, GraphQL, or Collibra queries

That keeps these options open:

- current Clojure implementation
- Spring Boot transaction service for selected operations
- future Rust, Go, or C implementation behind the same contract

## Token and key strategy

Near term:

- keep JWT issuance in Singine
- expose JWKS from the edge
- keep RS256 first
- keep the current discovery model compatible with
  `core/src/singine/pos/idp.clj`

Later:

- add key rotation metadata
- add refresh token storage and revocation
- add token introspection only if a real opaque-token use case appears

When tokens or assertions represent access to structured content, preserve
enough metadata to classify downstream resources consistently across XML,
HTML, Markdown, PDF, TeX, CSV, Parquet, SVG, PNG, and related MIME families.
That should plug into the existing bridge and query surfaces rather than
creating auth-specific metadata tables in isolation.

## XML and SAML requirements

For the SAML side, the current demo is not yet production-grade. The next
non-optional steps are:

- XML DSig for metadata and assertions
- encrypted assertions when the SP requires them
- `AuthnRequest` parsing and `InResponseTo` preservation
- SP metadata import
- clock-skew handling and replay protection

If these move quickly, a Java XML security component is justified even if the
browser-facing IdP stays in Node.

## First implementation slices

### Slice 1: normalize the internal contract

Add a protocol-neutral internal service contract for:

- authorization request validation
- code issuance
- code redemption
- token issuance
- SAML projection

Do this before changing more CLI surface.

### Slice 2: add explicit auth-code support to Singine CLI

Extend `singine/idp.py` with helpers for:

- discovery
- authorize URL generation
- token exchange
- userinfo fetch

This should mirror the current `saml metadata`, `saml sp-list`, and
`saml login-url` pattern.

### Slice 3: bind the Node edge to Singine core

The Node edge should call one of:

- Clojure HTTP service endpoints
- a local subprocess wrapper for the existing core
- a narrow Spring Boot service if transaction-heavy persistence is required

Choose HTTP if you want language independence and easier later replacement.

### Slice 4: productionize XML federation

Add:

- XML signing
- XML encryption
- metadata import
- assertion validation tests

This is the point where a Java XML stack becomes compelling.

## What not to do

- Do not mix browser session logic directly into the Clojure token library
- Do not move everything to Keycloak unless you are willing to stop making
  Singine's IdP a distinct product capability
- Do not put XML signature logic into ad hoc handwritten Node code
- Do not let the Python CLI become the protocol engine; it should stay a thin
  operator surface

## Immediate next step

Implement the internal auth-code contract first and make the Node edge call it.
That gives you the passthrough you want while preserving the current SAML/XML
and governed-token direction already visible in the repo.
