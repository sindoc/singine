# Canonify AI Policies

This guide shows how to test the LDAP-backed AI policy canonifier.

Current scope:

- reads LDAP groups from an LDIF file or via `ldapsearch`
- runs external LDAP access through `singine runtime exec-external`
- emits a Collibra-shaped policy pack
- writes JSON, EDN, SQL, CSV, Logseq Markdown, and Org-mode outputs

Current non-scope:

- it does **not** yet change Codex or Claude sandbox permissions
- it does **not** yet intercept directory access prompts
- it does **not** yet count command invocations across agent sessions

Those enforcement and telemetry pieces need a second integration step.

## 1. Fast local test with the fixture

From the repo root:

```bash
python3 bin/singine-canonify-ai-policies \
  --ldap-ldif docs/examples/ldap-ai-groups.ldif \
  --output-dir /tmp/singine-ai-policy-pack
```

Expected result:

- the command prints a JSON summary
- `/tmp/singine-ai-policy-pack/` contains:
  - `policy-pack.json`
  - `policy-pack.edn`
  - `policy-pack.sql`
  - `policy-pack.org`
  - `logseq-policy-pack.md`
  - `communities.csv`
  - `domains.csv`
  - `assets.csv`
  - `relations.csv`
  - `grants.csv`

Inspect the high-level structure:

```bash
jq '.metadata | {pack_id, group_count, grant_count, configured_systems}' /tmp/singine-ai-policy-pack/policy-pack.json
jq '.communities[].name' /tmp/singine-ai-policy-pack/policy-pack.json
jq '.policy_assets[].name' /tmp/singine-ai-policy-pack/policy-pack.json
```

Inspect the SQLite-shaped output:

```bash
sqlite3 /tmp/singine-ai-policy-pack/policy-pack.db < /tmp/singine-ai-policy-pack/policy-pack.sql
sqlite3 /tmp/singine-ai-policy-pack/policy-pack.db 'select count(*) from grants;'
sqlite3 /tmp/singine-ai-policy-pack/policy-pack.db 'select relation_type, count(*) from relations group by relation_type order by relation_type;'
```

Inspect the Logseq/Emacs-friendly projections:

```bash
sed -n '1,120p' /tmp/singine-ai-policy-pack/logseq-policy-pack.md
sed -n '1,120p' /tmp/singine-ai-policy-pack/policy-pack.org
```

## 2. Test with live LDAP through Singine's execution gate

If `ldapsearch` is available and you want the sanctioned runtime wrapper:

```bash
export LDAP_BIND_PASSWORD='your-secret'

python3 bin/singine-canonify-ai-policies \
  --ldap-uri ldap://127.0.0.1:389 \
  --base-dn 'ou=Groups,dc=example,dc=org' \
  --bind-dn 'cn=readonly,dc=example,dc=org' \
  --bind-password-env LDAP_BIND_PASSWORD \
  --output-dir /tmp/singine-ai-policy-pack-live
```

This path uses:

```text
python3 -m singine.command runtime exec-external ldapsearch ...
```

The bind password is written to a temporary file and passed with `ldapsearch -y`
so it is not exposed as a command-line argument.

## 3. Verify the current runtime envelope is captured

The generated JSON pack includes the result of:

```bash
python3 -m singine.command runtime inspect
```

Check it with:

```bash
jq '.metadata.runtime.runtime_capabilities' /tmp/singine-ai-policy-pack/policy-pack.json
```

## 4. What this gives you today

Today the script gives you a canonical source of truth for:

- which LDAP groups imply which canonical roles
- which roles imply which responsibilities
- which responsibilities imply which privileges
- which policies govern which AI systems
- which relations can be loaded into SQLite, Logseq, Org-mode, or later published

That is the reporting and canonification layer.

## 5. What is still needed for your actual goal

If your real goal is:

- no more repeated directory-access approvals for already-approved paths
- a durable hierarchy of allowed commands
- counters for how often commands and activities are invoked
- mapping commands and filesystem operations back to the activity taxonomy
- isolating execution into Docker or another Singine-governed runtime

then the next implementation step is an enforcement and telemetry layer.

That layer should:

1. maintain a canonical allowlist of paths and command prefixes per trusted AI system
2. wrap agent execution through a single governed gate
3. record every invocation into SQLite with:
   - command prefix
   - full command
   - path targets
   - activity taxonomy id
   - decision source
   - timestamp
   - execution environment such as local, docker, or isolated Singine runtime
4. project the same records into Logseq and policy assets

The current script is the first half of that: normalisation of grants and policy
structure. It is not yet the second half: enforcement of those grants.

## 6. Recommended next coding step

Build a second script or command that:

- reads `policy-pack.json`
- evaluates a requested command plus filesystem target
- returns `allow`, `deny`, or `prompt`
- increments counters in SQLite
- emits an activity record mapped to `core/java/singine/activity/*`

That is the point where your environment can stop asking repeatedly for grants
that have already been canonified.
