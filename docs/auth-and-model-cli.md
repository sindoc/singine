# Auth And Model CLI

This guide defines the current simple command surface for:

- TOTP-based login bootstrap
- data object discovery
- Collibra-bridge metamodel visibility

## TOTP login bootstrap

Create a local profile:

```bash
python3 -m singine.command auth totp init \
  --issuer Singine \
  --account-name you@example.com \
  --provider 1password \
  --state ~/.singine/auth/totp.json
```

Print the provisioning URI:

```bash
python3 -m singine.command auth totp uri --state ~/.singine/auth/totp.json --json
```

Show the current code:

```bash
python3 -m singine.command auth totp code --state ~/.singine/auth/totp.json --json
```

Verify a code:

```bash
python3 -m singine.command auth totp verify --state ~/.singine/auth/totp.json 123456
```

Open a local Singine session gate:

```bash
python3 -m singine.command auth login --state ~/.singine/auth/totp.json --code 123456
```

## Provider notes

- `1Password`: supported through the standard `otpauth://` provisioning URI
- `Google Authenticator`: supported through the standard `otpauth://` provisioning URI
- `Microsoft Authenticator`: planned on the same TOTP profile shape, but not yet validated in this repo

QR rendering is not built into the repo yet. The provisioning URI is the canonical artifact today.

## Model catalog

Use the catalog to see the main Singine object surfaces:

```bash
python3 -m singine.command model catalog
python3 -m singine.command model catalog --json
```

Inspect one object:

```bash
python3 -m singine.command model inspect code-table
python3 -m singine.command model inspect scenario-codes
python3 -m singine.command model inspect "Business Term"
```

The catalog currently groups:

- bootstrappers
- auth operations
- master data
- reference data
- entity families
- Collibra bridge asset types, domain types, and relation types
