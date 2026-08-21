"""The install line in the documentation must not carry a version.

Both README.md and GUIDE.md pinned v1.0.2 while the released version was v1.1.1,
which is what a hand-maintained version number does over time. They now point at
`refs/tags/latest`, a tag the release job moves onto each release, so the line is
correct without anyone editing it.

These tests hold that shape. A version-pinned archive URL reappearing in a document
a reader is meant to copy from is the regression.

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


@pytest.fixture(scope="module")
def workflow() -> str:
    return (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow_commands(workflow: str) -> str:
    """The workflow with comment lines removed.

    A comment that quotes a command would otherwise read as one, and the point of
    these tests is what the job runs rather than what it says about itself.
    """
    return "\n".join(line for line in workflow.splitlines() if not line.lstrip().startswith("#"))


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


class TestTheReleaseJobKeepsThatTagMoving:
    def test_it_moves_the_tag_the_documents_point_at(self, workflow):
        assert "refs/tags/latest" in workflow

    def test_it_forces_the_move_rather_than_failing_on_an_existing_tag(self, workflow):
        assert "force=true" in workflow

    def test_it_creates_the_tag_when_it_does_not_exist_yet(self, workflow):
        assert 'ref="refs/tags/latest"' in workflow

    def test_it_points_the_tag_at_the_released_commit_not_the_checkout(self, workflow):
        assert "git rev-list -n 1" in workflow


class TestTheMovingTagCannotBeMistakenForAReleaseName:
    """`latest` sits on the same commit as the newest version tag, so a bare
    `git describe --tags --abbrev=0` returns `latest` rather than `v1.1.2`. Passing
    that to `gh release upload` fails with "release not found", because a tag is
    not a release. This happened on the run that introduced the moving tag.
    """

    def test_every_tag_lookup_restricts_itself_to_version_tags(self, workflow_commands):
        lookups = re.findall(r"git describe[^\n]*", workflow_commands)

        assert lookups, "the job no longer resolves a tag at all"
        for found in lookups:
            assert "--match 'v*'" in found, f"unrestricted tag lookup: {found}"

    def test_the_tag_is_resolved_once_rather_than_per_step(self, workflow_commands):
        assert len(re.findall(r"git describe", workflow_commands)) == 1

    def test_the_steps_that_need_it_read_that_one_answer(self, workflow):
        assert workflow.count("steps.released.outputs.tag") >= 4

    def test_those_steps_do_not_run_when_no_version_tag_exists(self, workflow):
        assert workflow.count("if: steps.released.outputs.tag != ''") == 2
