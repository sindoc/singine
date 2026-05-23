#!/usr/bin/env bash
# bootstrap.sh — full install chain for the cleanup singine+silkpage stack
#
# What this does (in order):
#   1. Install singine globally (npm install -g singine)
#   2. Use singine to install silkpage (npm install -g silkpage)
#   3. Build the C stat-hook (POSIX only)
#   4. Build the Go scanner binary → bin/scan
#   5. Run the scanner to generate the initial report
#   6. Install Nginx config (prompts before overwriting)
#
# Prerequisites: npm, node (v18+), go (1.21+), cc (POSIX optional)
# Usage:
#   bash bootstrap.sh [--cdn-host cdn.example.org] [--port 8090] [--no-nginx]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CDN_HOST="cdn.example.org"
SITE_PORT="8090"
SKIP_NGINX=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cdn-host)  CDN_HOST="$2";  shift 2 ;;
    --port)      SITE_PORT="$2"; shift 2 ;;
    --no-nginx)  SKIP_NGINX=1;   shift   ;;
    *)           shift ;;
  esac
done

export SILKPAGE_ROOT="${SCRIPT_DIR}"
export CDN_HOST SITE_PORT

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m  ✓ %s\033[0m\n" "$*"; }
warn() { printf "\033[1;33m  ⚠ %s\033[0m\n" "$*"; }

# ── 1. singine ────────────────────────────────────────────────────────────────
step "Installing singine (npm install -g singine)"
if command -v singine >/dev/null 2>&1; then
  ok "singine already installed: $(singine --version 2>/dev/null || echo '?')"
else
  npm install -g singine
  ok "singine installed"
fi

# ── 2. silkpage (via singine) ─────────────────────────────────────────────────
step "Installing silkpage via singine"
if command -v silkpage >/dev/null 2>&1; then
  ok "silkpage already installed"
else
  singine runtime exec-external npm install -g silkpage
  ok "silkpage installed"
fi

# ── 3. C stat-hook (POSIX only) ───────────────────────────────────────────────
step "Building C stat-hook"
if [[ "$(uname -s 2>/dev/null)" == MINGW* ]] || [[ "$(uname -s 2>/dev/null)" == CYGWIN* ]]; then
  warn "Windows/Git-Bash detected — skipping C build (Go scanner handles sizing natively)"
elif command -v cc >/dev/null 2>&1 || command -v gcc >/dev/null 2>&1; then
  make -C "${SCRIPT_DIR}/c" --no-print-directory
  ok "bin/stat-hook built"
else
  warn "cc not found — stat-hook skipped (non-fatal)"
fi

# ── 4. Go scanner ─────────────────────────────────────────────────────────────
step "Building Go scanner → bin/scan"
if ! command -v go >/dev/null 2>&1; then
  warn "go not found — cannot build scanner. Install Go 1.21+ then run: make scanner"
else
  mkdir -p "${SCRIPT_DIR}/bin"
  (cd "${SCRIPT_DIR}/go/scanner" && CGO_ENABLED=0 go build -trimpath -o "${SCRIPT_DIR}/bin/scan" .)
  ok "bin/scan built"
fi

# ── 5. Initial scan ───────────────────────────────────────────────────────────
step "Running initial scan"
if [[ -x "${SCRIPT_DIR}/bin/scan" ]]; then
  bash "${SCRIPT_DIR}/scan.sh" --skip-build
  ok "report/latest.json written"
else
  warn "scanner not built — skipping initial scan"
fi

# ── 6. Nginx config ───────────────────────────────────────────────────────────
if [[ -z "${SKIP_NGINX}" ]]; then
  step "Installing Nginx configuration"
  if command -v nginx >/dev/null 2>&1; then
    NGINX_CONF_DIR="/etc/nginx/conf.d"
    DEST="${NGINX_CONF_DIR}/cleanup-silkpage.conf"
    if [[ -w "${NGINX_CONF_DIR}" ]]; then
      # Substitute env vars and write config
      SILKPAGE_ROOT="${SCRIPT_DIR}" \
      CDN_HOST="${CDN_HOST}" \
      SITE_PORT="${SITE_PORT}" \
      REPORT_DIR="${SCRIPT_DIR}/report" \
        envsubst '$SILKPAGE_ROOT $CDN_HOST $SITE_PORT $REPORT_DIR' \
        < "${SCRIPT_DIR}/nginx/silkpage.conf" \
        > "${DEST}"
      nginx -t && nginx -s reload
      ok "Nginx reloaded — site at http://localhost:${SITE_PORT}/cleanup.html"
    else
      warn "Cannot write to ${NGINX_CONF_DIR} — run with sudo or configure manually"
      printf "  Rendered config (copy manually to nginx conf.d):\n"
      SILKPAGE_ROOT="${SCRIPT_DIR}" CDN_HOST="${CDN_HOST}" SITE_PORT="${SITE_PORT}" \
      REPORT_DIR="${SCRIPT_DIR}/report" \
        envsubst '$SILKPAGE_ROOT $CDN_HOST $SITE_PORT $REPORT_DIR' \
        < "${SCRIPT_DIR}/nginx/silkpage.conf"
    fi
  else
    warn "nginx not found — install nginx then run:"
    printf "    SILKPAGE_ROOT=%s CDN_HOST=%s SITE_PORT=%s REPORT_DIR=%s/report \\\n" \
      "${SCRIPT_DIR}" "${CDN_HOST}" "${SITE_PORT}" "${SCRIPT_DIR}"
    printf "      envsubst '\$SILKPAGE_ROOT \$CDN_HOST \$SITE_PORT \$REPORT_DIR' \\\n"
    printf "      < nginx/silkpage.conf > /etc/nginx/conf.d/cleanup-silkpage.conf\n"
  fi
fi

# ── Done ──────────────────────────────────────────────────────────────────────
printf "\n\033[1;32m✓ Bootstrap complete\033[0m\n"
printf "\nQuick reference:\n"
printf "  Scan:         singine runtime exec-external bash %s/scan.sh\n" "${SCRIPT_DIR}"
printf "  Delete:       singine runtime exec-external %s/bin/scan delete --path <abs-path>\n" "${SCRIPT_DIR}"
printf "  Dispatch:     bash %s/singine/dispatch.sh delete --path <abs-path>\n" "${SCRIPT_DIR}"
printf "  Report JSON:  %s/report/latest.json\n" "${SCRIPT_DIR}"
printf "  Web UI:       http://localhost:%s/cleanup.html\n" "${SITE_PORT}"
printf "  CDN assets:   //cdn.example.org/assets/css/cleanup.css\n"
