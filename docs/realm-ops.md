# Realm Operations

`singine realm` is the simple operator surface for periodic realm checks driven
by Atom XML and cron.

It is designed around these constraints:

- every request is captured as an Atom request feed
- every result is captured as an Atom response feed
- the cron schedule itself is emitted as a documented artifact
- realm, domain, and service are kept together with a stable crosswalk code and
  causality key

## Supported realm model

By default the command assumes these realm names:

- `local.realm`
- `ext.realm`
- `neighbour.realm`
- `dmz.realm`
- `mode1.realm`
- `mode2.realm`

Every domain or subdomain can also be treated as a realm identifier. The
default domain set is:

- `lutino.io`
- `www.markupware.com`
- `app.lutino.io`
- `collibra.lutino.io`

## Supported service families

- `dns`: runs `nslookup` and `whois` when available
- `tls`: runs `openssl s_client` against `domain:443`
- `trust`: reports Singine/Lutino trust-store and keystore paths
- `vault`: reports HashiCorp Vault and Singine vault environment hints

The trust and vault checks are intentionally local and inventory-oriented. They
describe the current workstation/server setup without modifying it.

## Typical workflow

Generate a realm audit:

```bash
singine realm check --json
singine realm read-atom /tmp/singine-realm/realm-check.response.atom --json
```

Generate a cron specification for a periodic audit:

```bash
singine realm cron-write \
  --cron "*/30 * * * *" \
  --realm dmz.realm \
  --domain collibra.lutino.io \
  --service dns \
  --service tls \
  --json
```

That writes:

- `/tmp/singine-realm/realm-cron.request.atom`
- `/tmp/singine-realm/realm-cron.response.atom`
- `/tmp/singine-realm/realm-audit.cron`

Broadcast operational interest to publication and platform targets:

```bash
singine realm broadcast-interest \
  --topic "realm dns trust vault" \
  --json
```

## Cron installation

`singine realm cron-write` does not install into the system crontab. It writes
the cron line into a file so the schedule can be reviewed and versioned first.

Typical operator flow:

```bash
singine realm cron-write --cron "0 * * * *"
cat /tmp/singine-realm/realm-audit.cron
crontab /tmp/singine-realm/realm-audit.cron
```

## XML/Atom contract

The generated Atom feeds carry:

- `singine:xwalkCode`
- `singine:causalityKey`
- realm and service categories
- JSON content payloads per entry

That keeps the realm/domain/service mapping stable for later SPARQL, GraphQL,
or Collibra-side crosswalk work without changing the cron/operator surface.
