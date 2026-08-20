"""Building LaTeX documents.

The reports are long dense tables, and the browser based approach they replace
fought page breaking at every turn: a two column summary would spill a nearly
empty page, cells wrapped unpredictably, and there was no way to guarantee a
header row repeated after a break. `longtable` does that by construction, which
is the whole reason for this layer.

Everything is monochrome by design. These pages are printed and read next to a
stack of disks, so structure comes from rules and weight rather than colour.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

PREAMBLE = r"""\documentclass[9pt,a4paper]{extarticle}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[a4paper,margin=12mm,bottom=14mm]{geometry}
\usepackage{longtable}
\usepackage{booktabs}
\usepackage{array}
\usepackage{ragged2e}
\usepackage{fancyhdr}
\usepackage{lastpage}
\renewcommand{\familydefault}{\sfdefault}
\setlength{\parindent}{0pt}
\setlength{\parskip}{2pt}
\setlength{\tabcolsep}{3pt}
\renewcommand{\arraystretch}{1.15}
\pagestyle{fancy}
\fancyhf{}
\fancyfoot[L]{\footnotesize \DOCTITLE}
\fancyfoot[R]{\footnotesize \thepage\ of \pageref{LastPage}}
\renewcommand{\footrulewidth}{0.2pt}
"""


def escape(text: object) -> str:
    out = []
    for char in str(text):
        out.append(_ESCAPES.get(char, char))
    return "".join(out)


def section(heading: str) -> str:
    return f"\\section*{{{escape(heading)}}}\n"


def key_values(pairs: Iterable[tuple[str, str]]) -> str:
    rows = "".join(f"\\textbf{{{escape(k)}}} & {escape(v)} \\\\\n" for k, v in pairs)
    return "\\begin{tabular}{@{}p{45mm}p{100mm}@{}}\n" + rows + "\\end{tabular}\n\n"


def longtable(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    *,
    widths: Sequence[str],
    align: Sequence[str] | None = None,
    caption: str = "",
) -> str:
    if len(headers) != len(widths):
        raise ValueError("one width is required per header")
    for row in rows:
        if len(row) != len(headers):
            raise ValueError(f"a row has {len(row)} cells but the table has {len(headers)} columns")

    alignment = list(align or ["l"] * len(headers))
    spec = []
    for letter, width in zip(alignment, widths, strict=True):
        if letter == "r":
            spec.append(f">{{\\RaggedLeft\\arraybackslash}}p{{{width}}}")
        else:
            spec.append(f"p{{{width}}}")

    head = " & ".join(f"\\footnotesize\\textbf{{{escape(h)}}}" for h in headers)
    body = "".join(" & ".join(escape(cell) for cell in row) + " \\\\\n" for row in rows)

    parts = [
        "{\\footnotesize",
        f"\\begin{{longtable}}{{@{{}}{''.join(spec)}@{{}}}}",
    ]
    if caption:
        parts.append(f"\\caption*{{{escape(caption)}}}\\\\")
    parts += [
        "\\toprule",
        f"{head} \\\\",
        "\\midrule",
        "\\endfirsthead",
        "\\toprule",
        f"{head} \\\\",
        "\\midrule",
        "\\endhead",
        "\\bottomrule",
        "\\endfoot",
        body.rstrip(),
        "\\end{longtable}}",
        "",
    ]
    return "\n".join(parts)


def note(text: str) -> str:
    return "\\begin{quote}\\footnotesize\n" + escape(text) + "\n\\end{quote}\n\n"


def document(*, title: str, subtitle: str, body: str) -> str:
    safe_title = escape(title)
    header = PREAMBLE.replace(r"\DOCTITLE", safe_title)
    parts = [
        header,
        "\\begin{document}",
        f"{{\\LARGE\\bfseries {safe_title}}}\\\\[2pt]",
    ]
    if subtitle:
        parts.append(f"{{\\footnotesize {escape(subtitle)}}}\\\\[6pt]")
    parts += [
        "\\hrule\\vspace{6pt}",
        body,
        "\\end{document}",
        "",
    ]
    return "\n".join(parts)
