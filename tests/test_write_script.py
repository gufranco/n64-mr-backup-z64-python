"""The shell wrapper, which now only forwards to the packaged command.

Everything it used to implement moved into `z64kit write`, so those properties
are asserted in test_burn.py against the code that runs on both platforms. What
is left to check here is that the wrapper still forwards correctly and adds no
second implementation of its own.
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "write-zip.sh"


@pytest.fixture(scope="module")
def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def code(text: str) -> str:
    """The script with its help text removed.

    The help describes what the packaged command does, using the same words the
    code deliberately no longer contains.
    """
    before, _, rest = text.partition("<<'USAGE'")
    _, _, after = rest.partition("\nUSAGE\n")
    return before + after


class TestItOnlyForwards:
    def test_it_calls_the_packaged_command(self, text):
        assert "write" in text
        assert "$Z64KIT" in text

    def test_it_hands_over_rather_than_wrapping_the_run(self, text):
        """exec means the caller sees the command's own exit status, so a fault
        is not swallowed by a layer that has nothing left to add."""
        assert "exec $Z64KIT write" in text

    def test_it_carries_no_transfer_logic_of_its_own(self, code):
        """Two implementations of a safety check drift, and this is the copy
        nobody would notice going stale."""
        for absent in ("dd ", "shasum", "STALL", "diskutil", "chunk"):
            assert absent not in code

    def test_it_passes_the_flags_through(self, text):
        for flag in ("-y", "--full", "--empty"):
            assert flag in text

    def test_it_refuses_an_option_it_does_not_know(self, text):
        assert "unknown option" in text

    def test_it_needs_a_device(self, text):
        assert '[ -n "$DEVICE" ] || usage' in text

    def test_it_checks_the_image_is_there_first(self, text):
        assert "image not found" in text

    def test_it_stops_on_the_first_error(self, text):
        assert "set -euo pipefail" in text


class TestItWorksOnBothPlatforms:
    def test_the_help_names_a_device_on_each(self, text):
        assert "disk8" in text
        assert "sdb" in text

    def test_it_hardcodes_no_macos_only_tool(self, code):
        assert "diskutil" not in code

    def test_the_command_it_calls_is_overridable(self, text):
        assert "${Z64KIT:-" in text

    def test_the_image_is_overridable(self, text):
        assert "${IMG:-" in text
