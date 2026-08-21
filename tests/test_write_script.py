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


def resolved_byte_count(text: str, value: str) -> int:
    """The number behind a `bs=` argument, whether written inline or held in a
    variable. Asserting on the variable's name instead would test the spelling
    rather than the size."""
    if not value.startswith("$"):
        assert value.isdigit(), f"bs={value} is not a byte count"
        return int(value)

    name = value.strip("${}")
    assigned = re.search(rf"^{name}=(\d+)$", text, re.M)

    assert assigned, f"bs={value} but {name} is not assigned a plain number"
    return int(assigned.group(1))


def block_sizes_in(text: str, region: str) -> list[int]:
    return [resolved_byte_count(text, v) for v in re.findall(r"bs=\"?(\$?\{?\w+\}?)\"?", region)]


class TestPortability:
    def test_no_block_size_uses_a_suffix_only_bsd_accepts(self, text):
        """GNU dd rejects a lowercase suffix. A plain byte count suits both."""
        offenders = re.findall(r"bs=\d+[a-z]", text)

        assert offenders == []

    def test_every_block_size_is_a_byte_count(self, text):
        """Either a literal number, or a variable holding one."""
        sizes = block_sizes_in(text, text)

        assert sizes

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
        """Two disks sharing a serial can make real mode DOS serve a cached FAT from
        the previous one after a swap, so there is no way to ask for that."""
        assert "fixed-serial" not in text
        assert "FIXED_SERIAL" not in text

    def test_there_is_no_way_to_ask_for_a_volume_label(self, text):
        """An image carries no label by design, and the writer offers no way to add
        one, so every disk reads as NO NAME."""
        assert "LABEL" not in text

    def test_an_unrecognised_argument_is_refused_rather_than_read_as_a_label(self, text):
        """It used to treat any unknown word as a label, so a typo silently became
        the volume name instead of an error."""
        assert "unknown argument" in text


class TestItDependsOnlyOnTrackedCode:
    """The script used to call a helper that .gitignore excluded, so a clone got a
    script that could not run and a guide that pointed at it."""

    def test_it_calls_the_packaged_command(self, text):
        assert "payload" in text

    def test_it_no_longer_calls_the_untracked_helper(self, text):
        assert "z64_prep" not in text

    def test_the_helper_is_gone_from_the_tree(self):
        assert not (SCRIPT.parent / "z64_prep.py").exists()

    def test_the_command_it_calls_is_overridable(self, text):
        """So an installed z64kit can be used instead of the checkout."""
        assert "Z64KIT" in text

    def test_it_stops_when_that_command_fails(self, text):
        """A failed prepare used to leave PREP empty and the byte count blank, which
        then wrote nothing and reported success."""
        prepare = text[text.index("PREP=") :]

        assert "exit 1" in prepare[: prepare.index("\n\n")]


class TestVerification:
    def test_it_reads_the_disk_back_and_compares(self, text):
        assert "shasum" in text
        assert "WANT" in text and "GOT" in text


class TestItDoesNotLeaveTheDiskExposed:
    """macOS mounts a freshly written disk read-write and indexes it.

    On the disk written during development that cost 988 KB of Spotlight index
    plus an FSEvents log, added two directories the unit never asked for, and
    broke byte-identity with the image. Ejecting when the write is done is what
    stops it: an unmounted disk cannot be indexed.
    """

    def test_it_ejects_when_it_is_finished(self, text):
        assert "diskutil eject" in text

    def test_it_ejects_after_reading_the_disk_back(self, text):
        assert text.index("GOT=") < text.index("diskutil eject")

    def test_it_ejects_whether_or_not_the_comparison_matches(self, text):
        """A failed verify used to leave the disk mounted, which is when macOS
        indexes it, which is the worst moment to leave it exposed."""
        assert text.index("diskutil eject") < text.index('if [ "$WANT" = "$GOT" ]')

    def test_it_says_the_disk_was_ejected(self, text):
        assert "ejected" in text.lower()


class TestVerificationIsNotPainfullySlow:
    """Reading back 96 MiB in 512-byte requests is 196,608 round trips to a USB
    Zip drive. It looked like a hang during development, because at that request
    size it very nearly is one."""

    def test_the_read_back_uses_a_large_block_size(self, text):
        sizes = block_sizes_in(text, text[text.index("GOT=") :])

        assert sizes, "the read-back passes no block size to dd"
        assert min(sizes) >= 1 << 20

    def test_it_still_compares_exactly_the_payload_bytes(self, text):
        """A large block size overshoots, so the tail has to be trimmed."""
        read_back = text[text.index("GOT=") :]

        assert "head -c" in read_back


class TestItRefusesAnEmptyImage:
    """The default IMG is a build artifact that can be left over from an earlier
    run. An empty one is 229 KB of metadata, so writing it erases the disk and
    leaves nothing on it, which no one asks for by accident.
    """

    def test_it_checks_whether_the_image_holds_any_file(self, text):
        assert 'HIGH" -lt 2' in text

    def test_it_refuses_rather_than_writing(self, text):
        guard = text[text.index('HIGH" -lt 2') :]

        assert "fail " in guard[: guard.index("\nfi")]

    def test_it_says_what_would_happen(self, text):
        assert "leave a blank volume" in text

    def test_it_names_the_way_out(self, text):
        assert "--empty" in text

    def test_it_points_at_the_image_the_user_probably_meant(self, text):
        assert "Zip_Disk_NN.img" in text

    def test_the_escape_hatch_is_a_real_flag(self, text):
        assert "--empty) EMPTY_OK=1" in text

    def test_the_guard_runs_before_anything_is_written(self, text):
        assert text.index('HIGH" -lt 2') < text.index("sudo dd")
