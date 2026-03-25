# Intranet Deploy

`singine intranet publish` turns the generated `target/sindoc.local` intranet
into a Silkpage-governed local site:

- syncs the generated intranet into a deploy root such as `~/var/deploy/sindoc.local`
- writes a deploy dashboard under `target/sindoc.local/deploy/`
- emits the matching Silkpage Apache vhost and hosts fragment
- checks whether the expected TLS material for `sindoc.local` exists
- writes a Firefox `policies.json` snippet for importing enterprise roots

If the TLS material does not exist yet, bootstrap it first:

```bash
python3 -m singine.command intranet cert-bootstrap \
  --ssl-dir /Users/skh/.config/lutino/ssl \
  --json
```

Example:

```bash
python3 -m singine.command intranet publish \
  --site-root /Users/skh/ws/git/github/sindoc/singine/target/sindoc.local \
  --deploy-root /Users/skh/var/deploy/sindoc.local \
  --silkpage-root /Users/skh/ws/git/github/sindoc/silkpage \
  --json
```

This writes:

- `target/sindoc.local/deploy/index.html`
- `target/sindoc.local/deploy/deploy.json`
- `target/sindoc.local/deploy/firefox-policies.json`
- `silkpage/dev/infra/vhosts/sindoc.local.conf`
- `silkpage/dev/infra/hosts.sindoc.local.fragment`

## Firefox and local certificates

If Firefox still refuses `https://sindoc.local/`, the problem is usually trust,
not routing.

Expected local TLS files:

- `~/.config/lutino/ssl/sindoc.local.crt`
- `~/.config/lutino/ssl/sindoc.local.key`
- `~/.config/lutino/ssl/cacert.pem` or the path referenced by `~/.config/lutino/ssl/.cacert_path`

Typical local fix:

1. Generate or fetch the local CA and the `sindoc.local` server certificate.
2. Install the CA into the system trust store.
3. In Firefox, either set `security.enterprise_roots.enabled=true` in `about:config`, or import the CA into Firefox Authorities.

The generated deploy dashboard records the exact paths and commands so the setup
stays inspectable from `sindoc.local` itself.
