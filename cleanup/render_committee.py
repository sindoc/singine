#!/usr/bin/env python3
"""
render_committee.py — Generate the committee HTML report from committee-results.json.

Produces report/committee-report.html — a self-contained page that:
  - embeds all CSS inline (works without cdn.example.org)
  - references cdn.example.org for full CSS/JS in production
  - shows two sections: disk analysis + governance state
  - has copy-to-clipboard for every singine command
  - is ready to paste into a silkpage XML document or serve directly

Usage:
  python3 render_committee.py [--in report/committee-results.json] [--out report/committee-report.html]

singine invocation:
  singine runtime exec-external python3 cleanup/render_committee.py
"""

from __future__ import annotations
import argparse
import html
import json
import sys
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPORT_DIR = SCRIPT_DIR / "report"

# ── Inline critical CSS (works without CDN) ──────────────────────────────────

_CSS = """
:root{--safe:#1a7a4a;--review:#b45309;--keep:#374151;--bg:#f9fafb;
      --border:#e5e7eb;--mono:"JetBrains Mono","Fira Code",ui-monospace,monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:var(--bg);
     color:#111827;line-height:1.6;font-size:15px}
header{background:#111827;color:#f9fafb;padding:1.5rem 2rem}
header h1{font-size:1.4rem;font-weight:700}
.meta{font-size:.82rem;color:#9ca3af;margin-top:.25rem}
main{max-width:1300px;margin:0 auto;padding:2rem}
h2{font-size:1.1rem;font-weight:600;margin:1.75rem 0 .6rem;
   border-bottom:1px solid var(--border);padding-bottom:.4rem}
h3{font-size:.95rem;font-weight:600;margin:.75rem 0 .4rem;color:#374151}
p,li{margin-bottom:.4rem}
.banner{background:#111827;color:#f9fafb;padding:.65rem 1.1rem;
        border-radius:5px;margin-bottom:1rem;font-weight:600;font-size:.9rem}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1.5rem}
.card{background:#fff;border:1px solid var(--border);border-radius:6px;padding:1rem}
.card .val{font-size:2rem;font-weight:700;color:#111827}
.card .lbl{font-size:.8rem;color:#6b7280;margin-top:.1rem}
table{width:100%;border-collapse:collapse;font-size:.85rem;margin-bottom:1.5rem}
th{background:#111827;color:#f9fafb;text-align:left;padding:.55rem .75rem;white-space:nowrap}
td{padding:.55rem .75rem;border-bottom:1px solid var(--border);vertical-align:top}
tr:hover td{background:#f3f4f6}
td.size{font-weight:600;white-space:nowrap}
td.path code{font-family:var(--mono);font-size:.78rem;color:#374151}
.badge-safe  {color:var(--safe);font-weight:600}
.badge-review{color:var(--review);font-weight:600}
.badge-keep  {color:var(--keep)}
tr.r-safe   td:first-child{border-left:3px solid var(--safe)}
tr.r-review td:first-child{border-left:3px solid var(--review)}
td.cmd{max-width:480px}
code.sc{display:block;font-family:var(--mono);font-size:.76rem;
         background:#1f2937;color:#a7f3d0;padding:.3rem .55rem;border-radius:3px;
         white-space:pre-wrap;word-break:break-all;margin-bottom:.3rem}
.cp{font-size:.72rem;padding:.18rem .55rem;background:#374151;color:#f9fafb;
    border:none;border-radius:3px;cursor:pointer;transition:background .15s}
.cp:hover{background:#111827}
.cp.ok{background:var(--safe)}
details summary{font-size:.75rem;color:#6b7280;cursor:pointer}
code.sh,code.wn{display:block;font-family:var(--mono);font-size:.74rem;
                background:#f3f4f6;color:#374151;padding:.28rem .45rem;
                border-radius:3px;white-space:pre-wrap;word-break:break-all;margin-top:.2rem}
.note{background:#fffbeb;border-left:3px solid #f59e0b;
      padding:.55rem .85rem;border-radius:0 4px 4px 0;font-size:.83rem;margin:.5rem 0}
.gov-rule{background:#fff;border:1px solid var(--border);border-radius:5px;
          padding:.75rem 1rem;margin-bottom:.75rem}
.gov-rule .gid{font-family:var(--mono);font-weight:700;color:#111827;font-size:.88rem}
.gov-rule .gtitle{font-weight:600;margin-left:.5rem}
.gov-rule .gapplies{font-size:.8rem;color:#6b7280;margin-top:.15rem}
.gov-rule .grule{font-size:.83rem;margin-top:.35rem}
.empty-db{background:#fff;border:2px dashed var(--border);border-radius:6px;
          padding:1.5rem;text-align:center;color:#6b7280}
.empty-db code{font-family:var(--mono);font-size:.82rem;background:#f3f4f6;
               padding:.25rem .5rem;border-radius:3px}
footer{text-align:center;padding:1.5rem;color:#6b7280;font-size:.8rem;
       border-top:1px solid var(--border);margin-top:3rem}
footer a{color:#374151}
"""

_JS = """
document.querySelectorAll('.cp[data-cmd]').forEach(btn=>{
  btn.addEventListener('click',()=>{
    const cmd=btn.dataset.cmd;
    const copy=txt=>{try{navigator.clipboard.writeText(txt).catch(()=>{})}catch(e){}
      const ta=document.createElement('textarea');ta.value=txt;
      ta.style.cssText='position:fixed;opacity:0';document.body.appendChild(ta);
      ta.select();document.execCommand('copy');document.body.removeChild(ta)};
    copy(cmd);btn.textContent='Copied!';btn.classList.add('ok');
    setTimeout(()=>{btn.textContent='Copy';btn.classList.remove('ok')},2000);
  });
});
"""


# ── HTML helpers ─────────────────────────────────────────────────────────────

def e(s: object) -> str:
    return html.escape(str(s), quote=True)


def badge(risk: str) -> str:
    labels = {"safe": "✓ safe", "review": "⚠ review", "keep": "· keep"}
    return f'<span class="badge-{e(risk)}">{e(labels.get(risk, risk))}</span>'


def copy_btn(cmd: str) -> str:
    return (f'<button class="cp" data-cmd="{e(cmd)}" aria-label="Copy singine command">'
            f'Copy</button>')


# ── Disk section ─────────────────────────────────────────────────────────────

def disk_section(disk: dict) -> str:
    items = disk.get("items", [])
    total = disk.get("total_reclaimable_human", "?")

    rows_html = []
    for it in items:
        if it.get("size_bytes", -1) < 0:
            continue  # skip not-found
        risk = it.get("risk", "keep")
        sc   = it.get("singine_cmd", "")
        sh   = it.get("shell_cmd", "")
        wn   = it.get("win_cmd", "")
        note = it.get("notes", "")
        rows_html.append(f"""
    <tr class="r-{e(risk)}">
      <td class="size">{e(it.get('size_human','?'))}</td>
      <td class="label">{e(it.get('label',''))}</td>
      <td class="path"><code>{e(it.get('path',''))}</code></td>
      <td class="risk">{badge(risk)}</td>
      <td class="cmd">
        <code class="sc" id="cmd-{e(it.get('id',''))}">{e(sc)}</code>
        {copy_btn(sc)}
        <details><summary>shell / PowerShell</summary>
          <code class="sh">{e(sh)}</code>
          <code class="wn">{e(wn)}</code>
        </details>
        {f'<p style="font-size:.78rem;color:#6b7280;margin-top:.3rem">{e(note)}</p>' if note else ''}
      </td>
    </tr>""")

    n_safe   = sum(1 for it in items if it.get("risk") == "safe"   and it.get("size_bytes", -1) >= 0)
    n_review = sum(1 for it in items if it.get("risk") == "review" and it.get("size_bytes", -1) >= 0)

    return f"""
<section id="disk">
  <h2>1 · Disk Space Analysis</h2>
  <div class="banner">Total reclaimable: {e(total)}</div>
  <div class="grid2">
    <div class="card"><div class="val">{e(n_safe)}</div><div class="lbl">Safe to delete immediately</div></div>
    <div class="card"><div class="val">{e(n_review)}</div><div class="lbl">Require review before deletion</div></div>
  </div>
  <table>
    <thead><tr>
      <th>Size</th><th>Label</th><th>Path</th><th>Risk</th><th>singine Command</th>
    </tr></thead>
    <tbody>{''.join(rows_html)}</tbody>
  </table>
  <div class="note">
    <strong>To execute:</strong>
    copy a singine command above, then paste it into a terminal where
    <code>singine</code> is on PATH (<code>npm install -g singine</code>).
    <em>Review</em> items will trigger GOV-007 confirmation before deletion.
    All deletions are logged via GOV-001 to <code>report/audit.log</code>.
  </div>
</section>"""


# ── Governance section ────────────────────────────────────────────────────────

def gov_section(gov: dict) -> str:
    db_state = gov.get("db_state", "unknown")
    rules    = gov.get("rules", [])
    note     = gov.get("note", "")
    summary  = gov.get("summary", {})
    tables   = gov.get("tables", {})

    rules_html = "".join(f"""
    <div class="gov-rule">
      <span class="gid">{e(r['id'])}</span>
      <span class="gtitle">{e(r['title'])}</span>
      <div class="gapplies">Applies: {e(r['applies'])}</div>
      <div class="grule">{e(r['rule'])}</div>
    </div>""" for r in rules)

    if db_state == "not_initialized":
        db_html = f"""
    <div class="empty-db">
      <p><strong>Database not yet seeded</strong></p>
      <p>No runtime data to report. Initialize with:</p>
      <p><code>cd gh/sync-logseq &amp;&amp; npm install &amp;&amp; tsx src/cli/index.ts seed</code></p>
      {f'<p style="margin-top:.5rem;font-size:.82rem">{e(note)}</p>' if note else ''}
    </div>"""
    else:
        open_tasks = tables.get("human_tasks_open", [])
        failed_ex  = tables.get("executions_failed", [])

        task_rows = "".join(
            f"<tr><td>{e(t.get('id',''))}</td><td>{e(t.get('title',''))}</td>"
            f"<td>{e(t.get('priority',''))}</td><td>{e(t.get('due_at',''))}</td></tr>"
            for t in open_tasks
        ) or "<tr><td colspan='4' style='color:#6b7280'>No open tasks</td></tr>"

        fail_rows = "".join(
            f"<tr><td>{e(f.get('id',''))}</td><td>{e(f.get('action_id',''))}</td>"
            f"<td>{e(f.get('status',''))}</td><td>{e(f.get('error',''))}</td></tr>"
            for f in failed_ex
        ) or "<tr><td colspan='4' style='color:#6b7280'>None</td></tr>"

        db_html = f"""
    <div class="grid2">
      {''.join(f'<div class="card"><div class="val">{e(v)}</div><div class="lbl">{e(k.replace("_"," "))}</div></div>' for k,v in summary.items())}
    </div>
    <h3>Open Human Tasks (GOV-004)</h3>
    <table><thead><tr><th>ID</th><th>Title</th><th>Priority</th><th>Due</th></tr></thead>
    <tbody>{task_rows}</tbody></table>
    <h3>Failed / Awaiting Human Executions</h3>
    <table><thead><tr><th>Execution ID</th><th>Action</th><th>Status</th><th>Error</th></tr></thead>
    <tbody>{fail_rows}</tbody></table>"""

    return f"""
<section id="governance">
  <h2>2 · singine Governance State</h2>
  <h3>Database — <code style="font-size:.85rem">{e(gov.get('db_path','?'))}</code></h3>
  {db_html}
  <h3>Active Governance Rules ({len(rules)})</h3>
  {rules_html}
</section>"""


# ── Full page ─────────────────────────────────────────────────────────────────

def render(payload: dict) -> str:
    generated = payload.get("generated_at", "")
    disk = payload["result_sets"]["disk"]
    gov  = payload["result_sets"]["governance"]

    try:
        ts = datetime.fromisoformat(generated.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        ts = generated

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Committee Report — Disk + Governance</title>
  <!-- CDN production assets (overrides inline styles) -->
  <link rel="stylesheet" href="//cdn.example.org/assets/css/cleanup.css" media="print" onload="this.media='all'"/>
  <style>{_CSS}</style>
</head>
<body>
<header>
  <h1>Committee Report — Disk Space &amp; Governance State</h1>
  <p class="meta">Generated {e(ts)} · singine cleanup pipeline · <a href="//cdn.example.org" style="color:#9ca3af">cdn.example.org</a></p>
</header>
<main>
  {disk_section(disk)}
  {gov_section(gov)}
</main>
<footer>
  Generated by <code>cleanup/collect.py</code> +
  <code>cleanup/render_committee.py</code> ·
  singine + silkpage ·
  <a href="//cdn.example.org/cleanup.html">web view</a>
</footer>
<script>{_JS}</script>
</body>
</html>"""


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in",  dest="infile",
                        default=str(REPORT_DIR / "committee-results.json"))
    parser.add_argument("--out", dest="outfile",
                        default=str(REPORT_DIR / "committee-report.html"))
    args = parser.parse_args()

    inpath  = Path(args.infile)
    outpath = Path(args.outfile)

    if not inpath.exists():
        print(f"ERROR: {inpath} not found. Run collect.py first.", file=sys.stderr)
        sys.exit(1)

    payload = json.loads(inpath.read_text(encoding="utf-8"))
    html_out = render(payload)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    outpath.write_text(html_out, encoding="utf-8")
    print(f"written: {outpath}", file=sys.stderr)
    print(json.dumps({"ok": True, "output": str(outpath), "size_bytes": len(html_out)}))


if __name__ == "__main__":
    main()
