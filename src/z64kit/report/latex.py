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

PAGE_WIDTH_MM = 210.0
MARGIN_MM = 12.0
TEXT_WIDTH_MM = PAGE_WIDTH_MM - 2 * MARGIN_MM
TABCOLSEP_PT = 3.0
MM_PER_PT = 25.4 / 72.27


class TooWideError(ValueError):
    """A table whose columns cannot fit the page, caught before it is typeset.

    LaTeX only warns about an overfull box, so a table that runs off the right
    edge still produces a PDF and a zero exit code. That is how a nine-column
    listing shipped 15.9mm past the margin. Refusing here turns a warning nobody
    reads into a failure that stops the build.
    """


UNITS_IN_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "in": 25.4,
    "pt": MM_PER_PT,
    "bp": 25.4 / 72,
}


def _mm(width: str) -> float:
    """A TeX length in millimetres, so widths in any unit can be compared."""
    unit = width[-2:]
    if unit not in UNITS_IN_MM:
        raise ValueError(f"unknown column width unit in {width!r}")
    return float(width[:-2]) * UNITS_IN_MM[unit]


def table_width_mm(widths: Sequence[str]) -> float:
    """What a table will actually occupy, columns plus the padding between them.

    `\\tabcolsep` is added on both sides of every column, and the `@{}` at each
    end of the spec removes it from the outer edges, which leaves 2n-2 gaps.
    """
    columns = sum(_mm(w) for w in widths)
    gaps = max(0, 2 * len(widths) - 2)
    return columns + gaps * TABCOLSEP_PT * MM_PER_PT


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

    occupied = table_width_mm(widths)
    if occupied > TEXT_WIDTH_MM:
        raise TooWideError(
            f"a {len(widths)}-column table needs {occupied:.1f}mm but the page gives "
            f"{TEXT_WIDTH_MM:.1f}mm, so it would run {occupied - TEXT_WIDTH_MM:.1f}mm past "
            f"the right margin. Narrow the columns, the first of which is "
            f"{max(widths, key=_mm)}."
        )

    alignment = list(align or ["l"] * len(headers))
    spec = []
    for letter, width in zip(alignment, widths, strict=True):
        ragged = "RaggedLeft" if letter == "r" else "RaggedRight"
        spec.append(f">{{\\{ragged}\\arraybackslash}}p{{{width}}}")

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
