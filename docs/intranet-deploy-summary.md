# Sindoc Local Intranet Deploy Summary

## Scope

This summary captures the recent work to move the local `sindoc.local`
intranet from an ad hoc static site into a governed local deployment path that
fits the existing Silkpage and Singine infrastructure.

The main goals were:

- publish the generated intranet into a real local deploy root
- align `sindoc.local` with Silkpage's Apache vhost layout
- introduce certificate handling for local HTTPS
- make Firefox trust handling explicit
- keep the whole flow inspectable from Singine itself

## New Singine Command Surface

Two new `singine intranet` commands were added.

### `singine intranet publish`

Purpose:

- sync `target/sindoc.local` into a deploy directory such as
  `~/var/deploy/sindoc.local`
- generate a deploy dashboard under `target/sindoc.local/deploy/`
- emit the matching Silkpage vhost and hosts fragment
- report TLS readiness for `sindoc.local`
- register the deploy page on the intranet index

Implemented in:

- [command.py](/Users/skh/ws/git/github/sindoc/singine/singine/command.py)
- [intranet_deploy.py](/Users/skh/ws/git/github/sindoc/singine/singine/intranet_deploy.py)

### `singine intranet cert-bootstrap`

Purpose:

- create a local root CA
- create a `sindoc.local` server key and certificate
- write them under `~/.config/lutino/ssl`
- produce artifacts suitable for Apache and Firefox testing

Implemented in:

- [command.py](/Users/skh/ws/git/github/sindoc/singine/singine/command.py)
- [intranet_deploy.py](/Users/skh/ws/git/github/sindoc/singine/singine/intranet_deploy.py)

## New Singine Module

### `singine/intranet_deploy.py`

This module centralizes the local deployment logic.

Main responsibilities:

- inspect the presence of:
  - `sindoc.local.crt`
  - `sindoc.local.key`
  - `cacert.pem`
- generate a deploy dashboard as HTML
- generate deployment metadata as JSON
- generate a Firefox `policies.json` snippet for enterprise-root import
- write or refresh the Silkpage vhost and hosts fragment
- sync the intranet output into the real deploy root
- register `/deploy/` on the shared `sindoc.local` index page

It also includes local OpenSSL-based certificate bootstrap logic so the
certificate path is actionable even when no existing local CA material is
present.

## Silkpage Infrastructure Additions

Two first-class Silkpage local infrastructure files were added.

### Apache vhost

Added:

- [sindoc.local.conf](/Users/skh/ws/git/github/sindoc/silkpage/dev/infra/vhosts/sindoc.local.conf)

This defines:

- HTTP to HTTPS redirect for `sindoc.local`
- HTTPS `VirtualHost`
- `DocumentRoot "${HOME}/var/deploy/sindoc.local"`
- certificate, key, and CA paths under `~/.config/lutino/ssl`
- standard TLS and header configuration
- dedicated log paths for `sindoc.local`

### Hosts fragment

Added:

- [hosts.sindoc.local.fragment](/Users/skh/ws/git/github/sindoc/silkpage/dev/infra/hosts.sindoc.local.fragment)

This provides:

- `127.0.0.1 sindoc.local`
- `::1 sindoc.local`

for controlled installation into `/etc/hosts`.

## Certificate Bootstrap Enhancements

The existing Silkpage CA/certificate helper script was extended.

Updated:

- [cacert-setup.sh](/Users/skh/ws/git/github/sindoc/silkpage/dev/infra/ssl/cacert-setup.sh)

Changes include:

- support for optional extra domains through `LUTINO_SSL_DOMAINS`
- support for skipping missing secrets through `LUTINO_SSL_SKIP_MISSING=true`
- recognition of optional `sindoc.local` certificate material
- safer handling of missing 1Password items without forcing failure in every
  case

This means the existing Silkpage certificate workflow can now include
`sindoc.local` without hardcoding that domain into the older lutino-only loop.

## New Generated Deployment Artifacts

The publish flow now generates a proper deployment section under the intranet.

Generated under the site root:

- `target/sindoc.local/deploy/index.html`
- `target/sindoc.local/deploy/deploy.json`
- `target/sindoc.local/deploy/firefox-policies.json`

Generated into the real deploy root:

- `~/var/deploy/sindoc.local/index.html`
- `~/var/deploy/sindoc.local/control/`
- `~/var/deploy/sindoc.local/dotfiles/`
- `~/var/deploy/sindoc.local/sessions/`
- `~/var/deploy/sindoc.local/deploy/`
- `~/var/deploy/sindoc.local/pages.json`

The deploy dashboard is also registered at `/deploy/` on the root intranet
index so it appears alongside `/control/`, `/sessions/`, and `/dotfiles/`.

## Firefox Trust Handling

One of the operational problems was that Firefox would not open the local HTTPS
site cleanly.

The new deployment flow now makes that issue explicit instead of leaving it
implicit.

The deploy report includes:

- the exact certificate paths
- a readiness signal showing whether certificate, key, and CA are present
- a Firefox policy JSON snippet
- guidance for:
  - `security.enterprise_roots.enabled=true`
  - manual CA import into Firefox Authorities

This narrows the debugging surface:

- if routing fails, look at hosts/vhost install
- if TLS fails, look at the local certificate files
- if only Firefox fails, look at trust import behavior

## Documentation Updates

Added:

- [intranet-deploy.md](/Users/skh/ws/git/github/sindoc/singine/docs/intranet-deploy.md)

Updated:

- [README.md](/Users/skh/ws/git/github/sindoc/singine/docs/README.md)
- [singine-intranet.1](/Users/skh/ws/git/github/sindoc/singine/man/singine-intranet.1)
- [singine.1](/Users/skh/ws/git/github/sindoc/singine/man/singine.1)
- [singine-man.1](/Users/skh/ws/git/github/sindoc/singine/man/singine-man.1)

These updates document:

- the new publish command
- the new certificate bootstrap command
- the generated artifacts
- the local Apache and Firefox trust workflow

## Test Coverage

Added:

- [test_intranet_publish.py](/Users/skh/ws/git/github/sindoc/singine/py/tests/test_intranet_publish.py)

The tests cover:

- deploy bundle generation
- Silkpage artifact generation
- deploy sync behavior
- no-sync behavior
- local certificate bootstrap behavior

Related test suites were also re-run to confirm the new deploy path did not
break the existing intranet surfaces:

- [test_control_center.py](/Users/skh/ws/git/github/sindoc/singine/py/tests/test_control_center.py)
- [test_ai_session_dashboard.py](/Users/skh/ws/git/github/sindoc/singine/py/tests/test_ai_session_dashboard.py)
- [test_dotfiles_commands.py](/Users/skh/ws/git/github/sindoc/singine/py/tests/test_dotfiles_commands.py)

## Real Machine State After Execution

The following actions were executed against the real local machine:

- local CA and `sindoc.local` certificate created under
  `~/.config/lutino/ssl`
- intranet published into:
  - `/Users/skh/var/deploy/sindoc.local`
- deploy dashboard written into:
  - `/Users/skh/ws/git/github/sindoc/singine/target/sindoc.local/deploy/`

At the time of the last run, certificate readiness became `true` because:

- `~/.config/lutino/ssl/sindoc.local.crt` existed
- `~/.config/lutino/ssl/sindoc.local.key` existed
- `~/.config/lutino/ssl/cacert.pem` existed

## Remaining Manual System Step

The only part not completed automatically was the system-level install that
needs `sudo`.

Still required on the host:

```bash
sudo sh -c 'cat /Users/skh/ws/git/github/sindoc/silkpage/dev/infra/hosts.sindoc.local.fragment >> /etc/hosts'
sudo cp /Users/skh/ws/git/github/sindoc/silkpage/dev/infra/vhosts/sindoc.local.conf /etc/apache2/other/
sudo apachectl graceful
```

If Firefox still refuses the site after that:

1. open `about:config`
2. set `security.enterprise_roots.enabled` to `true`
3. if needed, import `~/.config/lutino/ssl/cacert.pem` into Firefox

## Net Effect

The intranet is no longer just a generated folder served by a temporary local
HTTP process.

It now has:

- a governed deploy root
- a Silkpage-compatible Apache vhost
- a dedicated local certificate path
- Firefox-aware trust instructions
- a persistent deploy dashboard registered on the intranet homepage
- test coverage for the full local deployment workflow
