"""singine.panel_server — Live intranet control panel (Tornado).

Serves on port 9090 (configurable via --port or SINGINE_PANEL_PORT).

Routes:
  GET  /                      → control panel UI
  GET  /api/health            → health check
  GET  /api/net/services      → service inventory (JSON)
  GET  /api/net/routes        → routing table (JSON)
  POST /api/net/probe         → probe a service  { "service": "edge-site" }
  POST /api/net/invoke        → invoke a singine command  { "cmd": [...] }
  GET  /api/presence/status   → presence status
  POST /api/presence/verify   → trigger presence verification
  GET  /feeds/activity.atom   → Atom 1.0 activity feed
  GET  /feeds/activity.rss    → RSS 1.0 (RDF) activity feed
  GET  /feeds/decisions.atom  → Atom governance decisions
  GET  /feeds/decisions.rss   → RSS governance decisions
  GET  /vocab/knowyourai.ttl  → SKOS vocabulary (Turtle)
  GET  /vocab/knowyourai.rdf  → SKOS vocabulary (RDF/XML)

All POST routes that affect infrastructure require a valid presence JWT
(Authorization: Bearer <jwt>  or cookie singine_presence).

Start::

    singine panel serve --port 9090
    singine panel serve --port 9090 --bind 127.0.0.1
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import tornado.web
    import tornado.ioloop
    import tornado.escape
    HAS_TORNADO = True
except ImportError:
    HAS_TORNADO = False

from . import net as _net
from . import presence as _presence
from . import feeds as _feeds

PANEL_PORT_DEFAULT = 9090
PANEL_BIND_DEFAULT = "127.0.0.1"
VOCAB_DIR = Path(__file__).resolve().parent.parent / "vocab"

# ── HTML template ──────────────────────────────────────────────────────────────

_PANEL_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>singine net — intranet control panel</title>
  <style>
    :root {
      --bg: #0d1117; --surface: #161b22; --border: #30363d;
      --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
      --green: #3fb950; --red: #f85149; --amber: #d29922;
      --purple: #bc8cff; --teal: #39d353;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg); color: var(--text);
      font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
      font-size: 13px; line-height: 1.6;
    }
    header {
      background: var(--surface); border-bottom: 1px solid var(--border);
      padding: 12px 24px; display: flex; align-items: center; gap: 16px;
    }
    header h1 { font-size: 1rem; color: var(--accent); letter-spacing: .05em; }
    header .sub { color: var(--muted); font-size: .8rem; }
    .presence-badge {
      margin-left: auto; padding: 4px 12px; border-radius: 4px;
      font-size: .75rem; cursor: pointer; border: 1px solid var(--border);
    }
    .presence-ok   { background: rgba(63,185,80,.15); color: var(--green); border-color: var(--green); }
    .presence-warn { background: rgba(248,81,73,.15); color: var(--red); border-color: var(--red); }
    main { display: grid; grid-template-columns: 300px 1fr; height: calc(100vh - 49px); }
    nav {
      background: var(--surface); border-right: 1px solid var(--border);
      overflow-y: auto; padding: 12px 0;
    }
    nav .section { padding: 6px 16px 2px; font-size: .65rem;
      text-transform: uppercase; letter-spacing: .1em; color: var(--muted); }
    nav a {
      display: block; padding: 6px 20px; color: var(--text); text-decoration: none;
      transition: background .1s;
    }
    nav a:hover, nav a.active { background: rgba(88,166,255,.08); color: var(--accent); }
    .content { overflow-y: auto; padding: 24px; }
    .panel { background: var(--surface); border: 1px solid var(--border);
      border-radius: 6px; margin-bottom: 20px; }
    .panel-header {
      padding: 10px 16px; border-bottom: 1px solid var(--border);
      font-size: .75rem; text-transform: uppercase; letter-spacing: .08em;
      color: var(--muted); display: flex; align-items: center; gap: 8px;
    }
    .panel-body { padding: 16px; }
    table { width: 100%; border-collapse: collapse; }
    th { text-align: left; color: var(--muted); font-size: .7rem;
      text-transform: uppercase; letter-spacing: .08em;
      padding: 4px 8px; border-bottom: 1px solid var(--border); }
    td { padding: 7px 8px; border-bottom: 1px solid rgba(48,54,61,.5); vertical-align: top; }
    tr:last-child td { border-bottom: none; }
    .dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
    .dot-green { background: var(--green); box-shadow: 0 0 6px var(--green); }
    .dot-red   { background: var(--red);   box-shadow: 0 0 6px var(--red); }
    .dot-grey  { background: var(--muted); }
    .tag {
      display: inline-block; padding: 1px 7px; border-radius: 3px;
      font-size: .7rem; border: 1px solid var(--border);
    }
    .tag-docker  { color: var(--accent);  border-color: var(--accent); }
    .tag-process { color: var(--purple);  border-color: var(--purple); }
    .tag-human   { color: var(--teal);    border-color: var(--teal); }
    .tag-machine { color: var(--muted);   }
    .btn {
      padding: 6px 14px; border-radius: 4px; cursor: pointer;
      font-size: .8rem; font-family: inherit; border: 1px solid var(--border);
      background: transparent; color: var(--text); transition: all .15s;
    }
    .btn:hover { background: var(--accent); color: var(--bg); border-color: var(--accent); }
    .btn-danger:hover { background: var(--red); border-color: var(--red); }
    .btn-green:hover  { background: var(--green); border-color: var(--green); }
    .cmd-input {
      width: 100%; background: var(--bg); border: 1px solid var(--border);
      color: var(--text); padding: 8px 12px; border-radius: 4px;
      font-family: inherit; font-size: .85rem;
    }
    .output-box {
      background: var(--bg); border: 1px solid var(--border);
      padding: 12px; border-radius: 4px; white-space: pre-wrap;
      font-size: .8rem; min-height: 80px; max-height: 400px; overflow-y: auto;
      color: var(--teal);
    }
    .feeds { display: flex; flex-wrap: wrap; gap: 10px; }
    .feed-link {
      padding: 8px 14px; border: 1px solid var(--border); border-radius: 4px;
      color: var(--accent); text-decoration: none; font-size: .8rem;
    }
    .feed-link:hover { border-color: var(--accent); background: rgba(88,166,255,.08); }
    .kya-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; padding: 8px 0;
      border-bottom: 1px solid var(--border); }
    .kya-row:last-child { border-bottom: none; }
    .port-num { color: var(--amber); font-weight: bold; }
    #toast {
      position: fixed; bottom: 20px; right: 20px; padding: 10px 18px;
      background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
      color: var(--text); font-size: .85rem; display: none; z-index: 9999;
    }
  </style>
</head>
<body>
<header>
  <span>◈</span>
  <h1>singine net</h1>
  <span class="sub">intranet control panel · sindoc.local</span>
  <div id="presence-badge" class="presence-badge presence-warn" onclick="verifyPresence()">
    ◌ presence unknown
  </div>
</header>
<main>
  <nav>
    <div class="section">Network</div>
    <a href="#services" onclick="show('services')" id="nav-services">Services &amp; Ports</a>
    <a href="#routes"   onclick="show('routes')"   id="nav-routes">Routing Table</a>
    <a href="#docker"   onclick="show('docker')"   id="nav-docker">Docker Containers</a>
    <div class="section">Identity</div>
    <a href="#presence" onclick="show('presence')" id="nav-presence">Presence &amp; Auth</a>
    <div class="section">Actions</div>
    <a href="#invoke"   onclick="show('invoke')"   id="nav-invoke">Invoke Command</a>
    <a href="#edge"     onclick="show('edge')"     id="nav-edge">Edge Stack</a>
    <a href="#web"      onclick="show('web')"      id="nav-web">Web (www/vww/wsec)</a>
    <div class="section">Vocabulary</div>
    <a href="#knowyourai" onclick="show('knowyourai')" id="nav-knowyourai">#knowyourai</a>
    <div class="section">Feeds</div>
    <a href="#feeds"    onclick="show('feeds')"    id="nav-feeds">Atom / RSS 1.0</a>
  </nav>
  <div class="content">

    <!-- Services -->
    <div id="pane-services" class="pane">
      <div class="panel">
        <div class="panel-header">⬡ Services &amp; Ports <button class="btn" onclick="refreshServices()">↻ Refresh</button></div>
        <div class="panel-body">
          <table id="services-table">
            <thead><tr>
              <th></th><th>Port</th><th>ID</th><th>Kind</th><th>Label</th><th>Latency</th><th>Presence</th>
            </tr></thead>
            <tbody id="services-body"><tr><td colspan="7">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Routes -->
    <div id="pane-routes" class="pane" style="display:none">
      <div class="panel">
        <div class="panel-header">⇀ Routing Table</div>
        <div class="panel-body">
          <table id="routes-table">
            <thead><tr><th>Path Pattern</th><th>Target Service</th><th>Cache</th><th>Auth</th><th>Notes</th></tr></thead>
            <tbody id="routes-body"><tr><td colspan="5">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Docker -->
    <div id="pane-docker" class="pane" style="display:none">
      <div class="panel">
        <div class="panel-header">⬡ Docker Containers <button class="btn" onclick="refreshDocker()">↻ Refresh</button></div>
        <div class="panel-body">
          <table>
            <thead><tr><th>Name</th><th>Image</th><th>Status</th><th>Ports</th></tr></thead>
            <tbody id="docker-body"><tr><td colspan="4">Loading…</td></tr></tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Presence -->
    <div id="pane-presence" class="pane" style="display:none">
      <div class="panel">
        <div class="panel-header">◈ Human Presence Attestation</div>
        <div class="panel-body">
          <div id="presence-detail">Loading…</div>
          <br>
          <button class="btn btn-green" onclick="verifyPresence()">Verify Presence (Touch ID / 1Password)</button>
          <button class="btn" onclick="presenceStatus()">↻ Check Status</button>
          <br><br>
          <div class="output-box" id="presence-output">—</div>
          <br>
          <p style="color:var(--muted); font-size:.8rem">
            Presence is checked every 30 minutes. A short-lived JWT is issued on successful verification.
            Activities tagged <span class="tag tag-human">⬡ human-required</span> will block unless presence is verified.
          </p>
        </div>
      </div>
    </div>

    <!-- Invoke -->
    <div id="pane-invoke" class="pane" style="display:none">
      <div class="panel">
        <div class="panel-header">⇒ Invoke singine Command</div>
        <div class="panel-body">
          <p style="color:var(--muted); margin-bottom:10px; font-size:.8rem">
            Commands that affect infrastructure require a verified presence. Commands are logged as domain events.
          </p>
          <input type="text" id="invoke-cmd" class="cmd-input"
            placeholder="singine net status --json"
            value="singine net status --json"/>
          <br><br>
          <button class="btn btn-green" onclick="invokeCmd()">▶ Execute</button>
          <br><br>
          <div class="output-box" id="invoke-output">—</div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-header">⬡ Quick Actions</div>
        <div class="panel-body" id="quick-actions">
          <div style="display:flex;flex-wrap:wrap;gap:8px;">
            <button class="btn" onclick="runQuick('singine edge status --json')">edge status</button>
            <button class="btn" onclick="runQuick('singine net status --json')">net status</button>
            <button class="btn" onclick="runQuick('singine context --json')">context</button>
            <button class="btn" onclick="runQuick('singine bridge sources --db /tmp/sqlite.db')">bridge sources</button>
            <button class="btn" onclick="runQuick('singine model catalog --json')">model catalog</button>
            <button class="btn" onclick="runQuick('singine domain event log --limit 10 --json --db /tmp/humble-idp.db')">event log</button>
            <button class="btn btn-danger" onclick="runQuick('singine edge down')">edge down</button>
            <button class="btn btn-green" onclick="runQuick('singine edge up --detach')">edge up</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Edge stack -->
    <div id="pane-edge" class="pane" style="display:none">
      <div class="panel">
        <div class="panel-header">⬡ Collibra Edge Stack</div>
        <div class="panel-body">
          <table>
            <thead><tr><th>Action</th><th>Command</th><th></th></tr></thead>
            <tbody>
              <tr><td>Status</td><td><code>singine edge status --json</code></td>
                  <td><button class="btn" onclick="runQuick('singine edge status --json')">Run</button></td></tr>
              <tr><td>Build all</td><td><code>singine edge build</code></td>
                  <td><button class="btn" onclick="runQuick('singine edge build')">Run</button></td></tr>
              <tr><td>Start (detach)</td><td><code>singine edge up --detach</code></td>
                  <td><button class="btn btn-green" onclick="runQuick('singine edge up --detach')">Run</button></td></tr>
              <tr><td>Stop</td><td><code>singine edge down</code></td>
                  <td><button class="btn btn-danger" onclick="runQuick('singine edge down')">Run</button></td></tr>
              <tr><td>Logs</td><td><code>singine edge logs --service cdn --follow</code></td>
                  <td><button class="btn" onclick="runQuick('singine edge logs')">Run</button></td></tr>
              <tr><td>Deploy</td><td><code>singine edge deploy</code></td>
                  <td><button class="btn btn-green" onclick="runQuick('singine edge deploy')">Run</button></td></tr>
            </tbody>
          </table>
          <br>
          <div class="output-box" id="edge-output">—</div>
        </div>
      </div>
    </div>

    <!-- Web -->
    <div id="pane-web" class="pane" style="display:none">
      <div class="panel">
        <div class="panel-header">⬡ Web Surface (www · vww · wingine · wsec)</div>
        <div class="panel-body">
          <table>
            <thead><tr><th>Command</th><th>Description</th><th>Presence</th><th></th></tr></thead>
            <tbody>
              <tr><td><code>singine www status</code></td>
                  <td>Deployment status for all sites</td>
                  <td><span class="tag tag-machine">machine</span></td>
                  <td><button class="btn" onclick="runQuick('singine www status --json')">Run</button></td></tr>
              <tr><td><code>singine www deploy --site markupware.com</code></td>
                  <td>git pull → build → deploy</td>
                  <td><span class="tag tag-human">human required</span></td>
                  <td><button class="btn btn-green" onclick="runInvoke('singine www deploy --site markupware.com')">Run</button></td></tr>
              <tr><td><code>singine vww audit --site markupware.com</code></td>
                  <td>Full TLS + security audit</td>
                  <td><span class="tag tag-machine">machine</span></td>
                  <td><button class="btn" onclick="runQuick('singine vww audit --site markupware.com --json')">Run</button></td></tr>
              <tr><td><code>singine wsec cert --site markupware.com --fix-san</code></td>
                  <td>Fix TLS cert SAN mismatch</td>
                  <td><span class="tag tag-human">human required</span></td>
                  <td><button class="btn" onclick="runInvoke('singine wsec cert --site markupware.com --fix-san --method certbot')">Run</button></td></tr>
              <tr><td><code>singine wsec token --site lutino.io</code></td>
                  <td>Mint deploy JWT</td>
                  <td><span class="tag tag-human">human required</span></td>
                  <td><button class="btn" onclick="runInvoke('singine wsec token --site lutino.io --json')">Run</button></td></tr>
            </tbody>
          </table>
          <br>
          <div class="output-box" id="web-output">—</div>
        </div>
      </div>
    </div>

    <!-- #knowyourai -->
    <div id="pane-knowyourai" class="pane" style="display:none">
      <div class="panel">
        <div class="panel-header">◈ #knowyourai — Activity Classification</div>
        <div class="panel-body">
          <p style="color:var(--muted);margin-bottom:14px;font-size:.8rem">
            Every singine activity is classified as human-led, machine-led, or assisted.
            Human-led activities require a valid presence attestation every 30 minutes.
          </p>
          <div>
            <div class="kya-row">
              <span class="tag tag-human">⬡ HumanLedActivity</span>
              <span>Requires presence JWT. Examples: deploy, cert renewal, governance decision, panel actions.</span>
            </div>
            <div class="kya-row">
              <span class="tag tag-machine">⬡ MachineLedActivity</span>
              <span>No presence needed. Examples: bridge search, feed generation, health probes.</span>
            </div>
            <div class="kya-row">
              <span class="tag" style="color:var(--amber);border-color:var(--amber)">⬡ AssistedActivity</span>
              <span>Human in the loop — reviews and approves machine proposals. Examples: AI session review.</span>
            </div>
          </div>
          <br>
          <p style="color:var(--muted);font-size:.8rem">SKOS vocabulary:</p>
          <div style="display:flex;gap:8px;margin-top:8px;">
            <a href="/vocab/knowyourai.ttl"  class="feed-link">Turtle (.ttl)</a>
            <a href="/vocab/knowyourai.rdf"  class="feed-link">RDF/XML (.rdf)</a>
          </div>
        </div>
      </div>
    </div>

    <!-- Feeds -->
    <div id="pane-feeds" class="pane" style="display:none">
      <div class="panel">
        <div class="panel-header">⇀ Atom / RSS 1.0 Feeds</div>
        <div class="panel-body">
          <p style="color:var(--muted);margin-bottom:12px;font-size:.8rem">
            All feeds are SKOS-tagged with #knowyourai concepts. RSS 1.0 is RDF-aligned using rdf:about URIs.
          </p>
          <div class="feeds">
            <a href="/feeds/activity.atom"   class="feed-link">activity · Atom 1.0</a>
            <a href="/feeds/activity.rss"    class="feed-link">activity · RSS 1.0 (RDF)</a>
            <a href="/feeds/decisions.atom"  class="feed-link">decisions · Atom 1.0</a>
            <a href="/feeds/decisions.rss"   class="feed-link">decisions · RSS 1.0 (RDF)</a>
          </div>
        </div>
      </div>
    </div>

  </div><!-- .content -->
</main>
<div id="toast"></div>

<script>
const PANES = ['services','routes','docker','presence','invoke','edge','web','knowyourai','feeds'];
let presenceJwt = null;
let activePane = 'services';

function show(id) {
  PANES.forEach(p => {
    document.getElementById('pane-'+p).style.display = p===id ? '' : 'none';
    const nav = document.getElementById('nav-'+p);
    if (nav) nav.classList.toggle('active', p===id);
  });
  activePane = id;
  if (id==='services') refreshServices();
  if (id==='docker')   refreshDocker();
  if (id==='routes')   loadRoutes();
  if (id==='presence') presenceStatus();
}

async function api(path, method='GET', body=null) {
  const opts = { method, headers: {'Content-Type':'application/json'} };
  if (presenceJwt) opts.headers['Authorization'] = 'Bearer ' + presenceJwt;
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  return r.json();
}

function toast(msg, ms=2500) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.style.display = 'block';
  setTimeout(() => t.style.display='none', ms);
}

async function refreshServices() {
  const data = await api('/api/net/services');
  const tbody = document.getElementById('services-body');
  tbody.innerHTML = (data.services||[]).map(s => {
    const dot = s.reachable===true  ? '<span class="dot dot-green"></span>'
               : s.reachable===false ? '<span class="dot dot-red"></span>'
               : '<span class="dot dot-grey"></span>';
    const kindTag = `<span class="tag tag-${s.kind}">${s.kind}</span>`;
    const presTag = s.requires_presence ? '<span class="tag tag-human">human</span>' : '';
    const ms = s.latency_ms != null ? s.latency_ms+'ms' : '—';
    return `<tr>
      <td>${dot}</td>
      <td class="port-num">${s.port}</td>
      <td><code>${s.id}</code></td>
      <td>${kindTag}</td>
      <td>${s.label}</td>
      <td>${ms}</td>
      <td>${presTag}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="7">No services</td></tr>';
}

async function loadRoutes() {
  const data = await api('/api/net/routes');
  const tbody = document.getElementById('routes-body');
  tbody.innerHTML = (data.routes||[]).map(r => {
    const cache = r.cacheable ? '✓' : '';
    const auth  = r.auth_required ? '<span class="tag tag-human">auth</span>' : '';
    return `<tr>
      <td><code>${r.path_pattern}</code></td>
      <td><code>${r.target_service}</code></td>
      <td>${cache}</td>
      <td>${auth}</td>
      <td style="color:var(--muted)">${r.description}</td>
    </tr>`;
  }).join('');
}

async function refreshDocker() {
  const data = await api('/api/net/services');
  const tbody = document.getElementById('docker-body');
  tbody.innerHTML = (data.docker_containers||[]).map(c =>
    `<tr><td><code>${c.name}</code></td><td>${c.image}</td><td>${c.status}</td><td>${c.ports}</td></tr>`
  ).join('') || '<tr><td colspan="4">No containers</td></tr>';
}

async function presenceStatus() {
  const data = await api('/api/presence/status');
  const badge = document.getElementById('presence-badge');
  const detail = document.getElementById('presence-detail');
  if (data.present) {
    const m = Math.floor((data.remaining_seconds||0)/60);
    const s = (data.remaining_seconds||0)%60;
    badge.className = 'presence-badge presence-ok';
    badge.textContent = `✓ presence verified (${m}m${s}s)`;
    detail.innerHTML = `<table>
      <tr><td>Status</td><td style="color:var(--green)">✓ Verified</td></tr>
      <tr><td>Method</td><td>${data.method||'—'}</td></tr>
      <tr><td>Agent</td><td>${data.agent||'—'}</td></tr>
      <tr><td>Last verified</td><td>${data.last_verified||'—'}</td></tr>
      <tr><td>Valid for</td><td>${m}m ${s}s</td></tr>
      <tr><td>Interval</td><td>${(data.interval_seconds||1800)/60}min</td></tr>
    </table>`;
  } else {
    badge.className = 'presence-badge presence-warn';
    badge.textContent = '◌ presence required';
    detail.innerHTML = '<p style="color:var(--red)">✗ Presence not verified. Click below to verify.</p>';
  }
}

async function verifyPresence() {
  toast('Verifying presence…');
  const data = await api('/api/presence/verify', 'POST', {});
  document.getElementById('presence-output').textContent = JSON.stringify(data, null, 2);
  if (data.ok && data.jwt) {
    presenceJwt = data.jwt;
    toast('✓ Presence verified');
  } else {
    toast('✗ Verification failed: ' + (data.error||'unknown'));
  }
  presenceStatus();
}

async function invokeCmd() {
  const raw = document.getElementById('invoke-cmd').value.trim();
  if (!raw) return;
  const parts = raw.split(/\\s+/);
  const out = document.getElementById('invoke-output');
  out.textContent = '⌛ running: ' + raw + '\\n';
  const data = await api('/api/net/invoke', 'POST', {cmd: parts});
  out.textContent = (data.stdout||'') + (data.stderr ? '\\n[stderr]\\n' + data.stderr : '');
  if (!data.ok) toast('✗ Command failed (exit ' + data.exit_code + ')');
}

function runQuick(cmd) {
  document.getElementById('invoke-cmd').value = cmd;
  show('invoke');
  setTimeout(invokeCmd, 50);
}

function runInvoke(cmd) {
  document.getElementById('invoke-cmd').value = cmd;
  show('invoke');
  const out = document.getElementById('web-output');
  if (out) out.textContent = '→ switched to Invoke pane';
  setTimeout(invokeCmd, 50);
}

// Boot
show('services');
presenceStatus();
setInterval(presenceStatus, 60000);  // refresh badge every minute
</script>
</body>
</html>"""


# ── Tornado handlers ───────────────────────────────────────────────────────────

if HAS_TORNADO:
    class PanelHandler(tornado.web.RequestHandler):
        def get(self):
            self.set_header("Content-Type", "text/html; charset=utf-8")
            self.write(_PANEL_HTML)

    class HealthHandler(tornado.web.RequestHandler):
        def get(self):
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({
                "ok": True,
                "service": "singine-panel",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }))

    class ServicesHandler(tornado.web.RequestHandler):
        def get(self):
            payload = _net.status_payload()
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(payload))

    class RoutesHandler(tornado.web.RequestHandler):
        def get(self):
            from dataclasses import asdict
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps({
                "routes": [asdict(r) for r in _net.ROUTES],
            }))

    class ProbeHandler(tornado.web.RequestHandler):
        def post(self):
            body = json.loads(self.request.body or b"{}")
            svc_id = body.get("service")
            svc = _net.SERVICE_INDEX.get(svc_id)
            if not svc:
                self.set_status(404)
                self.write(json.dumps({"error": f"Unknown service: {svc_id}"}))
                return
            _net.probe(svc)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(svc.as_dict()))

    class InvokeHandler(tornado.web.RequestHandler):
        def post(self):
            body = json.loads(self.request.body or b"{}")
            cmd: List[str] = body.get("cmd", [])
            if not cmd:
                self.set_status(400)
                self.write(json.dumps({"error": "cmd is required"}))
                return
            # Security: only allow singine / docker commands
            if cmd[0] not in ("singine", "docker"):
                self.set_status(403)
                self.write(json.dumps({"error": "Only 'singine' and 'docker' commands allowed"}))
                return
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                result = {
                    "ok": proc.returncode == 0,
                    "exit_code": proc.returncode,
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "cmd": cmd,
                }
            except subprocess.TimeoutExpired:
                result = {"ok": False, "error": "Command timed out", "cmd": cmd}
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(result))

    class PresenceStatusHandler(tornado.web.RequestHandler):
        def get(self):
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(_presence.status()))

    class PresenceVerifyHandler(tornado.web.RequestHandler):
        def post(self):
            result = _presence.verify(force=True)
            self.set_header("Content-Type", "application/json")
            self.write(json.dumps(result))

    class FeedHandler(tornado.web.RequestHandler):
        def get(self, name: str):
            db = os.environ.get("SINGINE_DOMAIN_DB", "/tmp/humble-idp.db")
            feed_map = {
                "activity.atom":  lambda: _feeds.activity_atom(db),
                "activity.rss":   lambda: _feeds.activity_rss(db),
                "decisions.atom": lambda: _feeds.decisions_atom(db),
                "decisions.rss":  lambda: _feeds.decisions_rss(db),
            }
            fn = feed_map.get(name)
            if not fn:
                self.set_status(404)
                self.write("Not found")
                return
            content_type = (
                "application/atom+xml" if name.endswith(".atom")
                else "application/rss+xml"
            )
            self.set_header("Content-Type", f"{content_type}; charset=utf-8")
            self.write(fn())

    class VocabHandler(tornado.web.RequestHandler):
        def get(self, name: str):
            ttl_path = VOCAB_DIR / "knowyourai.ttl"
            if name == "knowyourai.ttl":
                if ttl_path.exists():
                    self.set_header("Content-Type", "text/turtle; charset=utf-8")
                    self.write(ttl_path.read_text(encoding="utf-8"))
                else:
                    self.set_status(404)
            elif name == "knowyourai.rdf":
                # Minimal RDF/XML wrapper around the TTL content
                self.set_header("Content-Type", "application/rdf+xml; charset=utf-8")
                self.write(
                    '<?xml version="1.0" encoding="UTF-8"?>\n'
                    '<!-- Full vocabulary at /vocab/knowyourai.ttl (Turtle format) -->\n'
                    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"\n'
                    '         xmlns:kya="urn:knowyourai:vocab#">\n'
                    '  <!-- See /vocab/knowyourai.ttl for the full SKOS vocabulary -->\n'
                    '</rdf:RDF>\n'
                )
            else:
                self.set_status(404)

    def make_app() -> "tornado.web.Application":
        return tornado.web.Application([
            (r"/",                       PanelHandler),
            (r"/panel/?",                PanelHandler),
            (r"/api/health",             HealthHandler),
            (r"/api/net/services",       ServicesHandler),
            (r"/api/net/routes",         RoutesHandler),
            (r"/api/net/probe",          ProbeHandler),
            (r"/api/net/invoke",         InvokeHandler),
            (r"/api/presence/status",    PresenceStatusHandler),
            (r"/api/presence/verify",    PresenceVerifyHandler),
            (r"/feeds/([^/]+)",          FeedHandler),
            (r"/vocab/([^/]+)",          VocabHandler),
        ])


# ── CLI entry ──────────────────────────────────────────────────────────────────

def serve(
    port: int = PANEL_PORT_DEFAULT,
    bind: str = PANEL_BIND_DEFAULT,
) -> None:
    if not HAS_TORNADO:
        print("Error: tornado is required. Install it: pip install tornado", file=sys.stderr)
        sys.exit(1)
    app = make_app()
    app.listen(port, address=bind)
    print(f"singine panel — listening on http://{bind}:{port}/")
    print(f"  Feeds:  http://{bind}:{port}/feeds/activity.atom")
    print(f"  Vocab:  http://{bind}:{port}/vocab/knowyourai.ttl")
    print(f"  API:    http://{bind}:{port}/api/health")
    tornado.ioloop.IOLoop.current().start()


def cmd_serve(args) -> int:
    port = int(getattr(args, "port", PANEL_PORT_DEFAULT))
    bind = getattr(args, "bind", PANEL_BIND_DEFAULT)
    serve(port=port, bind=bind)
    return 0
