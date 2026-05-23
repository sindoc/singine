#!/usr/bin/env bash
# pr-commands.sh — PR creation commands for GitHub (public sindoc) + Bitbucket (private)
#
# Usage:
#   ENV=dev  bash pr-commands.sh      # PR targeting dev  (immediate approval)
#   ENV=prod bash pr-commands.sh      # PR targeting prod (requires review gate)
#
# Defaults to ENV=dev.

set -euo pipefail

ENV="${ENV:-dev}"
BRANCH="feat/cleanup-report-pipeline"
GH_REPO="sindoc/singine"
BB_WORKSPACE="${BB_WORKSPACE:-sindoc}"
BB_REPO="${BB_REPO:-singine}"

# ── Base branch per environment ───────────────────────────────────────────────
if [[ "${ENV}" == "prod" ]]; then
  GH_BASE="main"
  BB_BASE="main"
  AUTOMERGE_FLAG="--auto"      # still requires status checks
else
  GH_BASE="dev"
  BB_BASE="dev"
  AUTOMERGE_FLAG="--auto"      # immediate: auto-merge once checks pass
fi

PR_TITLE="feat: cleanup report pipeline — singine+silkpage+ATOM (${ENV})"

PR_BODY="$(cat <<BODY
## Summary
- Adds \`cleanup/\` to the singine repo: disk-space scanner, committee report generator, and Atom feed served at \`singine.uk/latest/ATOM\`
- Stack: C POSIX stat → Go scanner → Python collectors → singine actions (GOV-001/007) → silkpage HTML → Nginx CDN
- Committed artefacts: \`output/latest/ATOM\` (23 entries, 142.7 GB reclaimable), committee HTML + JSON
- Fixes \`singine/transfer.py\`: make \`import pwd\` optional (Windows compat)

## Environment
Target: \`${ENV}\` (\`${GH_BASE}\`)

## Test plan
- [ ] \`make -C cleanup committee\` regenerates JSON + HTML report
- [ ] \`make -C cleanup atom\` regenerates \`output/latest/ATOM\`
- [ ] \`GET https://singine.uk/latest/ATOM\` returns 200 \`application/atom+xml\`
- [ ] \`GET https://singine.uk/api/report\` returns latest scan JSON
- [ ] Copy button in \`cleanup.html\` copies \`singine runtime exec-external\` command to clipboard
- [ ] GOV-007 confirmation fires for \`dispatch.sh delete\`

🤖 Generated with [Claude Code](https://claude.ai/claude-code)
BODY
)"

# ── GitHub PR (public sindoc/singine) ─────────────────────────────────────────

echo "═══════════════════════════════════════════════════════"
echo " GitHub PR  →  github.com/${GH_REPO}  (env=${ENV})"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "# 1. Authenticate (once):"
echo "   gh auth login"
echo ""
echo "# 2. Ensure ${GH_BASE} branch exists:"
echo "   git fetch origin ${GH_BASE} || git push origin HEAD:${GH_BASE}"
echo ""
echo "# 3. Create PR (immediate approval via auto-merge):"
cat <<GH_CMD
gh pr create \\
  --repo "${GH_REPO}" \\
  --head "${BRANCH}" \\
  --base "${GH_BASE}" \\
  --title "${PR_TITLE}" \\
  --body \$'${PR_BODY//$'\n'/\\n}' \\
  --label "auto-merge" \\
  --label "env:${ENV}"

# 4. Enable auto-merge (merges automatically when checks pass):
#    gh pr merge --repo "${GH_REPO}" --auto --squash "${BRANCH}"
GH_CMD

echo ""
echo "# Direct URL (after push):"
echo "   https://github.com/${GH_REPO}/pull/new/${BRANCH}"

echo ""
echo "═══════════════════════════════════════════════════════"
echo " Bitbucket PR  →  bitbucket.org/${BB_WORKSPACE}/${BB_REPO}  (env=${ENV})"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "# 1. Add Bitbucket remote (one-time):"
echo "   git remote add bb https://bitbucket.org/${BB_WORKSPACE}/${BB_REPO}.git"
echo "   # or SSH: git remote add bb git@bitbucket.org:${BB_WORKSPACE}/${BB_REPO}.git"
echo ""
echo "# 2. Push branch to Bitbucket:"
echo "   git push bb ${BRANCH}"
echo ""
echo "# 3. Create PR via Bitbucket REST API:"
cat <<BB_CMD
BB_USER="\${BB_USER:?set BB_USER}"
BB_PASS="\${BB_PASS:?set BB_PASS}"   # app password — not account password

curl -s -u "\${BB_USER}:\${BB_PASS}" \\
  -X POST \\
  -H "Content-Type: application/json" \\
  "https://api.bitbucket.org/2.0/repositories/${BB_WORKSPACE}/${BB_REPO}/pullrequests" \\
  -d '{
    "title":       "${PR_TITLE}",
    "description": "Cleanup report pipeline (env=${ENV}). See GitHub PR for full test plan.",
    "source":      {"branch": {"name": "${BRANCH}"}},
    "destination": {"branch": {"name": "${BB_BASE}"}},
    "reviewers":   [],
    "close_source_branch": true
  }' | python3 -m json.tool
BB_CMD

echo ""
echo "# Or open the Bitbucket web UI directly:"
echo "   https://bitbucket.org/${BB_WORKSPACE}/${BB_REPO}/pull-requests/new?source=${BRANCH}&dest=${BB_BASE}"
