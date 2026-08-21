"""What a writer copies to a disk, and the identity that disk gets.

Two jobs. Find the prefix of an image that actually carries data, so writing a
96 MiB image to a drive managing about 765 kB/s does not spend minutes on zeroes.
And stamp a volume serial, because images deliberately carry none and real mode
DOS uses the serial to notice the media changed. Two disks sharing one can have it
serve a cached FAT from the previous disk after a swap, which reads as corruption.

The serial is an argument rather than something the function invents, so these
tests can pin it and the result stays a pure function of its inputs.
"""

from __future__ import annotations

import struct

import pytest

from z64kit.fat import image, payload
from z64kit.fat.writer import ROOT, Volume

SERIAL_OFFSET = image.PART_START_LBA * image.SECTOR + 39


def blank() -> bytes:
    return image.blank_image()


def with_files(*sizes: int) -> bytes:
    volume = Volume()
    for index, size in enumerate(sizes):
        volume.add_file(ROOT, f"F{index}", "Z64", bytes(size))
    return volume.to_bytes()


class TestItRefusesAnythingThatIsNotAZipImage:
    def test_it_refuses_a_file_of_the_wrong_size(self):
        with pytest.raises(payload.ImageRejectedError, match="expected"):
            payload.prepare(bytes(1024), serial=1)

    def test_it_names_the_size_it_got_and_the_size_it_wanted(self):
        with pytest.raises(payload.ImageRejectedError) as raised:
            payload.prepare(bytes(1024), serial=1)

        assert "1024" in str(raised.value)
        assert str(image.TOTAL_SECTORS * image.SECTOR) in str(raised.value)

    def test_it_refuses_an_image_with_no_mbr_signature(self):
        broken = bytearray(blank())
        broken[510:512] = b"\x00\x00"

        with pytest.raises(payload.ImageRejectedError, match="MBR signature"):
            payload.prepare(bytes(broken), serial=1)

    def test_it_refuses_the_lba_partition_type_real_mode_dos_cannot_read(self):
        broken = bytearray(blank())
        broken[446 + 4] = 0x0E

        with pytest.raises(payload.ImageRejectedError, match="0x0E"):
            payload.prepare(bytes(broken), serial=1)

    def test_it_refuses_a_boot_record_claiming_zero_sectors_per_cluster(self):
        broken = bytearray(blank())
        broken[image.PART_START_LBA * image.SECTOR + 13] = 0

        with pytest.raises(payload.ImageRejectedError, match="sectors per cluster"):
            payload.prepare(bytes(broken), serial=1)


class TestTheExtentCoversExactlyWhatIsUsed:
    def test_an_empty_volume_stops_after_its_metadata(self):
        found = payload.prepare(blank(), serial=1)

        assert found.sectors == image.data_lba()

    def test_an_empty_volume_reports_no_allocated_cluster(self):
        found = payload.prepare(blank(), serial=1)

        assert found.highest_cluster == 1

    def test_one_file_extends_the_payload_past_the_metadata(self):
        found = payload.prepare(with_files(image.SECTOR * 4), serial=1)

        assert found.sectors > image.data_lba()

    def test_the_payload_ends_on_the_last_used_cluster(self):
        one_cluster = image.SECTORS_PER_CLUSTER * image.SECTOR
        found = payload.prepare(with_files(one_cluster), serial=1)

        assert found.highest_cluster == 2
        assert found.sectors == found.data_start_lba + image.SECTORS_PER_CLUSTER

    def test_a_bigger_file_produces_a_bigger_payload(self):
        one_cluster = image.SECTORS_PER_CLUSTER * image.SECTOR
        small = payload.prepare(with_files(one_cluster), serial=1)
        large = payload.prepare(with_files(one_cluster * 8), serial=1)

        assert large.sectors > small.sectors

    def test_it_never_claims_more_than_the_image_holds(self):
        found = payload.prepare(with_files(4 * 1024 * 1024), serial=1)

        assert found.size <= image.TOTAL_SECTORS * image.SECTOR

    def test_the_body_is_exactly_the_sectors_it_reports(self):
        found = payload.prepare(with_files(image.SECTOR * 4), serial=1)

        assert len(found.body) == found.sectors * image.SECTOR
        assert len(found.body) == found.size

    def test_the_body_matches_the_image_it_came_from(self):
        source = with_files(image.SECTOR * 4)
        found = payload.prepare(source, serial=0)

        assert found.body == source[: found.size]


class TestTheDiskGetsAnIdentityTheImageDoesNotHave:
    def test_the_image_itself_carries_no_serial(self):
        assert struct.unpack_from("<I", blank(), SERIAL_OFFSET)[0] == 0

    def test_the_payload_carries_the_serial_it_was_given(self):
        found = payload.prepare(blank(), serial=0xDEADBEEF)

        assert struct.unpack_from("<I", found.body, SERIAL_OFFSET)[0] == 0xDEADBEEF

    def test_it_reports_the_serial_it_wrote(self):
        found = payload.prepare(blank(), serial=0xDEADBEEF)

        assert found.serial == 0xDEADBEEF

    def test_two_disks_from_one_image_can_differ(self):
        first = payload.prepare(blank(), serial=1)
        second = payload.prepare(blank(), serial=2)

        assert first.body != second.body

    def test_they_differ_only_in_the_serial(self):
        first = bytearray(payload.prepare(blank(), serial=1).body)
        second = bytearray(payload.prepare(blank(), serial=2).body)
        first[SERIAL_OFFSET : SERIAL_OFFSET + 4] = b"\x00\x00\x00\x00"
        second[SERIAL_OFFSET : SERIAL_OFFSET + 4] = b"\x00\x00\x00\x00"

        assert first == second

    def test_a_serial_wider_than_the_field_is_truncated_rather_than_overflowing(self):
        found = payload.prepare(blank(), serial=0x1_FFFF_FFFF)

        assert found.serial == 0xFFFFFFFF
        assert struct.unpack_from("<I", found.body, SERIAL_OFFSET)[0] == 0xFFFFFFFF

    def test_the_same_serial_twice_gives_the_same_bytes(self):
        first = payload.prepare(blank(), serial=0x12345678)
        second = payload.prepare(blank(), serial=0x12345678)

        assert first.body == second.body

    def test_no_volume_label_is_written(self):
        found = payload.prepare(blank(), serial=1)
        label_offset = image.PART_START_LBA * image.SECTOR + 43

        assert found.body[label_offset : label_offset + 11] == b" " * 11


class TestHighestUsedCluster:
    def test_an_untouched_table_reports_nothing_allocated(self):
        assert payload.highest_used_cluster(bytes(512), 256) == 1

    def test_it_finds_the_last_non_zero_entry(self):
        table = bytearray(512)
        struct.pack_into("<H", table, 2 * 2, 0xFFFF)
        struct.pack_into("<H", table, 9 * 2, 0xFFFF)

        assert payload.highest_used_cluster(bytes(table), 256) == 9

    def test_a_gap_does_not_stop_the_search(self):
        table = bytearray(512)
        struct.pack_into("<H", table, 2 * 2, 0xFFFF)
        struct.pack_into("<H", table, 40 * 2, 0xFFFF)

        assert payload.highest_used_cluster(bytes(table), 256) == 40

    def test_it_ignores_the_two_reserved_entries(self):
        table = bytearray(512)
        struct.pack_into("<H", table, 0, 0xFFF8)
        struct.pack_into("<H", table, 2, 0xFFFF)

        assert payload.highest_used_cluster(bytes(table), 256) == 1
