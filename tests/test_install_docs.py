"""The install line in the documentation must not carry a version.

Both README.md and GUIDE.md pinned v1.0.2 while the released version was v1.1.1,
which is what a hand-maintained version number does over time. They now point at
`refs/tags/latest`, a tag the release job moves onto each release, so the line is
correct without anyone editing it.

These tests hold that shape. A version-pinned archive URL reappearing in a document
a reader is meant to copy from is the regression. What the release job must do to keep
that tag correct lives in test_release_workflow.py.

Documents are keyed by their path relative to the repository root rather than by
filename, because `patches/README.md` and `README.md` share a name.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_URL = re.compile(r"archive/refs/(tags|heads)/(?P<ref>[\w.\-]+)\.(zip|tar\.gz)")
PINNED = re.compile(r"^v?\d+\.\d+")
INSTALLED_FROM = ("README.md", "GUIDE.md")


def tracked_markdown() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [name for name in listed if (ROOT / name).is_file()]


@pytest.fixture(scope="module")
def documents() -> dict[str, str]:
    return {name: (ROOT / name).read_text(encoding="utf-8") for name in tracked_markdown()}


def archive_urls(text: str) -> set[str]:
    return {found.group(0) for found in ARCHIVE_URL.finditer(text)}


class TestTheInstallLineDoesNotCarryAVersion:
    def test_it_covers_the_documents_a_reader_installs_from(self, documents):
        """Guards the guard: a glob that stopped matching would pass everything else."""
        for name in INSTALLED_FROM:
            assert name in documents

    def test_no_document_pins_a_version_in_an_archive_url(self, documents):
        offenders = [
            f"{name}: {found.group(0)}"
            for name, text in documents.items()
            for found in ARCHIVE_URL.finditer(text)
            if PINNED.match(found.group("ref"))
        ]

        assert offenders == [], "a pinned archive URL goes stale on the next release"

    def test_the_documents_a_reader_installs_from_use_the_moving_tag(self, documents):
        for name in INSTALLED_FROM:
            assert "archive/refs/tags/latest.zip" in documents[name]

    def test_both_documents_offer_the_same_install_line(self, documents):
        readme, guide = (archive_urls(documents[name]) for name in INSTALLED_FROM)

        assert readme == guide
