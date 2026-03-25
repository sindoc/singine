"""Persian/Arabic font proofing and showcase document generation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "target" / "farsi-proof"
INK_ROOT = Path("/Users/skh/ws/git/javad/ink")
INK_PROFILE_DIR = INK_ROOT / "profiles" / "Persian-Gulf"
INK_MACROS_DIR = INK_ROOT / "macros"
INK_STYLESHEET_DIR = INK_ROOT / "stylesheets"
PERSIAN_GULF_STY = INK_PROFILE_DIR / "Persian-Gulf.sty"

DEFAULT_SPECIMEN_FONTS = [
    "Amiri",
    "Geeza Pro",
    "Al Bayan",
    "Damascus",
    "Baghdad",
    "Tahoma",
]
DEFAULT_HB_FONT = "Noto Naskh Arabic"
DEFAULT_SHOWCASE_FONT = "Amiri"


@dataclass(frozen=True)
class FontRecord:
    request: str
    family: str
    style: str
    file: str
    directory: str
    filename: str
    tex_safe_file: bool


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _slug(text: str) -> str:
    chars = []
    previous_dash = False
    for ch in text.lower():
        if ch.isalnum():
            chars.append(ch)
            previous_dash = False
        elif not previous_dash:
            chars.append("-")
            previous_dash = True
    value = "".join(chars).strip("-")
    return value or "proof"


def _escape_tex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "%": r"\%",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
    }
    value = text
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value


def _latex_suffix(index: int) -> str:
    chars: List[str] = []
    value = index
    while value > 0:
        value -= 1
        chars.append(chr(ord("a") + (value % 26)))
        value //= 26
    return "".join(reversed(chars))


def _run(args: Sequence[str], env: Dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, env=env, cwd=cwd, check=False)


def _texinputs_env() -> Dict[str, str]:
    env = os.environ.copy()
    pieces = [str(INK_PROFILE_DIR), str(INK_MACROS_DIR), str(INK_STYLESHEET_DIR)]
    existing = env.get("TEXINPUTS", "")
    env["TEXINPUTS"] = os.pathsep.join(pieces + ([existing] if existing else [""]))
    env.setdefault("TEXMFVAR", "/tmp/texmf-var")
    return env


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(f"required binary not found on PATH: {name}")
    return path


def resolve_font(family: str) -> FontRecord:
    _require_binary("fc-match")
    proc = _run([
        "fc-match",
        "-f",
        "%{family[0]}\t%{style[0]}\t%{file}\n",
        f"{family}:lang=fa",
    ])
    line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    parts = line.split("\t")
    if proc.returncode != 0 or len(parts) != 3:
        raise ValueError(f"could not resolve font family {family!r} via fc-match")
    font_path = Path(parts[2])
    return FontRecord(
        request=family,
        family=parts[0],
        style=parts[1],
        file=str(font_path),
        directory=str(font_path.parent) + os.sep,
        filename=font_path.name,
        tex_safe_file=("[" not in font_path.name and "]" not in font_path.name),
    )


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _compile_tex(tex_path: Path) -> None:
    _require_binary("xelatex")
    env = _texinputs_env()
    cwd = tex_path.parent
    for _ in range(2):
        proc = _run(
            ["xelatex", "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            env=env,
            cwd=cwd,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"LaTeX build failed for {tex_path}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )


def _specimen_text_sections() -> List[tuple[str, str]]:
    return [
        (
            "Reading Text",
            "\n\n".join(
                [
                    "اَللّهُمَّ اَهْلَ الْكِبْرِيَاءِ وَالْعَظَمَةِ وَأَهْلَ الْجُودِ وَالْجَبَرُوتِ وَأَهْلَ الْعَفْوِ وَالرَّحْمَةِ.",
                    "می‌خواهیم شکل‌گیری حروف، جای‌گیری اعراب، نیم‌فاصله، و نسبتِ متن فارسی با متن انگلیسی را دقیق ببینیم.",
                    "در این صفحه، هر فونت باید هم برای نثر، هم برای تیتر، هم برای فرمول، و هم برای نمادهای یونی‌کد رفتاری روشن و قابل قضاوت داشته باشد.",
                ]
            ),
        ),
        (
            "Mixed Persian And English",
            "\n\n".join(
                [
                    "در این مدل، complex numbers به ما اجازه می‌دهند دامنه و فاز را هم‌زمان ببینیم: $z = x + iy = re^{i\\theta}$.",
                    "وقتی information propagation از یک bubble به bubble دیگر می‌رسد، تفسیر محلی، entropy و stability را بازنویسی می‌کند.",
                ]
            ),
        ),
        (
            "Unicode And ASCII",
            "\n".join(
                [
                    "signal ──► observer ──► bubble",
                    "   │           │           │",
                    "   ▼           ▼           ▼",
                    " phase      belief      entropy",
                    "Unicode: «سلام»  ∑  ∮  ∂  ℂ  ⟂  ⇌  ⟦x⟧",
                ]
            ),
        ),
    ]


def specimen_tex(title: str, fonts: Sequence[FontRecord]) -> str:
    unsafe = [font.request for font in fonts if not font.tex_safe_file]
    if unsafe:
        raise ValueError(
            "These fonts resolve to variable-font filenames that this XeLaTeX path does not handle cleanly: "
            + ", ".join(unsafe)
            + ". Use the HarfBuzz preview command for them."
        )

    blocks: List[str] = []
    for idx, font in enumerate(fonts, start=1):
        command = f"\\singinefaprooffont{_latex_suffix(idx)}"
        sections: List[str] = []
        for heading, body in _specimen_text_sections():
            body_lines = body.splitlines()
            rendered_lines = []
            for line in body_lines:
                if line.strip():
                    rendered_lines.append(
                        f"{{{command}\\fontsize{{18}}{{28}}\\selectfont {_escape_tex(line)}\\\\[3mm]}}"
                    )
                else:
                    rendered_lines.append("\\vspace{2mm}")
            sections.append(
                "\n".join(
                    [
                        f"\\subsection*{{{_escape_tex(heading)}}}",
                        "\\begin{RTL}",
                        *rendered_lines,
                        "\\end{RTL}",
                    ]
                )
            )

        blocks.append(
            "\n".join(
                [
                    f"\\newfontfamily{command}[Path={_escape_tex(font.directory)}, UprightFont={{{_escape_tex(font.filename)}}}, Script=Arabic, Language=Persian, Ligatures=TeX, RawFeature={{+kern,+mark,+mkmk}}]{{{_escape_tex(font.filename)}}}",
                    f"\\section*{{{_escape_tex(font.request)} \\hfill \\normalfont\\small {_escape_tex(font.family)} / {_escape_tex(font.style)}}}",
                    "\\begin{tcolorbox}[colback=white,colframe=fromcolor,title={Technique Matrix}]",
                    *sections,
                    "\\medskip",
                    "\\textbf{Math checks.} $z = x + iy$, \\quad $\\frac{\\partial u}{\\partial x} = \\frac{\\partial v}{\\partial y}$, \\quad $H(X) = -\\sum_x p(x)\\log p(x)$.",
                    "\\medskip",
                    "\\textbf{Dirac.} $\\left(i\\gamma^\\mu \\partial_\\mu - m\\right)\\psi = 0$",
                    "\\end{tcolorbox}",
                    "\\newpage",
                ]
            )
        )

    return "\n".join(
        [
            r"\documentclass[11pt,a4paper]{scrartcl}",
            r"\usepackage[a4paper,margin=15mm]{geometry}",
            r"\usepackage{fontspec}",
            r"\usepackage{bidi}",
            r"\usepackage{amsmath,amssymb,mathtools}",
            r"\usepackage{parskip}",
            r"\usepackage[most]{tcolorbox}",
            r"\usepackage{xcolor}",
            r"\usepackage{Persian-Gulf}",
            r"\pagestyle{empty}",
            r"\setlength{\parindent}{0pt}",
            r"\begin{document}",
            rf"{{\Huge\bfseries {_escape_tex(title)}}}\\[2mm]",
            r"{\small Font-by-font comparison for Persian reading text, bilingual mixing, Unicode symbols, ASCII-art flow, and mathematical formulae.}\\[5mm]",
            *blocks,
            r"\end{document}",
        ]
    )


def showcase_tex(title: str, font: FontRecord) -> str:
    if not font.tex_safe_file:
        raise ValueError(
            f"{font.request} resolves to a variable-font filename that this XeLaTeX path does not handle cleanly; use HarfBuzz preview for that font."
        )
    command = r"\showcasefont"
    return "\n".join(
        [
            r"\documentclass[10pt,a4paper]{scrartcl}",
            r"\usepackage[a4paper,margin=14mm]{geometry}",
            r"\usepackage{fontspec}",
            r"\usepackage{bidi}",
            r"\usepackage{amsmath,amssymb,mathtools}",
            r"\usepackage{parskip}",
            r"\usepackage[most]{tcolorbox}",
            r"\usepackage{xcolor}",
            r"\usepackage{Persian-Gulf}",
            r"\pagestyle{empty}",
            r"\setlength{\parindent}{0pt}",
            f"\\newfontfamily{command}[Path={_escape_tex(font.directory)}, UprightFont={{{_escape_tex(font.filename)}}}, Script=Arabic, Language=Persian, Ligatures=TeX, RawFeature={{+kern,+mark,+mkmk}}]{{{_escape_tex(font.filename)}}}",
            r"\begin{document}",
            rf"{{\Huge\bfseries {_escape_tex(title)}}}\\[-1mm]",
            r"{\small A compact bilingual showcase for two-column style, Unicode, and mathematical publication under the Persian-Gulf profile.}\\[4mm]",
            r"\begin{tcolorbox}[colback=white,colframe=fromcolor,title={Editorial Frame}]",
            r"The document stays semantically plain: KOMA-Script article, clear sections, explicit minipages, and a profile import from \texttt{Persian-Gulf.sty}.",
            r"\end{tcolorbox}",
            r"\begin{minipage}[t]{0.48\textwidth}",
            r"\raggedright",
            r"\section*{English Column}",
            r"Complex analysis gives us a language for phase, amplitude, and transformation. If information travels across interacting bubbles, then the local state of each bubble is altered not only by signal magnitude, but also by interpretation, delay, and resonance.",
            r"",
            r"We can write the complex state as",
            r"\[",
            r"z = x + iy = re^{i\theta}",
            r"\]",
            r"and use entropy as a coarse description of uncertainty:",
            r"\[",
            r"H(X) = -\sum_x p(x)\log p(x), \qquad I(X;Y) = H(X) - H(X\mid Y).",
            r"\]",
            r"In a teaching document, this page tests whether mathematics, prose, and symbolic density remain legible when mixed with Persian blocks.",
            r"\end{minipage}\hfill",
            r"\begin{minipage}[t]{0.48\textwidth}",
            r"\begin{RTL}",
            rf"{{{command}\section*{{ستون فارسی}}",
            r"در این نمونه، انتشارِ معنا مانند انتشارِ موج در یک محیط ناهمگن دیده می‌شود. هر فرد در یک یا چند حبابِ معنایی زندگی می‌کند و هر تماسِ اطلاعاتی، تعادلِ آن حباب را با تغییرِ فاز، وزنِ باور، و سطحِ آنتروپی بازتنظیم می‌کند.",
            r"",
            r"اگر بخواهیم این رفتار را به زبانِ ریاضی ساده کنیم، می‌توانیم بگوییم که حالتِ سیستم از یک تابعِ مختلط پیروی می‌کند و برهم‌کنشِ موضعی، هم دامنه را عوض می‌کند و هم فاز را.",
            r"",
            r"برای آزمایشِ حروف‌چینی، این ستون باید هم متنِ پیوسته، هم نیم‌فاصله، هم اعراب، و هم فرمول را در کنارِ متنِ انگلیسی تحمل کند.}}",
            r"\end{RTL}",
            r"\end{minipage}",
            r"\vspace{4mm}",
            r"\begin{tcolorbox}[colback=white,colframe=persianblue,title={Propagation, Dirac, And Structure}]",
            r"Dirac's equation still reads beautifully on the page:",
            r"\[",
            r"\left(i\gamma^\mu \partial_\mu - m\right)\psi = 0.",
            r"\]",
            r"If propagation changes the reachable microstates of the receiving bubble, then entropy is not just a count of disorder. It becomes a trace of contact, memory, and structural adaptation.",
            r"\end{tcolorbox}",
            r"\begin{tcolorbox}[colback=white,colframe=fromcolor,title={Unicode And ASCII Surface}]",
            r"\ttfamily",
            r"source  ──►  observer  ──►  bubble\\",
            r"   │             │             │\\",
            r"   ▼             ▼             ▼\\",
            r" phase        belief        entropy\\[2mm]",
            r"\rmfamily",
            rf"\begin{{RTL}}{{{command}یونی‌کد: «سلام»  ∮  ℂ  ∂  ⇌  ⟦x⟧  و متنِ ترکیبی با English tokens.}}\end{{RTL}}",
            r"\end{tcolorbox}",
            r"\begin{tcolorbox}[colback=white,colframe=fromcolor,title={Complex Numbers As Pedagogy}]",
            r"\textbf{English.} Cauchy--Riemann equations test alignment between prose and notation:",
            r"\[",
            r"\frac{\partial u}{\partial x} = \frac{\partial v}{\partial y}, \qquad",
            r"\frac{\partial u}{\partial y} = -\frac{\partial v}{\partial x}.",
            r"\]",
            r"\begin{RTL}",
            rf"{{{command}\textbf{{فارسی.}} این فرمول‌ها فقط ابزارِ تحلیلی نیستند؛ برای این نمونه، آن‌ها یک آزمونِ حروف‌چینی‌اند تا ببینیم معادله، متن، و نشانه‌های ریاضی چگونه در کنارِ هم می‌نشینند.}}",
            r"\end{RTL}",
            r"\end{tcolorbox}",
            r"\end{document}",
        ]
    )


def _write_artifacts(
    output_dir: Path,
    stem: str,
    tex_text: str,
    manifest: Dict[str, Any],
) -> Dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_path = output_dir / f"{stem}.tex"
    pdf_path = output_dir / f"{stem}.pdf"
    json_path = output_dir / f"{stem}.json"
    tex_path.write_text(tex_text, encoding="utf-8")
    _write_json(json_path, manifest | {"tex": str(tex_path), "pdf": str(pdf_path)})
    _compile_tex(tex_path)
    return {"tex": str(tex_path), "pdf": str(pdf_path), "json": str(json_path)}


def build_specimen(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    fonts: Sequence[str] = DEFAULT_SPECIMEN_FONTS,
    title: str = "Singine Persian Font Specimen",
) -> Dict[str, Any]:
    if not PERSIAN_GULF_STY.exists():
        raise FileNotFoundError(f"Persian-Gulf profile not found at {PERSIAN_GULF_STY}")
    records = [resolve_font(item) for item in fonts]
    stem = f"{_timestamp()}-{_slug(title)}"
    artifacts = _write_artifacts(
        output_dir=output_dir,
        stem=stem,
        tex_text=specimen_tex(title, records),
        manifest={
            "kind": "specimen",
            "title": title,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "fonts": [asdict(item) for item in records],
            "profile": str(PERSIAN_GULF_STY),
        },
    )
    return {"kind": "specimen", "title": title, "fonts": [asdict(item) for item in records], "artifacts": artifacts}


def build_showcase(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    font: str = DEFAULT_SHOWCASE_FONT,
    title: str = "Propagation, Bubbles, And Complex Analysis",
) -> Dict[str, Any]:
    if not PERSIAN_GULF_STY.exists():
        raise FileNotFoundError(f"Persian-Gulf profile not found at {PERSIAN_GULF_STY}")
    record = resolve_font(font)
    stem = f"{_timestamp()}-{_slug(title)}-showcase"
    artifacts = _write_artifacts(
        output_dir=output_dir,
        stem=stem,
        tex_text=showcase_tex(title, record),
        manifest={
            "kind": "showcase",
            "title": title,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "font": asdict(record),
            "profile": str(PERSIAN_GULF_STY),
        },
    )
    return {"kind": "showcase", "title": title, "font": asdict(record), "artifacts": artifacts}


def build_harfbuzz_preview(
    font: str,
    text: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> Dict[str, Any]:
    _require_binary("hb-view")
    record = resolve_font(font)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_timestamp()}-{_slug(font)}-hb"
    pdf_path = output_dir / f"{stem}.pdf"
    proc = _run(
        [
            "hb-view",
            "--output-format=pdf",
            f"--output-file={pdf_path}",
            "--direction=rtl",
            "--language=fa",
            "--script=Arab",
            "--margin=32",
            "--font-size=42",
            record.file,
            text,
        ]
    )
    if proc.returncode != 0:
        raise RuntimeError(f"hb-view failed for {font}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
    json_path = output_dir / f"{stem}.json"
    _write_json(
        json_path,
        {
            "kind": "harfbuzz-preview",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "font": asdict(record),
            "text": text,
            "pdf": str(pdf_path),
        },
    )
    return {"kind": "harfbuzz-preview", "font": asdict(record), "artifacts": {"pdf": str(pdf_path), "json": str(json_path)}}


def build_suite(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    specimen_fonts: Sequence[str] = DEFAULT_SPECIMEN_FONTS,
    showcase_font: str = DEFAULT_SHOWCASE_FONT,
    hb_font: str = DEFAULT_HB_FONT,
) -> Dict[str, Any]:
    return {
        "specimen": build_specimen(output_dir=output_dir, fonts=specimen_fonts),
        "showcase": build_showcase(output_dir=output_dir, font=showcase_font),
        "harfbuzz": build_harfbuzz_preview(
            font=hb_font,
            text="سلام فارسی · Complex phase z = re^{iθ} · ∮ f(z) dz",
            output_dir=output_dir,
        ),
    }
