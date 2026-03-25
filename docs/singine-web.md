# singine web — Web Asset Management, Security, and Deployment

This document describes the full `singine web` command surface: four
command families that together cover the complete lifecycle of a web
property from source to live server.

## Command Families

| Family | Purpose |
|---|---|
| `singine www` | Deploy pipeline: git → build → Dropbox → rsync/scp |
| `singine vww` | Read-only validation: TLS, HTTP headers, asset audit |
| `singine wingine` | Build engine: compile/render the site from source |
| `singine wsec` | Security: TLS certificates, SSH deploy keys, IDP tokens |

Registered sites: `markupware.com`, `lutino.io`.

---

## Architecture

```
Source (git)
    │
    │  singine www pull
    ▼
Local working copy
    │
    │  singine wingine build
    ▼
Built output (html/ or target/webapp)
    │
    ├─── singine www sync --method dropbox
    │         → ~/Dropbox/www/<site>/        (backup / staging copy)
    │
    └─── singine www sync --method rsync
              → deploy@<host>:/var/www/...   (live server via SSH key)

Security surface
    │
    ├─── singine wsec keys   — ed25519 deploy key (singine IDP trust store)
    ├─── singine wsec cert   — TLS certificate check / renewal
    ├─── singine wsec token  — short-lived JWT deploy token (HS256, TTL 3600s)
    └─── singine vww audit   — read-only full security report
```

### IDP trust chain

```
singine-root-ca  (singine.jks / singine.sec.trust)
  └── singine-deploy-<site>  (ed25519, urn:singine:deploy:<site>)
        └── JWT deploy token  (HS256, iss: urn:singine:idp, TTL 3600s)
```

---

## singine www

Manages the full deploy pipeline for a registered site.

### Subcommands

#### `singine www deploy`

Full pipeline in one command:

```
git pull → singine wingine build → Dropbox stage → rsync/scp → remote
```

```
singine www deploy --site markupware.com
singine www deploy --site lutino.io --method rsync
singine www deploy --site markupware.com --dry-run
singine www deploy --site markupware.com --skip-build --skip-dropbox
singine www deploy --site lutino.io --method scp
singine www deploy --site markupware.com --json
```

Options:

| Flag | Default | Description |
|---|---|---|
| `--site` | required | `markupware.com` or `lutino.io` |
| `--method` | `rsync` | `rsync` · `scp` · `dropbox` · `all` |
| `--skip-git` | false | Skip `git pull` |
| `--skip-build` | false | Skip `wingine build` |
| `--skip-dropbox` | false | Skip Dropbox staging |
| `--dry-run` | false | Print commands, make no changes |
| `--json` | false | Machine-readable output |

#### `singine www sync`

Sync via a single specified method without the full pipeline:

```
singine www sync --site markupware.com --method rsync
singine www sync --site markupware.com --method dropbox
singine www sync --site markupware.com --method git
singine www sync --site markupware.com --method all
```

Methods:

| Method | Action |
|---|---|
| `git` | `git pull` on local source repo |
| `dropbox` | rsync built output → `~/Dropbox/www/<site>/` |
| `rsync` | rsync built output → remote server via SSH key |
| `scp` | scp built output → remote server via SSH key |
| `all` | git + dropbox + rsync |

#### `singine www status`

Show current deployment state: recent git log, remote SSH reachability,
local html path, remote path, Dropbox path.

```
singine www status --site markupware.com
singine www status --site lutino.io --json
```

#### `singine www diff`

Show `git status --short` for the local source repo — files changed
since the last commit or last deploy.

```
singine www diff --site markupware.com
```

#### `singine www pull`

`git pull` only, no build or sync.

```
singine www pull --site markupware.com
singine www pull --site markupware.com --dry-run
```

---

## singine vww

Read-only validation and audit. Never modifies anything.

### Subcommands

#### `singine vww cert`

Check TLS certificate for the site: expiry, SAN coverage, issuer.
Delegates to `singine wsec cert` (read path only).

```
singine vww cert --site markupware.com
singine vww cert --site lutino.io --json
```

Example output for markupware.com (current state):

```
[wsec] cert check — markupware.com
  ✗ markupware.com
  subject  : yesplay-online.com     ← wrong cert — vhost misconfiguration
  issuer   : Let's Encrypt
  expires  : 2026-05-21 (62 days)
  SANs     : www.yesplay-online.com, yesplay-online.com
  ⚠ SAN MISMATCH: missing markupware.com www.markupware.com
                          silkpage.markupware.com docbookit.markupware.com
  ⚠ FIX: singine wsec cert --site markupware.com --fix-san
```

#### `singine vww scan`

HTTP security scan: HTTPS redirect, security response headers, server
header exposure.

```
singine vww scan --site lutino.io
singine vww scan --site markupware.com --json
```

Checks performed:

| Check | Pass condition |
|---|---|
| HTTPS redirect | HTTP 301/302 → `https://` |
| `Strict-Transport-Security` | header present |
| `Content-Security-Policy` | header present |
| `X-Content-Type-Options` | header present |
| `X-Frame-Options` | header present |
| `Referrer-Policy` | header present |
| `Permissions-Policy` | header present |
| Server header | not exposed |

#### `singine vww assets`

List all tracked web assets (HTML, CSS, JS, images, XML, RDF, fonts) in
the local build output. Groups by type with counts.

```
singine vww assets --site markupware.com
singine vww assets --site markupware.com --json
```

#### `singine vww check`

Quick health check. Without `--all`: cert only. With `--all`: cert +
security scan + asset inventory.

```
singine vww check --site markupware.com
singine vww check --site lutino.io --all
singine vww check --site markupware.com --all --json
```

#### `singine vww audit`

Full audit report combining cert, security scan, asset inventory, SSH key
status, and recent git log. Summarises all alerts.

```
singine vww audit --site markupware.com
singine vww audit --site lutino.io --json
```

---

## singine wingine

Build engine — invokes each site's native build system.

| Site | Backend | Command invoked |
|---|---|---|
| `markupware.com` | `python-cortex` | `python3 cortex/build.py --output html/ [--clean]` |
| `lutino.io` | `maven-war` | `mvn package -DskipTests` |

### Subcommands

#### `singine wingine build`

Build the site from source.

```
singine wingine build --site markupware.com
singine wingine build --site markupware.com --clean
singine wingine build --site lutino.io
singine wingine build --site markupware.com --dry-run
singine wingine build --site markupware.com --json
```

`--clean` passes `--clean` to the cortex pipeline (full rebuild, no
incremental). Ignored for Maven builds (use `mvn clean package` directly).

#### `singine wingine serve`

Serve the built output locally via Python's built-in HTTP server.

```
singine wingine serve --site markupware.com
singine wingine serve --site markupware.com --port 9000
singine wingine serve --site lutino.io --port 8081
```

Default ports: `markupware.com` → 8080, `lutino.io` → 8081.

#### `singine wingine status`

Show build status: output directory existence, file count.

```
singine wingine status --site markupware.com
singine wingine status --site lutino.io --json
```

---

## singine wsec

Web security operations: TLS certificate management, SSH deploy keys,
and IDP deploy tokens.

### Subcommands

#### `singine wsec cert`

Inspect or renew the TLS certificate for a site.

**Check (default):**

```
singine wsec cert --site markupware.com
singine wsec cert --site lutino.io --json
```

**Renew with corrected SANs:**

```
# Dry run first
singine wsec cert --site markupware.com --fix-san --dry-run

# Certbot (Let's Encrypt) — requires server access
singine wsec cert --site markupware.com --fix-san --method certbot

# acme.sh
singine wsec cert --site markupware.com --renew --method acme.sh

# Manual — prints required SANs, user handles renewal
singine wsec cert --site markupware.com --renew --method manual
```

Required SANs per site:

| Site | Required SANs |
|---|---|
| `markupware.com` | `markupware.com` · `www.markupware.com` · `silkpage.markupware.com` · `docbookit.markupware.com` |
| `lutino.io` | `lutino.io` · `www.lutino.io` · `app.lutino.io` |

#### `singine wsec keys`

Manage SSH ed25519 deploy keys. Keys are stored in `~/.singine/keys/`
and registered in the singine IDP trust store (singine.jks).

**List:**

```
singine wsec keys --site markupware.com
singine wsec keys --site lutino.io --json
```

**Generate new key:**

```
singine wsec keys --site markupware.com --add
singine wsec keys --site markupware.com --add --dry-run
```

Generates `~/.singine/keys/<site>_deploy_ed25519` and registers it as
`urn:singine:deploy:<site>` in the singine IDP trust store. Prints the
public key for manual addition to the server's `authorized_keys`.

**Rotate (archive old, generate new):**

```
singine wsec keys --site markupware.com --rotate
```

Archives the current key as `<name>.<timestamp>.retired`, then generates
a new key.

Key paths:

| Site | Private key | Public key |
|---|---|---|
| `markupware.com` | `~/.singine/keys/markupware_com_deploy_ed25519` | `…pub` |
| `lutino.io` | `~/.singine/keys/lutino_io_deploy_ed25519` | `…pub` |

#### `singine wsec token`

Mint a short-lived JWT deploy token (HS256) for a site via the singine IDP.

```
singine wsec token --site markupware.com
singine wsec token --site lutino.io --ttl 7200
singine wsec token --site markupware.com --dry-run
singine wsec token --site markupware.com --json
```

Token claims:

```json
{
  "sub": "urn:singine:deploy:markupware.com",
  "site": "markupware.com",
  "role": "deploy",
  "iss": "urn:singine:idp",
  "iat": 1742555700,
  "exp": 1742559300
}
```

Secret source: `SINGINE_DEPLOY_SECRET` environment variable.
Default (insecure, dev only): `singine-deploy-<site>-changeme`.

#### `singine wsec status`

Full security status combining cert check and key inventory.

```
singine wsec status --site markupware.com
singine wsec status --site lutino.io --json
```

---

## Site Registry

Both sites are registered in `singine/www.py` (`SITE_REGISTRY`) and
`singine/wingine.py` (`WINGINE_BACKENDS`).

### markupware.com

| Property | Value |
|---|---|
| Local source | `~/ws/git/markupware.com/` |
| Built output | `~/ws/git/markupware.com/html/` |
| Build backend | `python-cortex` (XML → HTML via xsltproc + DocBook XSL) |
| Remote host | `markupware.com` |
| Remote user | `deploy` |
| Remote path | `/var/www/markupware.com/html` |
| Dropbox path | `~/Dropbox/www/markupware.com/` |
| SSH key | `~/.singine/keys/markupware_com_deploy_ed25519` |
| IDP URN | `urn:singine:deploy:markupware.com` |
| TLS status | ⚠ wrong cert (yesplay-online.com) — run `singine wsec cert --fix-san` |

### lutino.io

| Property | Value |
|---|---|
| Local source | `~/ws/git/lutino.io/lutino/` |
| Built output | `~/ws/git/lutino.io/lutino/target/lutino_webapp` |
| Build backend | `maven-war` (`mvn package -DskipTests`) |
| Remote host | `lutino.io` |
| Remote user | `deploy` |
| Remote path | `/var/www/lutino.io/webapp` |
| Dropbox path | `~/Dropbox/www/lutino.io/` |
| SSH key | `~/.singine/keys/lutino_io_deploy_ed25519` |
| IDP URN | `urn:singine:deploy:lutino.io` |

---

## Common Workflows

### First-time setup for a site

```bash
# 1. Generate deploy key and register in IDP
singine wsec keys --site markupware.com --add

# 2. Add the printed public key to the server
#    ssh root@markupware.com "cat >> ~/.ssh/authorized_keys" < ~/.singine/keys/markupware_com_deploy_ed25519.pub

# 3. Verify connectivity
singine www status --site markupware.com

# 4. Build and deploy
singine www deploy --site markupware.com --dry-run
singine www deploy --site markupware.com
```

### Fix TLS certificate (markupware.com)

```bash
# Diagnose
singine vww cert --site markupware.com

# Renew — run on the server where certbot has web root access
singine wsec cert --site markupware.com --fix-san --method certbot --dry-run
singine wsec cert --site markupware.com --fix-san --method certbot

# Verify after renewal
singine vww cert --site markupware.com
```

### Regular deploy

```bash
# Check what changed
singine www diff --site lutino.io

# Full deploy with staging backup
singine www deploy --site lutino.io

# Or step by step
singine www pull    --site lutino.io
singine wingine build --site lutino.io
singine www sync   --site lutino.io --method dropbox
singine www sync   --site lutino.io --method rsync
```

### Audit before deploy

```bash
singine vww audit --site markupware.com
singine wingine status --site markupware.com
singine wsec status --site markupware.com
```

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `SINGINE_DEPLOY_SECRET` | HS256 secret for JWT deploy tokens |
| `SINGINE_DOMAIN_DB` | Path to singine domain event log SQLite DB (default: `/tmp/humble-idp.db`) |
| `SINGINE_KS_PASS` | singine.jks keystore password (default: `singine-changeit`) |

---

## Source Modules

| Module | Path |
|---|---|
| `singine.www` | `singine/www.py` |
| `singine.vww` | `singine/vww.py` |
| `singine.wingine` | `singine/wingine.py` |
| `singine.wsec` | `singine/wsec.py` |
| CLI registration | `singine/command.py` → `build_parser()` |

---

## See Also

- `singine transfer` — lower-level rsync, scp, SSH, SFTP primitives
- `singine wsec` / `singine.sec.trust` — JKS trust store and SSH key management
- `singine auth` / `singine.auth.token` — JWT signing and verification (RS256/HS256)
- `singine domain` — event log and governed transactions (deploy events recorded here)
- `singine edge` — Collibra edge stack lifecycle (separate from public web assets)
- `man singine-web(1)` — condensed man page reference
