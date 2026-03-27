# IdP SAML Web SSO

This guide documents the current bounded SAML 2.0 Web SSO scenario for Singine.

It is intentionally a local/demo profile:

- the IdP publishes SAML metadata
- the IdP exposes a browser login endpoint
- a local demo service provider receives a POSTed `SAMLResponse`
- the demo SP parses the assertion and displays the authenticated identity

Current limitation:

- assertions are not XML-signed yet
- the demo SP does not verify XML signatures
- this is suitable for local validation and operator demos, not production federation

## Components

- `humble-idp/server/src/routes/saml.ts` implements the IdP metadata, login, and demo SP endpoints
- `singine idp saml metadata` fetches the IdP metadata
- `singine idp saml sp-list` lists configured SAML service providers
- `singine idp saml login-url --sp demo-sp` prints the login URL for the local demo service

## Configured demo service provider

The current local demo SP is defined in:

- `~/ws/today/X0-DigitalIdentity/humble-idp/config/clients.properties`

Relevant properties:

```properties
saml.demo-sp.name=Demo SAML Service Provider
saml.demo-sp.entity_id=urn:singine:sp:demo
saml.demo-sp.acs_url=http://127.0.0.1:3000/demo-sp/acs
saml.demo-sp.audience=urn:singine:sp:demo
```

## End-to-end scenario

1. Start the humble IdP server:

```bash
cd ~/ws/today/X0-DigitalIdentity/humble-idp/server
npm install
npm run dev
```

2. Confirm the IdP is up:

```bash
curl -s http://127.0.0.1:3000/health
```

3. Inspect SAML metadata from Singine:

```bash
cd ~/ws/git/github/sindoc/singine
python3 -m singine.command idp --idp-url http://127.0.0.1:3000 saml metadata
python3 -m singine.command idp --idp-url http://127.0.0.1:3000 saml sp-list
python3 -m singine.command idp --idp-url http://127.0.0.1:3000 saml login-url --sp demo-sp
```

4. Open the demo service provider in a browser:

```text
http://127.0.0.1:3000/demo-sp
```

5. Click `Sign in with Singine IdP`, log in with a configured user, and allow the browser to POST the response back to:

```text
http://127.0.0.1:3000/demo-sp/acs
```

6. The demo SP shows:

- `name_id`
- `issuer`
- `audience`
- `RelayState`
- extracted attributes such as `email`, `urn`, and `username`

## What this proves

This scenario proves that your self-hosted IdP can:

- publish SAML IdP metadata
- act as a SAML login authority for a configured service provider
- issue a standards-shaped browser POST response
- hand authenticated identity claims to a service provider endpoint

## Next steps toward a production-grade flow

To use this against third-party or stricter service providers, the next required steps are:

1. sign assertions and metadata with XML DSig
2. support SP-provided metadata import instead of only local property configuration
3. validate `AuthnRequest` fields and preserve `InResponseTo`
4. implement logout/profile choices if the target SP requires them
5. support encrypted assertions where required
