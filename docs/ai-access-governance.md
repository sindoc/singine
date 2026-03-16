# AI Access Governance

This guide covers the enforcement and telemetry layer for AI-system access.

Primary script:

- `bin/singine-govern-ai-access`

It works with the canonical policy pack produced by:

- `bin/singine-canonify-ai-policies`

## What it does

- evaluates an AI request against trusted-system, environment, network-mode,
  command-prefix, path, repo, and major-change rules
- persists approvals so already-granted resources do not prompt again
- tracks invocation counters in SQLite
- maps commands to activity ids
- emits decision artefacts as JSON, EDN, Markdown, and XML
- can optionally log approvals to 1Password

## What it does not yet do

- it does not automatically intercept Codex or Claude at the host runtime level
- it does not yet auto-compute real diffs from git or apply patches on its own
- it does not yet publish directly through Silkpage, but it emits XML and
  Markdown artefacts suitable for that next step

## 1. Generate or refresh the canonical pack

```bash
python3 bin/singine-canonify-ai-policies \
  --ldap-ldif docs/examples/ldap-ai-groups.ldif \
  --output-dir /tmp/singine-ai-policy-pack
```

Use the generated pack at:

```text
/private/tmp/singine-ai-policy-pack/policy-pack.json
```

## 2. Evaluate a trusted read request

This should allow because:

- system is `codex`
- environment is `dev`
- network mode is `offline`
- command is read-only
- path is under `~/ws`

```bash
python3 bin/singine-govern-ai-access \
  evaluate \
  --policy-pack /private/tmp/singine-ai-policy-pack/policy-pack.json \
  --ai-system codex \
  --environment dev \
  --network-mode offline \
  --execution-env local \
  --operation read \
  --command rg --files /Users/skh/ws/git/github/sindoc/singine \
  --path /Users/skh/ws/git/github/sindoc/singine/README.md
```

Expected result:

- exit code `0`
- decision `allow`
- decision artefacts written under `~/.singine/ai-access-governance/decisions/`

## 3. Evaluate a destructive request

This should prompt because deletes are approval-gated:

```bash
python3 bin/singine-govern-ai-access \
  evaluate \
  --policy-pack /private/tmp/singine-ai-policy-pack/policy-pack.json \
  --ai-system codex \
  --environment dev \
  --network-mode offline \
  --execution-env local \
  --operation delete \
  --command rm -rf /Users/skh/ws/git/github/sindoc/singine/tmp \
  --path /Users/skh/ws/git/github/sindoc/singine/tmp
```

Expected result:

- exit code `2`
- decision `prompt`

## 4. Persist an approval

Persist an approval for a path prefix, repo, command prefix, or lambda.

Example for a path prefix:

```bash
python3 bin/singine-govern-ai-access \
  approve \
  --ai-system codex \
  --environment dev \
  --network-mode offline \
  --execution-env local \
  --operation write \
  --command git status \
  --path /Users/skh/ws/collibra/edge \
  --resource-grant-kind path-prefix \
  --granted-by singineer-dev \
  --reason "Collibra Edge docker build area approved for trusted dev work"
```

If you want a best-effort 1Password log entry:

```bash
python3 bin/singine-govern-ai-access \
  approve \
  --ai-system codex \
  --environment dev \
  --network-mode lan \
  --execution-env docker \
  --operation execute \
  --command docker compose -f docker/docker-compose.edge.yml up -d --build \
  --repo-path /Users/skh/ws/collibra/edge \
  --resource-grant-kind repo \
  --granted-by singineer-dev \
  --reason "Approved docker build and run for Collibra Edge test env" \
  --op-vault Singine
```

## 5. Re-evaluate after approval

Once an approval exists, the same request should return `allow` instead of
`prompt`.

## 6. Evaluate with a request JSON

You can use structured requests when you want major-change heuristics and
explicit file statistics.

Example:

```bash
python3 bin/singine-govern-ai-access \
  evaluate \
  --policy-pack /private/tmp/singine-ai-policy-pack/policy-pack.json \
  --request-json docs/examples/ai-access-major-change.json
```

## 7. Inspect counters and approvals

```bash
python3 bin/singine-govern-ai-access report
python3 bin/singine-govern-ai-access report --ai-system codex
```

The SQLite database lives by default at:

```text
~/.singine/ai-access-governance.sqlite3
```

Useful direct queries:

```bash
sqlite3 ~/.singine/ai-access-governance.sqlite3 'select scope, key, ai_system, count from invocation_counters order by count desc;'
sqlite3 ~/.singine/ai-access-governance.sqlite3 'select ai_system, decision, command_prefix, created_at from decisions order by created_at desc limit 20;'
sqlite3 ~/.singine/ai-access-governance.sqlite3 'select ai_system, resource_kind, resource_value, granted_by from approvals order by created_at desc;'
```

## 8. Decision artefacts for Silkpage and review

Each evaluation or approval writes artefacts under:

- `~/.singine/ai-access-governance/decisions/`
- `~/.singine/ai-access-governance/approvals/`

Each record includes:

- JSON
- EDN
- Markdown
- XML

The XML form is intended as the bridge into Silkpage publication and other
XML-first workflows.

## 9. Current policy defaults

Current defaults are intentionally conservative:

- trusted systems:
  - `dev`: `claude`, `codex`
  - `prd`: `claude`
- reads under `~/ws` are allowed for trusted systems
- delete operations always require approval
- major changes require approval
- internet-facing execution without explicit network permission requires approval
- trusted dev write and execute requests can proceed when they match the policy
  pack and do not trigger destructive heuristics

## 10. Next integration step

The next step is to wrap actual agent execution through this gate so a live
request is:

1. evaluated here
2. matched against persisted approvals
3. allowed or prompted
4. counted and linked back to a taxonomy activity id

That is the step that can remove repeated directory prompts for already-granted
resources.
