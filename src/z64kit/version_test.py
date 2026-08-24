"""The released version, which nothing imports and the release job rewrites.

It is read by the build backend rather than by the code, so a typo in it is
caught at package time and not before. Asserting its shape here is what makes
the release job's edit verifiable without building a wheel.
"""

from __future__ import annotations

import re

from z64kit import version


class TestTheRecordedVersion:
    def test_it_is_a_semantic_version(self):
        assert re.fullmatch(r"\d+\.\d+\.\d+", version.VERSION), version.VERSION

    def test_the_release_script_can_find_the_line_it_rewrites(self):
        from z64kit.conftest import repo_root

        text = (repo_root() / "src" / "z64kit" / "version.py").read_text(encoding="utf-8")

        assert re.search(r'^VERSION = "[^"]+"$', text, re.MULTILINE)
