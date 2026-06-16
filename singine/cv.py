"""singine cv — CV generation and serving utilities."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────

_HERE     = Path(__file__).parent                            # singine/singine/
_BIN      = _HERE.parent / "bin"                             # singine/bin/
_WS       = _HERE.parent.parent.parent.parent                # ws/
_SILKPAGE = _WS / "silkpage" / "main" / "silkpage" / "www"  # ws/silkpage/.../www
_CV_HTML  = _SILKPAGE / "cv" / "index.html"
_CV_MD    = _WS / "cv-sina-heshmati.md"

# ── serve ─────────────────────────────────────────────────────────────────────

def serve(port: int = 4242, webroot: str | None = None) -> None:
    """Launch SingineServe.java as the appserver for SilkPage documents."""
    java_server = _BIN / "SingineServe.java"
    root = webroot or str(_SILKPAGE)

    java_home = os.environ.get("JAVA_HOME", "")
    java = shutil.which("java") or (java_home + "/bin/java" if java_home else "java")

    cmd = [java, str(java_server), str(port), root]
    print(f"singine serve: launching SingineServe on :{port}")
    print(f"  url  http://localhost:{port}/")
    print(f"  cv   http://localhost:{port}/cv/")
    subprocess.run(cmd, check=False)

# ── html ─────────────────────────────────────────────────────────────────────

def html(output: str | None = None) -> str:
    """Print the CV HTML path, or copy it to output."""
    if not _CV_HTML.exists():
        print(f"error: CV HTML not found: {_CV_HTML}", file=sys.stderr)
        sys.exit(1)
    if output:
        shutil.copy2(_CV_HTML, output)
        print(f"CV HTML → {output}")
        return output
    print(str(_CV_HTML))
    return str(_CV_HTML)

# ── markdown ─────────────────────────────────────────────────────────────────

def md(output: str | None = None) -> str:
    """Print the CV Markdown path, or copy it to output."""
    if not _CV_MD.exists():
        print(f"error: CV Markdown not found: {_CV_MD}", file=sys.stderr)
        sys.exit(1)
    if output:
        shutil.copy2(_CV_MD, output)
        print(f"CV Markdown → {output}")
        return output
    print(str(_CV_MD))
    return str(_CV_MD)

# ── RTF ──────────────────────────────────────────────────────────────────────

_RTF_HEADER = (
    r"{\rtf1\ansi\ansicpg1252\deff0"
    r"{\fonttbl"
    r"{\f0\fswiss\fcharset0 Arial;}"
    r"{\f1\fmodern\fcharset0 Courier New;}"
    r"}"
    r"{\colortbl;\red74\green111\blue165;}"   # cf1 = accent blue
    r"\widowctrl\hyphauto"
    r"\margl1440\margr1440\margt1080\margb1080"
    "\n"
)
_RTF_FOOTER = "}"


def _esc(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "{":
            out.append("\\{")
        elif ch == "}":
            out.append("\\}")
        elif ord(ch) > 127:
            out.append(f"\\u{ord(ch)}?")
        else:
            out.append(ch)
    return "".join(out)


def _inline(line: str) -> str:
    """Apply bold/italic inline markup, escaping everything else."""
    # Process bold before italic to handle **...*
    line = re.sub(r"\*\*(.+?)\*\*", lambda m: r"{\b " + _esc(m.group(1)) + "}", line)
    line = re.sub(r"\*(.+?)\*",     lambda m: r"{\i " + _esc(m.group(1)) + "}", line)
    # backtick code spans
    line = re.sub(r"`(.+?)`",       lambda m: r"{\f1 " + _esc(m.group(1)) + "}", line)
    return line


def _md_to_rtf(text: str) -> str:
    lines = text.splitlines()
    parts: list[str] = [_RTF_HEADER]

    for line in lines:
        s = line.strip()
        if not s:
            parts.append(r"\par" + "\n")
            continue

        if s.startswith("# "):
            parts.append(r"{\pard\sb240\f0\fs40\b " + _esc(s[2:]) + r"\par}" + "\n")
        elif s.startswith("## "):
            parts.append(r"{\pard\sb200\f0\fs28\b\cf1 " + _esc(s[3:]) + r"\par}" + "\n")
        elif s.startswith("### "):
            parts.append(r"{\pard\sb160\f0\fs24\b " + _esc(s[4:]) + r"\par}" + "\n")
        elif s.startswith("#### "):
            parts.append(r"{\pard\sb120\f0\fs22\b\i " + _esc(s[5:]) + r"\par}" + "\n")
        elif s.startswith("---"):
            parts.append(r"{\pard\sb60\brdrb\brdrs\brdrw10\brsp20 \par}" + "\n")
        elif s.startswith("- "):
            parts.append(r"{\pard\li360\fi-180\f0\fs22\bullet  " + _inline(s[2:]) + r"\par}" + "\n")
        elif s.startswith("|"):
            # table row: skip pure separator rows (---)
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue
            row = "    ".join(_esc(c) for c in cells if c)
            if row:
                parts.append(r"{\pard\f1\fs20 " + row + r"\par}" + "\n")
        else:
            parts.append(r"{\pard\f0\fs22 " + _inline(line) + r"\par}" + "\n")

    parts.append(_RTF_FOOTER)
    return "".join(parts)


def rtf(output: str | None = None) -> str:
    """Generate an RTF version of the CV from the Markdown source."""
    if not _CV_MD.exists():
        print(f"error: CV Markdown not found: {_CV_MD}", file=sys.stderr)
        sys.exit(1)
    text    = _CV_MD.read_text(encoding="utf-8")
    rtf_doc = _md_to_rtf(text)
    dest    = output or str(Path.home() / "Downloads" / "cv-sina-heshmati.rtf")
    Path(dest).write_text(rtf_doc, encoding="utf-8")
    print(f"CV RTF → {dest}")
    return dest

# ── PDF ──────────────────────────────────────────────────────────────────────

def pdf(output: str | None = None) -> str:
    """Generate a PDF version of the CV via Chrome headless (A4 layout)."""
    dest = output or str(Path.home() / "Downloads" / "cv-sina-heshmati.pdf")

    if not _CV_HTML.exists():
        print(f"error: CV HTML not found: {_CV_HTML}", file=sys.stderr)
        sys.exit(1)

    chrome_candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("chromium") or "",
        shutil.which("google-chrome") or "",
        shutil.which("chromium-browser") or "",
    ]
    for chrome in chrome_candidates:
        if chrome and Path(chrome).exists():
            cmd = [
                chrome,
                "--headless", "--disable-gpu",
                f"--print-to-pdf={dest}",
                "--print-to-pdf-no-header",
                "--no-margins",
                str(_CV_HTML),
            ]
            subprocess.run(cmd, check=True)
            print(f"CV PDF → {dest}")
            return dest

    wk = shutil.which("wkhtmltopdf")
    if wk:
        subprocess.run([wk, "-s", "A4", str(_CV_HTML), dest], check=True)
        print(f"CV PDF → {dest}")
        return dest

    print("error: no PDF renderer found. Install Google Chrome or wkhtmltopdf.", file=sys.stderr)
    print(f"  Or open {_CV_HTML} in a browser and use File → Print → Save as PDF.", file=sys.stderr)
    sys.exit(1)
