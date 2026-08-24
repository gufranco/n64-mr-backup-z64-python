"""The install instructions have to match how this project can actually be got.

It used to be installable from a source archive, and both documents carried that
URL. Adopting a submodule ended that: `git archive`, which is what the Download
ZIP button and the auto-generated release tarballs run, resolves one repository
and stops. The archive holds the submodule directory empty and carries no git
metadata, so `git submodule update --init` cannot repair that copy either.

Nothing about that failure is visible to a maintainer, who clones, or to CI,
which checks out recursively. It surfaces only for the person who clicked the
button, and it surfaces as a broken project rather than as a wrong download. So
the documents have to say so, and these tests are what keeps them saying it.

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


class TestTheArchiveIsNotOfferedAnyMore:
    def test_it_covers_the_documents_a_reader_installs_from(self, documents):
        """Guards the guard: a glob that stopped matching would pass everything else."""
        for name in INSTALLED_FROM:
            assert name in documents

    def test_no_document_offers_an_archive_of_this_repository(self, documents):
        offenders = [
            f"{name}: {found.group(0)}"
            for name, text in documents.items()
            for found in ARCHIVE_URL.finditer(text)
            if "n64-mr-backup-z64-python" in text[max(0, found.start() - 120) : found.start()]
        ]

        assert offenders == [], "an archive of a repository with a submodule installs nothing"

    def test_both_documents_tell_the_reader_to_clone_recursively(self, documents):
        for name in INSTALLED_FROM:
            assert "--recurse-submodules" in documents[name], name

    def test_both_documents_say_the_archive_cannot_work(self, documents):
        for name in INSTALLED_FROM:
            text = documents[name].lower()
            assert "download zip" in text, name


class TestTheSubmoduleIsDeclared:
    def test_the_repository_declares_it(self):
        assert (ROOT / ".gitmodules").is_file()

    def test_the_path_the_documents_name_is_the_path_git_uses(self):
        declared = (ROOT / ".gitmodules").read_text(encoding="utf-8")

        assert "path = n64-video-interface-python" in declared

    def test_it_is_cloned_over_https_so_no_key_is_needed(self):
        declared = (ROOT / ".gitmodules").read_text(encoding="utf-8")

        assert "url = https://" in declared

    def test_the_build_reaches_into_it(self):
        manifest = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        assert "n64-video-interface-python/src/n64_video_interface" in manifest

    def test_the_test_run_needs_no_environment(self):
        manifest = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        assert 'pythonpath = ["src", "n64-video-interface-python/src"]' in manifest
