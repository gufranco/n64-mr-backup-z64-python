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

import ast
import subprocess
from pathlib import Path

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
        "block": "/dev/disk8",
        "raw": "/dev/rdisk8",
    }
    base.update(over)
    return burn.Device(**base)


class TestReadingTheDevice:
    def test_it_reads_the_size(self):
        assert burn.parse_macos("disk8", DISKUTIL).size == ZIP100

    def test_it_reads_the_media_name(self):
        assert burn.parse_macos("disk8", DISKUTIL).media == "ZIP 100"

    def test_it_reads_removability(self):
        assert burn.parse_macos("disk8", DISKUTIL).removable is True

    def test_it_reads_that_the_device_is_external(self):
        assert burn.parse_macos("disk8", DISKUTIL).external is True

    def test_it_reads_that_the_device_is_not_virtual(self):
        assert burn.parse_macos("disk8", DISKUTIL).virtual is False

    def test_an_internal_disk_is_not_external(self):
        text = DISKUTIL.replace("External", "Internal")

        assert burn.parse_macos("disk8", text).external is False

    def test_fixed_media_is_not_removable(self):
        text = DISKUTIL.replace("Removable Media:           Removable", "Removable Media: Fixed")

        assert burn.parse_macos("disk8", text).removable is False

    def test_output_with_no_size_is_refused(self):
        with pytest.raises(burn.DeviceError, match="size"):
            burn.parse_macos("disk8", "   Device Node: /dev/disk8\n")


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
        wanted = burn.privileged(burn.unmount_command(device()))
        unmounts = [c for c in drive.commands if c == wanted]

        assert len(unmounts) == 2

    def test_it_issues_no_device_command_but_unmount_and_eject(self, tmp_path):
        """Stronger than looking for a mount verb, and portable. Searching for
        one platform's word passes on the other by finding nothing."""
        source = payload_file(tmp_path, 40)
        drive = FakeDrive(bytes(40))

        burn.write_image(source, device(), total_bytes=40, chunk_bytes=16, run=drive)
        allowed = [
            burn.privileged(burn.unmount_command(device())),
            burn.privileged(burn.eject_command(device())),
        ]
        others = [
            c for c in drive.commands if not any(a.startswith("dd") for a in c) and c not in allowed
        ]

        assert others == []

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


LSBLK = """{
   "blockdevices": [
      {"name":"sdb","size":100663296,"rm":true,"model":"ZIP 100","tran":"usb","type":"disk"}
   ]
}"""

LSBLK_OLD_STRINGS = """{
   "blockdevices": [
      {"name":"sdb","size":"100663296","rm":"1","model":"ZIP 100  ","tran":"usb","type":"disk"}
   ]
}"""


class TestReadingALinuxDevice:
    """util-linux changed these fields from strings to real JSON types, and both
    shapes are still in the wild, so the parser reads either."""

    def test_it_reads_the_size(self):
        assert burn.parse_linux("sdb", LSBLK).size == ZIP100

    def test_it_reads_a_size_given_as_a_string(self):
        assert burn.parse_linux("sdb", LSBLK_OLD_STRINGS).size == ZIP100

    def test_it_reads_the_model_as_the_media_name(self):
        assert burn.parse_linux("sdb", LSBLK).media == "ZIP 100"

    def test_it_trims_the_padding_older_lsblk_leaves_on_the_model(self):
        assert burn.parse_linux("sdb", LSBLK_OLD_STRINGS).media == "ZIP 100"

    def test_it_reads_removability(self):
        assert burn.parse_linux("sdb", LSBLK).removable is True

    def test_it_reads_removability_given_as_a_string(self):
        assert burn.parse_linux("sdb", LSBLK_OLD_STRINGS).removable is True

    def test_a_fixed_disk_is_not_removable(self):
        text = LSBLK.replace('"rm":true', '"rm":false')

        assert burn.parse_linux("sdb", text).removable is False

    def test_usb_counts_as_external(self):
        assert burn.parse_linux("sdb", LSBLK).external is True

    def test_removable_media_counts_as_external_whatever_the_transport(self):
        """An internal ATAPI Zip is still not the machine's fixed storage, and
        refusing it would block the drive this tool exists for."""
        text = LSBLK.replace('"tran":"usb"', '"tran":"ata"')

        assert burn.parse_linux("sdb", text).external is True

    def test_a_fixed_sata_disk_is_not_external(self):
        text = LSBLK.replace('"rm":true', '"rm":false').replace('"tran":"usb"', '"tran":"sata"')

        assert burn.parse_linux("sdb", text).external is False

    def test_nothing_on_linux_is_reported_as_virtual(self):
        assert burn.parse_linux("sdb", LSBLK).virtual is False

    def test_the_block_and_raw_nodes_are_the_same(self):
        """Linux has no separate character device. Writing to the block device
        does not mount it, which is the property that matters."""
        found = burn.parse_linux("sdb", LSBLK)

        assert found.block == "/dev/sdb"
        assert found.raw == "/dev/sdb"

    def test_a_partition_rather_than_a_whole_disk_is_refused(self):
        text = LSBLK.replace('"type":"disk"', '"type":"part"')

        with pytest.raises(burn.DeviceError, match="whole disk"):
            burn.parse_linux("sdb", text)

    def test_output_naming_no_device_is_refused(self):
        with pytest.raises(burn.DeviceError, match="not report"):
            burn.parse_linux("sdb", '{"blockdevices": []}')

    def test_output_that_is_not_json_is_refused(self):
        with pytest.raises(burn.DeviceError, match="could not be read"):
            burn.parse_linux("sdb", "sdb 100663296 1 disk")

    def test_a_linux_device_faces_the_same_refusals(self):
        found = burn.parse_linux("sdb", LSBLK)

        assert burn.refusals(found, ZIP100) == ()

    def test_a_wrong_sized_linux_device_is_refused(self):
        text = LSBLK.replace("100663296", "500107862016")

        assert burn.refusals(burn.parse_linux("sdb", text), ZIP100)


class TestTheCommandsMatchThePlatform:
    """The write path is identical on both; only the words for unmount and eject
    differ, so they are the only thing that branches."""

    def test_macos_unmounts_the_whole_disk(self, monkeypatch):
        monkeypatch.setattr(burn.sys, "platform", "darwin")

        assert burn.unmount_command(device()) == [
            "diskutil",
            "unmountDisk",
            "force",
            "/dev/disk8",
        ]

    def test_linux_detaches_every_filesystem_on_the_disk(self, monkeypatch):
        """Linux mounts partitions, not disks, so unmounting the disk alone
        would leave sdb1 mounted and the write would fight it."""
        monkeypatch.setattr(burn.sys, "platform", "linux")

        assert "--all-targets" in burn.unmount_command(device())

    def test_macos_ejects_with_diskutil(self, monkeypatch):
        monkeypatch.setattr(burn.sys, "platform", "darwin")

        assert burn.eject_command(device())[0] == "diskutil"

    def test_linux_ejects_with_eject(self, monkeypatch):
        monkeypatch.setattr(burn.sys, "platform", "linux")

        assert burn.eject_command(device()) == ["eject", "/dev/disk8"]

    def test_both_name_the_block_device_never_the_raw_one(self, monkeypatch):
        """diskutil and eject operate on the disk, not on the transfer node."""
        for platform in ("darwin", "linux"):
            monkeypatch.setattr(burn.sys, "platform", platform)
            assert burn.eject_command(device())[-1] == "/dev/disk8"
            assert burn.unmount_command(device())[-1] == "/dev/disk8"

    def test_the_write_path_does_not_branch_on_platform(self):
        """Only the two device commands differ. If the transfer branched as well
        there would be a second implementation to keep correct.

        Read from the syntax tree with the docstring dropped, because the prose
        mentions the tools it deliberately does not name in code.
        """
        module = ast.parse(Path(burn.__file__).read_text(encoding="utf-8"))
        function = next(
            node
            for node in ast.walk(module)
            if isinstance(node, ast.FunctionDef) and node.name == "write_image"
        )
        body = function.body[1:] if ast.get_docstring(function) else function.body
        code = "\n".join(ast.dump(statement) for statement in body)

        assert "on_macos" not in code
        assert "diskutil" not in code
        assert "lsblk" not in code


class TestTheBoundaryWithTheSystem:
    """Every place this shells out, which is where it stops being testable by luck.

    Reading a device, unmounting it, ejecting it and asking whether sudo will
    answer are all one subprocess call each. They are trivial and they are also
    the only code here that can be wrong in a way the rest of the suite cannot
    see, because everything above them takes a Device that a test built.
    """

    def device(self):
        return burn.Device(
            node="disk9",
            size=100 * 1024 * 1024,
            media="ZIP 100",
            removable=True,
            external=True,
            virtual=False,
            block="/dev/disk9",
            raw="/dev/rdisk9",
        )

    def answering(self, monkeypatch, *, code=0, out=b""):
        seen = []

        def fake(command, **kwargs):
            seen.append(command)
            return subprocess.CompletedProcess(command, code, out, b"")

        monkeypatch.setattr(burn, "_run", fake)
        return seen

    def test_a_label_the_report_does_not_carry_reads_as_empty(self):
        assert burn._field("Device Node: disk9\n", "Nothing Like This") == ""

    def test_running_a_command_returns_what_it_printed(self):
        import sys

        done = burn._run([sys.executable, "-c", "print('hi')"])

        assert done.returncode == 0
        assert done.stdout.strip() == b"hi"

    def test_privilege_is_whatever_sudo_answers(self, monkeypatch):
        self.answering(monkeypatch, code=0)
        assert burn.have_privilege() is True

        self.answering(monkeypatch, code=1)
        assert burn.have_privilege() is False

    def test_unmounting_runs_the_command_for_this_platform(self, monkeypatch):
        seen = self.answering(monkeypatch)

        burn.unmount(self.device())

        assert seen and any("disk9" in part for part in seen[0])

    def test_ejecting_reports_whether_it_worked(self, monkeypatch):
        self.answering(monkeypatch, code=0)
        assert burn.eject(self.device()) is True

        self.answering(monkeypatch, code=1)
        assert burn.eject(self.device()) is False


class TestReadingADevice:
    """The four ways asking the system about a disk can go, on both platforms."""

    MAC = (
        "Device Node: /dev/disk9\n"
        "Disk Size: 100.7 MB (100663296 Bytes)\n"
        "Device / Media Name: ZIP 100\n"
        "Removable Media: Removable\n"
        "Device Location: External\n"
        "Virtual: No\n"
    )
    LINUX = (
        '{"blockdevices":[{"name":"sdb","size":100663296,"rm":true,'
        '"model":"ZIP 100","tran":"usb","type":"disk"}]}'
    )

    def arrange(self, monkeypatch, *, macos, tool=True, code=0, out=b""):
        monkeypatch.setattr(burn, "on_macos", lambda: macos)
        monkeypatch.setattr(burn.shutil, "which", lambda name: "/usr/bin/x" if tool else None)
        monkeypatch.setattr(
            burn, "_run", lambda command, **kw: subprocess.CompletedProcess(command, code, out, b"")
        )

    def test_macos_without_diskutil_says_so(self, monkeypatch):
        self.arrange(monkeypatch, macos=True, tool=False)

        with pytest.raises(burn.DeviceError, match="diskutil was not found"):
            burn.read_device("disk9")

    def test_linux_without_lsblk_says_so(self, monkeypatch):
        self.arrange(monkeypatch, macos=False, tool=False)

        with pytest.raises(burn.DeviceError, match="lsblk was not found"):
            burn.read_device("sdb")

    def test_a_device_the_tool_does_not_know_is_refused(self, monkeypatch):
        self.arrange(monkeypatch, macos=True, code=1)

        with pytest.raises(burn.DeviceError, match="no such device"):
            burn.read_device("disk9")

    def test_a_device_linux_does_not_know_is_refused(self, monkeypatch):
        self.arrange(monkeypatch, macos=False, code=1)

        with pytest.raises(burn.DeviceError, match="no such device"):
            burn.read_device("sdb")

    def test_macos_reports_a_disk(self, monkeypatch):
        self.arrange(monkeypatch, macos=True, out=self.MAC.encode())

        found = burn.read_device("disk9")

        assert found.media == "ZIP 100"
        assert found.removable is True

    def test_linux_reports_a_disk(self, monkeypatch):
        self.arrange(monkeypatch, macos=False, out=self.LINUX.encode())

        found = burn.read_device("sdb")

        assert found.media == "ZIP 100"
        assert found.removable is True
