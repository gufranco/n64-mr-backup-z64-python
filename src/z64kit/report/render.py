"""Turning LaTeX source into a PDF, when that is possible.

The `.tex` file is the artifact and is always written. Compilation is
opportunistic: several engines are tried in turn and the absence of all of them
is reported plainly rather than treated as an error. A user with no TeX
installation still gets something they can compile elsewhere, which is the
reason no engine is a hard dependency.

Tectonic is tried first because it is a single self contained binary that
downloads what a document needs on demand, rather than a multi gigabyte
distribution.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path

ENGINES = ("tectonic", "xelatex", "lualatex", "pdflatex")
COMPILE_TIMEOUT_SECONDS = 300

_PAGE_MARKER = re.compile(rb"/Type\s*/Page[^s]")
_PAGE_COUNT = re.compile(rb"/Count\s+(\d+)")
_STREAM = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)


@dataclass(frozen=True)
class Rendered:
    tex_path: Path
    pdf_path: Path | None
    pages: int
    engine: str | None
    message: str


def find_engine(prefer: str | None = None) -> str | None:
    candidates = (prefer,) if prefer else ENGINES
    for name in candidates:
        if name and shutil.which(name):
            return name
    return None


def count_pages(path: Path | None) -> int:
    """Count pages, including PDFs whose metadata sits in compressed object streams.

    Older engines leave the page tree in plain bytes, so a marker scan finds it.
    Tectonic packs that metadata into object streams, where a scan finds nothing,
    so those streams are inflated before looking again.
    """
    if path is None or not path.exists():
        return 0
    data = path.read_bytes()
    if not data.startswith(b"%PDF"):
        return 0

    direct = len(_PAGE_MARKER.findall(data))
    if direct:
        return direct

    inflated = bytearray()
    for match in _STREAM.finditer(data):
        try:
            inflated += zlib.decompress(match.group(1))
        except zlib.error:
            continue

    if not inflated:
        return 0

    from_markers = len(_PAGE_MARKER.findall(bytes(inflated)))
    if from_markers:
        return from_markers

    counts = [int(n) for n in _PAGE_COUNT.findall(bytes(inflated))]
    return max(counts) if counts else 0


def _command(engine: str, tex: Path, outdir: Path) -> list[str]:
    if engine == "tectonic":
        return [engine, "--outdir", str(outdir), "--keep-logs", "--reruns", "2", str(tex)]
    return [
        engine,
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-output-directory={outdir}",
        str(tex),
    ]


def write(
    source: str,
    stem: Path | str,
    *,
    compile_pdf: bool = True,
    engine: str | None = None,
) -> Rendered:
    target = Path(stem)
    target.parent.mkdir(parents=True, exist_ok=True)
    tex_path = target.with_suffix(".tex")
    tex_path.write_text(source, encoding="utf-8")

    if not compile_pdf:
        return Rendered(
            tex_path=tex_path,
            pdf_path=None,
            pages=0,
            engine=None,
            message=(
                f"wrote {tex_path.name}. Compile it with "
                f"`tectonic {tex_path.name}`, or install one of "
                f"{', '.join(ENGINES)} and run this again."
            ),
        )

    chosen = find_engine(engine)
    if chosen is None:
        return Rendered(
            tex_path=tex_path,
            pdf_path=None,
            pages=0,
            engine=None,
            message=(
                f"wrote {tex_path.name} but no TeX engine was found. Install "
                f"tectonic, a single self contained binary, then run "
                f"`tectonic {tex_path.name}`."
            ),
        )

    outcome = subprocess.run(
        _command(chosen, tex_path, tex_path.parent),
        capture_output=True,
        timeout=COMPILE_TIMEOUT_SECONDS,
        check=False,
    )
    pdf_path = tex_path.with_suffix(".pdf")

    if outcome.returncode != 0 or not pdf_path.exists():
        detail = (outcome.stderr or outcome.stdout).decode("utf-8", "replace")
        first = next(
            (line for line in detail.splitlines() if line.startswith("!")),
            detail.strip().splitlines()[-1] if detail.strip() else "no output",
        )
        return Rendered(
            tex_path=tex_path,
            pdf_path=None,
            pages=0,
            engine=chosen,
            message=f"{chosen} failed: {first.strip()}. The source is at {tex_path.name}.",
        )

    pages = count_pages(pdf_path)
    return Rendered(
        tex_path=tex_path,
        pdf_path=pdf_path,
        pages=pages,
        engine=chosen,
        message=f"{pdf_path.name}, {pages} pages, via {chosen}",
    )
