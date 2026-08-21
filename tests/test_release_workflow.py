"""What the release job must keep doing, asserted against the workflow itself.

Two failures drove these. The moving `latest` tag broke the job on its first run,
because a bare `git describe` prefers it over the version tag on the same commit
and a tag is not a release name. And the job attached assets with `--clobber`, so
a docs-only push could rewrite a signed artifact on an already-published release.

Neither is visible until a release runs, which is the slowest feedback loop in the
repository, so they are pinned here instead.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


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


class TestTheReleaseJobKeepsTheMovingTagMoving:
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

    def test_the_steps_that_need_it_read_one_resolved_answer(self, workflow):
        assert workflow.count("steps.released.outputs.tag") >= 4

    def test_those_steps_do_not_run_when_nothing_was_released(self, workflow):
        assert workflow.count("if: steps.released.outputs.tag != ''") == 2


class TestPublishedReleasesAreImmutable:
    """A signed artifact that can change is not much of a claim. The job used to
    attach with `--clobber`, so a push that released nothing resolved to the
    existing release and replaced its SBOM and signature.
    """

    def test_it_never_overwrites_an_existing_asset(self, workflow_commands):
        assert "--clobber" not in workflow_commands

    def test_it_records_the_tag_that_existed_before_releasing(self, workflow_commands):
        recorded = workflow_commands.index("steps.before.outputs.tag")
        released = workflow_commands.index("semantic-release")

        assert recorded > released, "the comparison reads a value captured earlier"

    def test_the_earlier_capture_runs_before_semantic_release(self, workflow):
        assert workflow.index("id: before") < workflow.index("pnpm exec semantic-release")

    def test_an_unchanged_tag_is_treated_as_no_release(self, workflow_commands):
        assert '[ "${tag}" = "${BEFORE}" ]' in workflow_commands

    def test_the_two_tag_lookups_ask_the_same_question(self, workflow_commands):
        """Comparing before against after only means anything if both were measured
        the same way. The surrounding shell differs, so this reads the command."""
        asked = re.findall(r"git describe[^\n]*?(?= 2>)", workflow_commands)

        assert len(asked) == 2, "one lookup before the release, one after"
        assert asked[0] == asked[1]
