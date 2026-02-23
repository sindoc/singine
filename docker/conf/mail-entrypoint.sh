#!/bin/bash
# mail-entrypoint.sh — singine mail container startup
# Configures Postfix + Dovecot from ENV, then starts both daemons.
#
# ENV:
#   MAIL_DOMAIN   — SMTP/IMAP domain (default: localhost)
#   MAIL_USER     — username (default: singine)
#   MAIL_PASS     — plain-text password (default: singinepass)
set -euo pipefail

MAIL_DOMAIN="${MAIL_DOMAIN:-localhost}"
MAIL_USER="${MAIL_USER:-singine}"
MAIL_PASS="${MAIL_PASS:-singinepass}"

echo "singine-mail: domain=${MAIL_DOMAIN} user=${MAIL_USER}"

# ── Create system user for mail delivery ─────────────────────────────────────
if ! id "${MAIL_USER}" &>/dev/null; then
  useradd -m -s /bin/false -d "/var/mail/${MAIL_USER}" "${MAIL_USER}"
fi
mkdir -p "/var/mail/${MAIL_USER}/Maildir"/{cur,new,tmp}
chown -R "${MAIL_USER}:${MAIL_USER}" "/var/mail/${MAIL_USER}"

# ── vmail group for Dovecot ───────────────────────────────────────────────────
groupadd -f vmail
id vmail &>/dev/null || useradd -g vmail -s /bin/false vmail

# ── Postfix: substitute domain in main.cf ────────────────────────────────────
sed "s/\${MAIL_DOMAIN}/${MAIL_DOMAIN}/g" \
    /etc/postfix/main.cf.template > /etc/postfix/main.cf

# ── Dovecot passwd-file ───────────────────────────────────────────────────────
# Format: username:{PLAIN}password:uid:gid:gecos:home:shell:extra_fields
DOVECOT_UID=$(id -u "${MAIL_USER}" 2>/dev/null || echo "1000")
DOVECOT_GID=$(id -g "${MAIL_USER}" 2>/dev/null || echo "1000")
echo "${MAIL_USER}:{PLAIN}${MAIL_PASS}:${DOVECOT_UID}:${DOVECOT_GID}::/var/mail/${MAIL_USER}::" \
    > /etc/dovecot/users

# ── Start Postfix ─────────────────────────────────────────────────────────────
postfix start

# ── Start Dovecot (foreground) ────────────────────────────────────────────────
exec dovecot -F
