"""Tests for the shell script that writes an image to a physical disk.

This script is the one piece of the project that can destroy data, and it is the
only piece not written in Python, so nothing else here checks it. These tests read
it as text and assert the properties that matter, which is weaker than running it
but stronger than nothing: running it needs a Zip drive and root.

The first of them exists because of a real failure. The script passed `bs=1m` to
dd, which BSD dd accepts and GNU dd rejects, so on a machine with coreutils ahead
of the system tools it aborted at the write with `invalid number`.
"""

import re
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "write-zip.sh"


@pytest.fixture
def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


class TestPortability:
    def test_no_block_size_uses_a_suffix_only_bsd_accepts(self, text):
        """GNU dd rejects a lowercase suffix. A plain byte count suits both."""
        offenders = re.findall(r"bs=\d+[a-z]", text)

        assert offenders == []

    def test_every_block_size_is_a_plain_number(self, text):
        for value in re.findall(r"bs=(\S+)", text):
            assert value.isdigit(), f"bs={value} is not a plain byte count"

    def test_it_does_not_rely_on_a_bsd_only_stat_format(self, text):
        assert "stat -f" not in text

    def test_no_script_uses_an_idiom_only_one_of_the_two_provides(self):
        """macOS ships BSD tools, and Homebrew coreutils puts GNU ones ahead of them.

        Either can be first in PATH on a given machine, so an idiom that only one
        accepts is a script that works until somebody installs coreutils. The dd
        block size was exactly that.
        """
        divergent = {
            r"sed -i(?!\.)": "GNU sed -i with no backup suffix",
            r"stat -c": "GNU stat format",
            r"stat -f": "BSD stat format",
            r"readlink -f": "GNU readlink",
            r"grep -P": "GNU perl regex",
            r"date -d": "GNU date arithmetic",
            r"sort -V": "GNU version sort",
            r"bs=\d+[a-zA-Z]": "dd block size with a suffix",
            r"mktemp -p": "GNU mktemp directory flag",
            r"xargs -r": "GNU xargs",
        }
        offenders = []
        for script in [SCRIPT, *sorted((SCRIPT.parent / "scripts").glob("*.sh"))]:
            body = script.read_text(encoding="utf-8")
            offenders += [
                f"{script.name}: {why}"
                for pattern, why in divergent.items()
                if re.search(pattern, body)
            ]

        assert offenders == []


class TestRefusals:
    def test_it_checks_the_device_is_exactly_a_zip_100(self, text):
        assert "100663296" in text
        assert "EXPECTED_BYTES" in text

    def test_it_refuses_a_device_that_is_not_external(self, text):
        assert 'LOCATION" = "External"' in text or "External" in text

    def test_it_refuses_media_that_is_not_removable(self, text):
        assert "removable" in text.lower()

    def test_it_refuses_a_virtual_device(self, text):
        assert "virtual" in text.lower()

    def test_every_refusal_says_so_rather_than_continuing(self, text):
        assert text.count("fail ") >= 4

    def test_it_stops_on_the_first_error(self, text):
        assert "set -euo pipefail" in text


class TestIdentity:
    def test_it_stamps_a_fresh_serial_on_every_disk(self, text):
        assert "SERIAL" in text

    def test_no_option_keeps_the_image_serial(self, text):
        """Images carry no identity, so a disk that kept it would match every other."""
        assert "fixed-serial" not in text
        assert "FIXED_SERIAL" not in text


class TestVerification:
    def test_it_reads_the_disk_back_and_compares(self, text):
        assert "shasum" in text
        assert "WANT" in text and "GOT" in text
