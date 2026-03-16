#!/usr/bin/env python3
"""
singine_shape.py — HarfBuzz + fonttools + cairocffi typographic experiment.

Shapes 'Singine' (Latin, LTR) and 'سین‌جین' (Persian, RTL) via HarfBuzz,
extracts glyph outlines through fonttools, renders to SVG via cairocffi.

Stack:
  uharfbuzz  →  OpenType shaping  (GSUB/GPOS, Arabic joining, ZWNJ)
  fonttools  →  glyph outline extraction  (CFF/TT contours → SVG path d=)
  cairocffi  →  2-D layout, Y-flip, fill  (SVG surface output)
"""

import re
import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
import cairocffi as cairo

FONT_LATIN   = "/System/Library/Fonts/SFNS.ttf"
FONT_PERSIAN = "/Users/skh/Library/Fonts/Amiri-Regular.ttf"

W, H = 900, 320
OUT  = "singine_experiment_02.svg"


# ── HarfBuzz shaping ──────────────────────────────────────────────────────────
def hb_shape(font_path, text, direction="ltr", script="Latn",
             lang="en", features=None):
    blob = hb.Blob.from_file_path(font_path)
    face = hb.Face(blob)
    font = hb.Font(face)
    buf  = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    buf.direction = direction
    buf.script    = script
    buf.language  = lang           # plain string — uharfbuzz ≥ 0.36
    hb.shape(font, buf, features or {})
    return buf.glyph_infos, buf.glyph_positions, face.upem


# ── fonttools: glyph name → SVG path string ───────────────────────────────────
def glyph_path(ft_font, name):
    try:
        pen = SVGPathPen(ft_font.getGlyphSet())
        ft_font.getGlyphSet()[name].draw(pen)
        return pen.getCommands()   # e.g. "M 100 200 L 300 200 …"
    except Exception:
        return ""


# ── Build positioned run ──────────────────────────────────────────────────────
def build_run(font_path, text, pt_size, direction="ltr",
              script="Latn", lang="en", features=None):
    infos, positions, upem = hb_shape(
        font_path, text, direction, script, lang, features)
    ft    = TTFont(font_path)
    order = ft.getGlyphOrder()
    scale = pt_size / upem

    # Collect raw glyph data first
    glyphs = []
    total_w = 0.0
    for info, pos in zip(infos, positions):
        gid  = info.codepoint
        name = order[gid] if gid < len(order) else ".notdef"
        adv  = pos.x_advance * scale
        glyphs.append({
            "path":    glyph_path(ft, name),
            "x_off":   pos.x_offset * scale,
            "y":       pos.y_offset * scale,
            "scale":   scale,
            "adv":     adv,
            "name":    name,
        })
        total_w += adv

    # Assign x positions:
    # LTR → cursor accumulates left-to-right (glyph[0] is visual-left)
    # RTL → HarfBuzz glyph[0] is visual-right; walk right-to-left from total_w
    run = []
    if direction == "rtl":
        cx = total_w
        for g in glyphs:
            cx -= g["adv"]
            run.append({**g, "x": cx + g["x_off"]})
    else:
        cx = 0.0
        for g in glyphs:
            run.append({**g, "x": cx + g["x_off"]})
            cx += g["adv"]

    return run, total_w   # (glyphs, total advance width)


# ── SVG path d="" → Cairo path replay ────────────────────────────────────────
_TOK = re.compile(r'([MmLlHhVvCcSsQqTtZz])|([+-]?(?:\d*\.\d+|\d+\.?)(?:[eE][+-]?\d+)?)')
_SZ  = {'M':2,'L':2,'H':1,'V':1,'C':6,'Q':4,'S':4,'T':2,'Z':0}

def cairo_replay(ctx, d):
    if not d:
        return
    cmd, nums = None, []

    def emit(c, n):
        pt = lambda: ctx.get_current_point()
        if   c == 'M': ctx.move_to(n[0], n[1])
        elif c == 'L': ctx.line_to(n[0], n[1])
        elif c == 'H': ctx.line_to(n[0], pt()[1])
        elif c == 'V': ctx.line_to(pt()[0], n[0])
        elif c == 'C': ctx.curve_to(n[0],n[1],n[2],n[3],n[4],n[5])
        elif c == 'Q':
            x0,y0 = pt()
            ctx.curve_to(x0+2/3*(n[0]-x0), y0+2/3*(n[1]-y0),
                         n[2]+2/3*(n[0]-n[2]), n[3]+2/3*(n[1]-n[3]),
                         n[2], n[3])
        elif c == 'Z': ctx.close_path()

    for m in _TOK.finditer(d):
        if m.group(1):                          # command letter
            c = m.group(1).upper()
            if cmd and (c != cmd or c == 'M'):  # flush on new command
                pass                            # already flushed below
            cmd, nums = c, []
            if c == 'Z':
                emit('Z', [])
                cmd = None
        else:                                   # coordinate number
            nums.append(float(m.group(2)))
            if cmd and cmd in _SZ and _SZ[cmd] and len(nums) >= _SZ[cmd]:
                emit(cmd, nums)
                nums = []                       # implicit repetition


# ── Paint a shaped run onto Cairo context ────────────────────────────────────
def paint_run(ctx, run, bx, by, color=(0.08, 0.08, 0.10)):
    """bx,by = baseline origin (Y-down canvas). Font glyphs are Y-up → flip."""
    ctx.save()
    ctx.set_source_rgb(*color)
    for g in run:
        if not g["path"]:
            continue
        ctx.save()
        ctx.translate(bx + g["x"], by - g["y"])
        ctx.scale(g["scale"], -g["scale"])
        ctx.new_path()
        cairo_replay(ctx, g["path"])
        ctx.fill()
        ctx.restore()
    ctx.restore()


# ── LaTeX output (XeLaTeX + fontspec + bidi) ─────────────────────────────────
def write_latex(out_tex="singine_experiment.tex"):
    """
    Emit a XeLaTeX document that typesets the bilingual lockup.
    Compile with:
        xelatex singine_experiment.tex
    Requires: fontspec, bidi (or polyglossia), xcolor packages.
    The Persian font path must be accessible to XeLaTeX.
    """
    latin_font   = FONT_LATIN.replace("\\", "/")
    persian_font = FONT_PERSIAN.replace("\\", "/")

    latin_dir   = "/".join(latin_font.split("/")[:-1]) + "/"
    latin_file  = latin_font.split("/")[-1]
    persian_dir = "/".join(persian_font.split("/")[:-1]) + "/"
    persian_file = persian_font.split("/")[-1]

    tex = (r"""\documentclass[a4paper]{article}
\usepackage{fontspec}
\usepackage{bidi}
\usepackage{xcolor}
\usepackage[margin=2cm]{geometry}

% Latin font -- SF NS (system font path)
\newfontfamily\latinfont[
  Path=LATIN_DIR,
  Ligatures=TeX,
  Kerning=On,
  Numbers=OldStyle
]{LATIN_FILE}

% Persian / Arabic font -- Amiri
\newfontfamily\persianfont[
  Path=PERSIAN_DIR,
  Script=Arabic,
  Language=Persian,
  Ligatures=Required,
  RawFeature={+mark}
]{PERSIAN_FILE}

\definecolor{inkblack}{rgb}{0.08,0.08,0.10}
\definecolor{manuredred}{rgb}{0.52,0.11,0.07}
\definecolor{hairline}{rgb}{0.35,0.30,0.28}

\pagestyle{empty}

\begin{document}
\begin{center}

  % Latin name
  {\latinfont\fontsize{90pt}{108pt}\selectfont
   \textcolor{inkblack}{Singine}}

  \vspace{6pt}
  \textcolor{hairline}{\rule{0.7\linewidth}{0.4pt}}
  \vspace{6pt}

  % Persian name -- ZWNJ keeps morphemes distinct
  \begin{RTL}
    {\persianfont\fontsize{82pt}{98pt}\selectfont
     \textcolor{manuredred}{""" + "\u0633\u06cc\u0646\u200c\u062c\u06cc\u0646" + r"""}}
  \end{RTL}

\end{center}
\end{document}
""")
    tex = (tex
           .replace("LATIN_DIR",    latin_dir)
           .replace("LATIN_FILE",   latin_file)
           .replace("PERSIAN_DIR",  persian_dir)
           .replace("PERSIAN_FILE", persian_file)
           )

    with open(out_tex, "w", encoding="utf-8") as f:
        f.write(tex)
    print(f"→ {out_tex}  (compile with: xelatex {out_tex})")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    surface = cairo.SVGSurface(OUT, W, H)
    ctx     = cairo.Context(surface)

    # warm off-white background
    ctx.set_source_rgb(0.97, 0.96, 0.94)
    ctx.paint()

    PT_LAT = 90
    PT_PER = 82

    # Latin: "Singine"
    lat, lat_w = build_run(
        FONT_LATIN, "Singine", PT_LAT,
        features={"kern": True, "liga": True, "calt": True},
    )

    # Persian: سین‌جین  (U+200C ZWNJ between سین and جین — keeps the two
    # morphemes visually separate while still shaping correctly)
    per, per_w = build_run(
        FONT_PERSIAN, "سین\u200cجین", PT_PER,
        direction="rtl", script="Arab", lang="fa",
        features={"kern": True, "liga": True, "calt": True, "mark": True},
    )

    GAP = 28
    BL_LAT = H / 2 - GAP / 2        # upper baseline
    BL_PER = H / 2 + PT_PER + GAP / 2  # lower baseline

    # centre both runs
    BX_LAT = (W - lat_w) / 2
    BX_PER = (W - per_w) / 2

    # hairline rule
    ctx.save()
    ctx.set_source_rgba(0.35, 0.30, 0.28, 0.22)
    ctx.set_line_width(0.75)
    ctx.move_to(60, H / 2)
    ctx.line_to(W - 60, H / 2)
    ctx.stroke()
    ctx.restore()

    # Latin: near-black
    paint_run(ctx, lat, BX_LAT, BL_LAT, color=(0.08, 0.08, 0.10))
    # Persian: deep manuscript red
    paint_run(ctx, per, BX_PER, BL_PER, color=(0.52, 0.11, 0.07))

    surface.finish()
    print(f"→ {OUT}  ({W}×{H})")
    print(f"  Latin   'Singine'  {lat_w:.0f}px  {len(lat)} glyphs")
    print(f"  Persian 'سین‌جین'  {per_w:.0f}px  {len(per)} glyphs")
    for g in per:
        print(f"    {g['name']:32s} adv={g['adv']:6.1f}  path={'yes' if g['path'] else 'NO'}")

    write_latex()


if __name__ == "__main__":
    main()
