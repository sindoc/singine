// cleanup.js — served via cdn.example.org/assets/js/cleanup.js
// Fetches /api/report (report/latest.json), renders the cleanup table,
// and wires copy-to-clipboard for singine commands.

(function () {
  'use strict';

  const API_URL = window.CLEANUP_API || '/api/report';

  // ── Rendering ──────────────────────────────────────────────────────────────

  function humanSize(bytes) {
    if (bytes < 0) return 'not found';
    const units = ['B','KB','MB','GB','TB'];
    let i = 0, n = bytes;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return n.toFixed(1) + ' ' + units[i];
  }

  function riskBadge(risk) {
    const map = { safe: '✓ safe', review: '⚠ review', keep: '· keep' };
    return map[risk] || risk;
  }

  function makeRow(item) {
    const tr = document.createElement('tr');
    tr.className = `item risk-${item.risk}`;
    tr.dataset.id = item.id;

    const size = item.size_bytes > 0 ? item.size_human : 'not found';

    tr.innerHTML = `
      <td class="size">${escHtml(size)}</td>
      <td class="label">${escHtml(item.label)}</td>
      <td class="path"><code>${escHtml(item.path)}</code></td>
      <td class="risk badge-${escHtml(item.risk)}">${riskBadge(item.risk)}</td>
      <td class="cmd">
        <code class="singine-cmd" id="cmd-${escHtml(item.id)}">${escHtml(item.singine_cmd)}</code>
        <button class="copy-btn" data-cmd="${escHtml(item.singine_cmd)}">Copy</button>
        <details class="cmd-detail">
          <summary>shell / win</summary>
          <code class="shell-cmd">${escHtml(item.shell_cmd)}</code>
          <code class="win-cmd">${escHtml(item.win_cmd)}</code>
        </details>
        ${item.notes ? `<p class="item-notes">${escHtml(item.notes)}</p>` : ''}
      </td>`;

    return tr;
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderReport(report) {
    const tbody = document.getElementById('cleanup-tbody');
    const banner = document.getElementById('total-banner');
    const meta   = document.getElementById('scan-meta');

    if (!tbody) return;

    tbody.innerHTML = '';
    report.items.forEach(function (item) {
      if (item.size_bytes !== 0) {          // hide "not found" items by default
        tbody.appendChild(makeRow(item));
      }
    });

    if (banner) {
      banner.textContent =
        'Total reclaimable: ' + report.total_reclaimable_human +
        '  ·  scanned: ' + report.scanned_at;
      banner.removeAttribute('hidden');
    }

    if (meta) {
      meta.textContent =
        'OS: ' + report.os +
        '  ·  home: ' + report.home_dir +
        '  ·  scanned: ' + report.scanned_at;
    }

    // Wire copy buttons
    tbody.querySelectorAll('.copy-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var cmd = btn.dataset.cmd;
        if (!cmd) return;
        navigator.clipboard.writeText(cmd).then(function () {
          btn.textContent = 'Copied!';
          btn.classList.add('copied');
          setTimeout(function () {
            btn.textContent = 'Copy';
            btn.classList.remove('copied');
          }, 2000);
        }).catch(function () {
          // Fallback for non-HTTPS contexts
          var ta = document.createElement('textarea');
          ta.value = cmd;
          ta.style.position = 'fixed';
          ta.style.opacity  = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          btn.textContent = 'Copied!';
          setTimeout(function () { btn.textContent = 'Copy'; }, 2000);
        });
      });
    });
  }

  // ── Fetch ──────────────────────────────────────────────────────────────────

  function loadReport() {
    fetch(API_URL, { cache: 'no-store' })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(renderReport)
      .catch(function (err) {
        var meta = document.getElementById('scan-meta');
        if (meta) meta.textContent =
          'Could not load live report (' + err.message + ')' +
          ' — showing static data.';
        // Wire copy buttons on pre-rendered static rows
        document.querySelectorAll('.copy-btn[data-cmd]').forEach(function (btn) {
          btn.addEventListener('click', function () {
            navigator.clipboard.writeText(btn.dataset.cmd).catch(function(){});
            btn.textContent = 'Copied!';
            setTimeout(function(){ btn.textContent = 'Copy'; }, 2000);
          });
        });
      });
  }

  document.addEventListener('DOMContentLoaded', loadReport);
}());
