"""Writing an image to a physical disk, and refusing to when that looks unwise.

Two things this has to get right, and neither is about speed.

A Zip drive that cannot find a track retracts the head and seeks again, over and
over. That is the click, and it can wreck the disk, then the drive, then every
disk put in that drive afterwards. Nothing here can hear it. What it can see is
an I/O error, or throughput collapsing against what the same drive managed a
moment earlier, and both are what the clicking does to the bus.

And the disk is never mounted. Everything goes through the raw device, because a
mounted volume is one macOS writes Spotlight and FSEvents data to behind your
back, on media meant for a console.

The decisions are pure and tested here. The dd calls are not, and live behind
them.
"""

from __future__ import annotations

import subprocess

import pytest

from z64kit import burn

ZIP100 = 100_663_296

DISKUTIL = """   Device Identifier:         disk8
   Device Node:               /dev/disk8
   Whole:                     Yes
   Device / Media Name:       ZIP 100
   Volume Name:               Not applicable
   Mounted:                   Not applicable
   Removable Media:           Removable
   Media Removal:             Software-Activated
   Device Location:           External
   Virtual:                   No
   Disk Size:                 100.7 MB (100663296 Bytes) (exactly 196608 512-Byte-Units)
"""


def device(**over):
    base = {
        "node": "disk8",
        "size": ZIP100,
        "media": "ZIP 100",
        "removable": True,
        "external": True,
        "virtual": False,
    }
    base.update(over)
    return burn.Device(**base)


class TestReadingTheDevice:
    def test_it_reads_the_size(self):
        assert burn.parse_device("disk8", DISKUTIL).size == ZIP100

    def test_it_reads_the_media_name(self):
        assert burn.parse_device("disk8", DISKUTIL).media == "ZIP 100"

    def test_it_reads_removability(self):
        assert burn.parse_device("disk8", DISKUTIL).removable is True

    def test_it_reads_that_the_device_is_external(self):
        assert burn.parse_device("disk8", DISKUTIL).external is True

    def test_it_reads_that_the_device_is_not_virtual(self):
        assert burn.parse_device("disk8", DISKUTIL).virtual is False

    def test_an_internal_disk_is_not_external(self):
        text = DISKUTIL.replace("External", "Internal")

        assert burn.parse_device("disk8", text).external is False

    def test_fixed_media_is_not_removable(self):
        text = DISKUTIL.replace("Removable Media:           Removable", "Removable Media: Fixed")

        assert burn.parse_device("disk8", text).removable is False

    def test_output_with_no_size_is_refused(self):
        with pytest.raises(burn.DeviceError, match="size"):
            burn.parse_device("disk8", "   Device Node: /dev/disk8\n")


class TestRefusingToWrite:
    def test_a_zip_100_is_accepted(self):
        assert burn.refusals(device(), ZIP100) == ()

    def test_the_wrong_size_is_refused(self):
        assert any("bytes" in r for r in burn.refusals(device(size=500_000_000), ZIP100))

    def test_an_internal_device_is_refused(self):
        assert any("external" in r for r in burn.refusals(device(external=False), ZIP100))

    def test_fixed_media_is_refused(self):
        assert any("removable" in r for r in burn.refusals(device(removable=False), ZIP100))

    def test_a_virtual_device_is_refused(self):
        assert any("virtual" in r for r in burn.refusals(device(virtual=True), ZIP100))

    def test_every_reason_is_reported_not_just_the_first(self):
        found = burn.refusals(device(external=False, virtual=True), ZIP100)

        assert len(found) == 2

    def test_the_raw_node_is_the_one_that_avoids_mounting(self):
        assert device().raw == "/dev/rdisk8"

    def test_the_block_node_is_used_for_diskutil(self):
        assert device().block == "/dev/disk8"


class TestWatchingForAClickOfDeath:
    def watch(self, **over):
        settings = {"ceiling_seconds": 60, "slow_factor": 6, "warmup_chunks": 3}
        settings.update(over)
        return burn.StallWatch(**settings)

    def test_a_normal_chunk_passes(self):
        assert self.watch().observe("write", 0, 12, 10) is None

    def test_a_chunk_over_the_ceiling_is_a_fault(self):
        assert self.watch().observe("write", 0, 12, 61) is not None

    def test_the_ceiling_message_names_the_chunk(self):
        found = self.watch().observe("write", 4, 12, 61)

        assert "4" in found and "12" in found

    def test_the_first_chunks_are_not_compared_against_each_other(self):
        """Spin-up makes them unrepresentative, so a healthy drive would trip."""
        watch = self.watch()
        watch.observe("write", 0, 12, 1)

        assert watch.observe("write", 1, 12, 30) is None

    def test_a_later_collapse_is_a_fault(self):
        watch = self.watch()
        for index in range(4):
            watch.observe("write", index, 12, 2)

        assert watch.observe("write", 4, 12, 20) is not None

    def test_the_collapse_message_names_both_timings(self):
        watch = self.watch()
        for index in range(4):
            watch.observe("write", index, 12, 2)
        found = watch.observe("write", 4, 12, 20)

        assert "20" in found and "2" in found

    def test_a_chunk_only_slightly_slower_is_not_a_fault(self):
        watch = self.watch()
        for index in range(4):
            watch.observe("write", index, 12, 2)

        assert watch.observe("write", 4, 12, 10) is None

    def test_the_fastest_chunk_sets_the_baseline(self):
        watch = self.watch()
        for index, seconds in enumerate((9, 8, 2, 3)):
            watch.observe("write", index, 12, seconds)

        assert watch.fastest == 2

    def test_a_zero_second_chunk_does_not_become_the_baseline(self):
        """It would make every later chunk a collapse against nothing."""
        watch = self.watch()
        for index in range(4):
            watch.observe("write", index, 12, 0)

        assert watch.observe("write", 4, 12, 5) is None

    def test_the_direction_is_named_so_the_reader_knows_which_half_failed(self):
        assert "read" in self.watch().observe("read", 0, 12, 61)

    def test_a_reused_watch_starts_over(self):
        watch = self.watch()
        for index in range(4):
            watch.observe("write", index, 12, 2)
        watch.reset()

        assert watch.fastest == 0


class TestChunking:
    def test_it_covers_every_byte(self):
        spans = list(burn.chunks(total=20, size=8))

        assert sum(length for _, length in spans) == 20

    def test_the_last_chunk_is_short_rather_than_overshooting(self):
        spans = list(burn.chunks(total=20, size=8))

        assert spans[-1] == (2, 4)

    def test_an_exact_multiple_has_no_short_chunk(self):
        spans = list(burn.chunks(total=24, size=8))

        assert [length for _, length in spans] == [8, 8, 8]

    def test_a_payload_smaller_than_one_chunk_is_one_chunk(self):
        assert list(burn.chunks(total=5, size=8)) == [(0, 5)]

    def test_nothing_to_write_is_no_chunks(self):
        assert list(burn.chunks(total=0, size=8)) == []


class TestItAsksForRootOnce:
    """Writing to a raw device needs root. Discovering that on chunk one, after
    the disk has already been unmounted, is the wrong moment to find out."""

    def test_the_dd_calls_run_privileged(self):
        assert burn.privileged(["dd"])[0] == "sudo"

    def test_the_command_survives_the_prefix(self):
        assert burn.privileged(["dd", "if=/dev/rdisk8"])[1:] == ["dd", "if=/dev/rdisk8"]


class FakeDrive:
    """A drive that answers dd and diskutil, and can fail on cue.

    Standing in for the external tools rather than for anything in this project:
    a real drive cannot be made to click on demand, and the abort logic is the
    part most worth proving.
    """

    def __init__(self, contents=b"", *, fail_on=None, corrupt_chunk=None, slow_chunk=None):
        self.contents = bytearray(contents)
        self.fail_on = fail_on
        self.corrupt_chunk = corrupt_chunk
        self.slow_chunk = slow_chunk
        self.commands = []
        self.reads = 0
        self.writes = 0

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        joined = " ".join(command)
        if "dd" not in joined:
            return subprocess.CompletedProcess(command, 0, b"", b"")
        chunk = next(int(a.split("=")[1]) for a in command if a.startswith(("seek=", "skip=")))
        size = next(int(a.split("=")[1]) for a in command if a.startswith("bs="))
        if "of=/dev/r" in joined:
            self.writes += 1
            if self.fail_on == ("write", chunk):
                return subprocess.CompletedProcess(command, 1, b"", b"I/O error")
            payload = kwargs.get("input", b"")
            start = chunk * size
            self.contents[start : start + len(payload)] = payload
            return subprocess.CompletedProcess(command, 0, b"", b"")
        self.reads += 1
        if self.fail_on == ("read", chunk):
            return subprocess.CompletedProcess(command, 1, b"", b"I/O error")
        block = bytes(self.contents[chunk * size : chunk * size + size])
        if self.corrupt_chunk == chunk:
            block = bytes(len(block))
        return subprocess.CompletedProcess(command, 0, block, b"")


def payload_file(tmp_path, size):
    """Every byte non-zero and varying, so zeroing a chunk is a visible change.

    A payload of zeros would make the corruption tests pass against a check that
    does nothing.
    """
    made = tmp_path / "payload.bin"
    made.write_bytes(bytes((index * 7 + 1) % 256 or 0xFF for index in range(size)))
    return made


class TestWritingADisk:
    def test_a_healthy_drive_writes_and_verifies(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40))

        result = burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)

        assert result.chunks == 3

    def test_it_ejects_when_it_finishes(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40))

        result = burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)

        assert result.ejected is True

    def test_it_unmounts_before_writing_and_before_reading(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40))

        burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)
        unmounts = [c for c in drive.commands if "unmountDisk" in " ".join(c)]

        assert len(unmounts) == 2

    def test_it_never_mounts(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40))

        burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)

        assert not any(c[:2] == ["sudo", "diskutil"] and c[2] == "mount" for c in drive.commands)

    def test_everything_goes_through_the_raw_device(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40))

        burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)
        transfers = [" ".join(c) for c in drive.commands if " dd " in f" {' '.join(c)} "]

        assert transfers
        assert all("/dev/rdisk8" in t for t in transfers)

    def test_a_failed_write_stops_and_ejects(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40), fail_on=("write", 1))

        with pytest.raises(burn.WriteFailedError, match="write failed"):
            burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)

        assert any("eject" in " ".join(c) for c in drive.commands)

    def test_a_failed_write_does_not_go_on_to_the_next_chunk(self, tmp_path):
        source = payload_file(tmp_path, 400)
        drive = FakeDrive(bytes(400), fail_on=("write", 1))

        with pytest.raises(burn.WriteFailedError):
            burn.write_image(source, device(), total_bytes=400, chunk_bytes=16, run=drive)

        assert drive.writes == 2

    def test_a_failed_read_stops_and_ejects(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40), fail_on=("read", 0))

        with pytest.raises(burn.WriteFailedError, match="read failed"):
            burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)

        assert any("eject" in " ".join(c) for c in drive.commands)

    def test_a_chunk_that_comes_back_wrong_stops_the_run(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40), corrupt_chunk=1)

        with pytest.raises(burn.WriteFailedError, match="came back different"):
            burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)

    def test_a_corrupt_chunk_is_named(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40), corrupt_chunk=2)

        with pytest.raises(burn.WriteFailedError, match="chunk 2"):
            burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)

    def test_a_stall_stops_the_run(self, tmp_path):
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40))
        always_stalled = burn.StallWatch(ceiling_seconds=-1)

        with pytest.raises(burn.WriteFailedError, match="limit"):
            burn.write_image(
                source, device(), total_bytes=40, chunk_bytes=16, watch=always_stalled, run=drive
            )

    def test_the_last_partial_chunk_verifies(self, tmp_path):
        """Comparing a short written chunk against a full block read off the disk
        would fail on every healthy write."""
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40))

        result = burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)

        assert result.chunks == 3

    def test_it_says_what_it_is_doing(self, tmp_path):
        source = payload_file(tmp_path, 40)
        said = []

        burn.write_image(
            source,
            device(),
            total_bytes=40,
            chunk_bytes=16,
            run=FakeDrive(bytes(40)),
            say=said.append,
        )

        assert any("never mounted" in line for line in said)
