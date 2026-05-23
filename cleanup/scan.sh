#!/usr/bin/env bash
# scan.sh — POSIX disk-space scan entry point
#
# Builds the Go scanner binary if needed, runs it, and writes:
#   report/latest.json      — machine-readable report (singine/silkpage input)
#   report/cleanup.xml      — silkpage XML page (transformed to HTML by XSL)
#
# Usage:
#   bash scan.sh                    # scan current user's home
#   bash scan.sh --home /other      # scan a different home
#   bash scan.sh --pretty false     # compact JSON
#   bash scan.sh --skip-build       # skip go build (use existing bin/scan)
#
# singine invocation (from anywhere):
#   singine runtime exec-external bash /path/to/cleanup/scan.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/bin"
REPORT_DIR="${SCRIPT_DIR}/report"
SCANNER="${BIN_DIR}/scan"
C_DIR="${SCRIPT_DIR}/c"

# ── Argument defaults ─────────────────────────────────────────────────────────
HOME_FLAG=""
PRETTY="true"
SKIP_BUILD=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --home)        HOME_FLAG="$2";  shift 2 ;;
    --pretty)      PRETTY="$2";    shift 2 ;;
    --skip-build)  SKIP_BUILD=1;   shift   ;;
    *)             shift ;;
  esac
done

# ── Build C stat-hook (POSIX only, skip on Windows/Git-Bash without cc) ───────
if [[ -z "${SKIP_BUILD}" && "$(uname -s)" != MINGW* && "$(uname -s)" != CYGWIN* ]]; then
  if command -v cc >/dev/null 2>&1 || command -v gcc >/dev/null 2>&1; then
    make -C "${C_DIR}" --no-print-directory 2>/dev/null && \
      printf "  [c]  stat-hook built\n" || \
      printf "  [c]  stat-hook build skipped (non-fatal)\n"
  fi
fi

# ── Build Go scanner ─────────────────────────────────────────────────────────
if [[ -z "${SKIP_BUILD}" ]]; then
  if command -v go >/dev/null 2>&1; then
    mkdir -p "${BIN_DIR}"
    (cd "${SCRIPT_DIR}/go/scanner" && \
     CGO_ENABLED=0 go build -trimpath -o "${SCANNER}" . 2>&1)
    printf "  [go] scanner built: %s\n" "${SCANNER}"
  else
    printf "  [go] go not found — using existing binary if available\n"
  fi
fi

if [[ ! -x "${SCANNER}" ]]; then
  printf "ERROR: scanner binary not found at %s\n" "${SCANNER}" >&2
  printf "  Run: cd %s/go/scanner && go build -o ../../bin/scan .\n" "${SCRIPT_DIR}" >&2
  exit 1
fi

# ── Run scanner ───────────────────────────────────────────────────────────────
mkdir -p "${REPORT_DIR}"

SCAN_ARGS=(--pretty "${PRETTY}" --out "${REPORT_DIR}/latest.json" --xml "${REPORT_DIR}/cleanup.xml")
[[ -n "${HOME_FLAG}" ]] && SCAN_ARGS+=(--home "${HOME_FLAG}")

printf "scanning... "
"${SCANNER}" "${SCAN_ARGS[@]}"
printf "done\n"

printf "\nreport written to:\n"
printf "  %s/latest.json\n" "${REPORT_DIR}"
printf "  %s/cleanup.xml\n" "${REPORT_DIR}"

# ── Show top-5 summary ────────────────────────────────────────────────────────
if command -v python3 >/dev/null 2>&1; then
  python3 - "${REPORT_DIR}/latest.json" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    r = json.load(f)
print(f"\ntotal reclaimable: {r['total_reclaimable_human']}")
print(f"{'SIZE':>10}  {'RISK':<8}  LABEL")
for it in r['items'][:10]:
    if it['size_bytes'] > 0:
        print(f"{it['size_human']:>10}  {it['risk']:<8}  {it['label']}")
PYEOF
fi
