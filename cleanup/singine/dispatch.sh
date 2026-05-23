#!/usr/bin/env bash
# singine/dispatch.sh — singine cleanup action dispatcher
#
# Wraps singine runtime exec-external with GOV-007 confirmation prompts
# and GOV-001 audit logging.  Called by scan.sh or directly.
#
# Usage:
#   bash dispatch.sh delete  --path <abs-path> [--yes]
#   bash dispatch.sh scan
#   bash dispatch.sh report
#
# All dispatches are logged to report/audit.log (GOV-001).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "${SCRIPT_DIR}")"
AUDIT_LOG="${ROOT_DIR}/report/audit.log"
SCAN_BIN="${ROOT_DIR}/bin/scan"

log_audit() {
  mkdir -p "$(dirname "${AUDIT_LOG}")"
  printf "%s\taction=%s\tparams=%s\tgov=GOV-001\n" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$1" "${*:2}" >> "${AUDIT_LOG}"
}

confirm() {
  local msg="$1"
  local force="${2:-}"
  if [[ -n "${force}" ]]; then return 0; fi
  printf "\n%s\n(GOV-007) Type YES to confirm: " "${msg}"
  read -r answer
  [[ "${answer}" == "YES" ]] || { printf "aborted.\n"; exit 0; }
}

CMD="${1:-}"
shift || true

case "${CMD}" in

  scan)
    log_audit "cleanup.scan"
    bash "${ROOT_DIR}/scan.sh" "$@"
    ;;

  report)
    if [[ -f "${ROOT_DIR}/report/latest.json" ]]; then
      cat "${ROOT_DIR}/report/latest.json"
    else
      printf '{"error":"no report yet — run: bash scan.sh"}\n'
    fi
    ;;

  delete)
    PATH_ARG=""
    YES_FLAG=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --path) PATH_ARG="$2"; shift 2 ;;
        --yes)  YES_FLAG=1;    shift   ;;
        *)      shift ;;
      esac
    done
    [[ -n "${PATH_ARG}" ]] || { printf "dispatch.sh delete: --path required\n" >&2; exit 1; }

    SIZE="$(du -sh "${PATH_ARG}" 2>/dev/null | cut -f1 || echo "?")"
    log_audit "cleanup.delete.path" "path=${PATH_ARG}"  # GOV-001: before dispatch
    confirm "Delete ${PATH_ARG} (${SIZE})?  This cannot be undone." "${YES_FLAG}"

    printf "deleting %s...\n" "${PATH_ARG}"
    singine runtime exec-external "${SCAN_BIN}" delete --path "${PATH_ARG}"
    printf "done.\n"
    log_audit "cleanup.delete.path.done" "path=${PATH_ARG}"
    ;;

  *)
    printf "usage: dispatch.sh <scan|report|delete> [options]\n" >&2
    exit 1
    ;;
esac
