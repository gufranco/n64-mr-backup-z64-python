import struct

import pytest

from z64kit.fat import image, writer


@pytest.fixture(scope="module")
def blank():
    return image.blank_image()


class TestGeometry:
    def test_the_media_is_exactly_one_hundred_megabytes(self):
        assert image.TOTAL_SECTORS * image.SECTOR == 100_663_296

    def test_the_native_geometry_multiplies_out_to_the_media_size(self):
        assert image.CYLINDERS * image.HEADS * image.SECTORS_PER_TRACK == image.TOTAL_SECTORS

    def test_usable_capacity_excludes_the_filesystem_metadata(self):
        assert image.usable_capacity() == 100_431_872

    def test_usable_capacity_is_cluster_aligned_not_merely_sector_aligned(self):
        sectors_left_after_metadata = (
            image.partition_sectors()
            - image.RESERVED_SECTORS
            - image.NUM_FATS * image.SECTORS_PER_FAT
            - image.root_sectors()
        )
        sector_aligned = sectors_left_after_metadata * image.SECTOR

        assert image.usable_capacity() < sector_aligned
        assert sector_aligned - image.usable_capacity() == 3 * image.SECTOR

    def test_the_alignment_loss_does_not_change_how_many_games_fit(self):
        from z64kit import packing

        assert packing.units_for_capacity(image.usable_capacity()) == 23

    def test_an_empty_volume_only_needs_its_metadata_written(self):
        assert image.metadata_extent_sectors() == 449

    def test_three_large_roms_would_need_the_whole_raw_disk(self):
        assert image.usable_capacity() < 3 * 32 * 1024 * 1024


class TestBlankImage:
    def test_is_exactly_the_media_size(self, blank):
        assert len(blank) == 100_663_296

    def test_is_reproducible(self):
        assert image.blank_image() == image.blank_image()

    def test_only_the_metadata_region_is_non_zero(self, blank):
        tail = blank[image.metadata_extent_sectors() * image.SECTOR :]

        assert tail.count(0) == len(tail)

    def test_carries_no_entropy_beyond_a_few_hundred_bytes(self, blank):
        assert sum(1 for b in blank if b) < 300


class TestMasterBootRecord:
    def test_ends_with_the_boot_signature(self, blank):
        assert blank[510:512] == b"\x55\xaa"

    def test_declares_the_partition_type_real_mode_dos_understands(self, blank):
        assert blank[446 + 4] == 0x06

    def test_does_not_use_the_lba_partition_type(self, blank):
        assert blank[446 + 4] != 0x0E

    def test_the_partition_starts_one_track_in(self, blank):
        start = struct.unpack_from("<I", blank, 446 + 8)[0]

        assert start == image.PART_START_LBA == 32

    def test_the_partition_covers_the_rest_of_the_media(self, blank):
        count = struct.unpack_from("<I", blank, 446 + 12)[0]

        assert count == image.TOTAL_SECTORS - image.PART_START_LBA

    def test_the_start_address_matches_the_native_geometry(self, blank):
        head, sector_field, cylinder = blank[447], blank[448], blank[449]

        assert (head, sector_field & 0x3F, cylinder) == (1, 1, 0)

    def test_the_partition_is_not_marked_bootable(self, blank):
        assert blank[446] == 0x00

    def test_the_remaining_partition_slots_are_empty(self, blank):
        assert blank[462:510].count(0) == 48


class TestBootSector:
    def test_starts_with_a_jump_instruction(self, blank):
        boot = blank[image.PART_START_LBA * image.SECTOR :]

        assert boot[0] == 0xEB
        assert boot[2] == 0x90

    def test_declares_an_oem_name_old_dos_accepts(self, blank):
        boot = blank[image.PART_START_LBA * image.SECTOR :]

        assert boot[3:11] == b"MSDOS5.0"

    def test_declares_the_expected_cluster_and_fat_layout(self, blank):
        boot = blank[image.PART_START_LBA * image.SECTOR :]

        assert struct.unpack_from("<H", boot, 11)[0] == 512
        assert boot[13] == image.SECTORS_PER_CLUSTER == 4
        assert boot[16] == image.NUM_FATS == 2
        assert struct.unpack_from("<H", boot, 17)[0] == image.ROOT_ENTRIES == 512
        assert struct.unpack_from("<H", boot, 22)[0] == image.SECTORS_PER_FAT

    def test_declares_the_geometry_the_unit_expects(self, blank):
        boot = blank[image.PART_START_LBA * image.SECTOR :]

        assert struct.unpack_from("<H", boot, 24)[0] == image.SECTORS_PER_TRACK
        assert struct.unpack_from("<H", boot, 26)[0] == image.HEADS
        assert struct.unpack_from("<I", boot, 28)[0] == image.PART_START_LBA

    def test_uses_the_fixed_disk_media_descriptor(self, blank):
        boot = blank[image.PART_START_LBA * image.SECTOR :]

        assert boot[21] == 0xF8

    def test_identifies_itself_as_fat16(self, blank):
        boot = blank[image.PART_START_LBA * image.SECTOR :]

        assert boot[54:62] == b"FAT16   "

    def test_the_volume_serial_is_zero_so_the_image_is_deterministic(self, blank):
        boot = blank[image.PART_START_LBA * image.SECTOR :]

        assert struct.unpack_from("<I", boot, 39)[0] == 0

    def test_no_caller_can_set_a_serial(self):
        """Identity belongs to a physical disk, stamped when one is written."""
        import inspect

        assert inspect.signature(image.blank_image).parameters == {}


class TestClusterCount:
    def test_stays_inside_the_range_that_makes_a_volume_fat16(self):
        assert 4085 <= image.cluster_count() <= 65524

    def test_the_declared_fat_is_large_enough_for_every_cluster(self):
        needed = -(-((image.cluster_count() + 2) * 2) // image.SECTOR)

        assert needed <= image.SECTORS_PER_FAT


class TestVolumeLabel:
    def test_the_boot_sector_carries_no_name(self):
        boot = image.blank_image()[image.PART_START_LBA * image.SECTOR :]

        assert boot[43:54] == image.NO_LABEL

    def test_no_caller_can_set_one(self):
        import inspect

        assert inspect.signature(image.boot_sector).parameters == {}
        assert inspect.signature(image.empty_root).parameters == {}

    def test_the_root_directory_is_entirely_empty(self):
        """With no label there is no entry at all, so every slot reads as free."""
        data = image.blank_image()
        root = data[image.root_lba() * image.SECTOR :][: image.root_sectors() * image.SECTOR]

        assert set(root) == {0}

    def test_that_constant_decodes_to_the_expected_moment(self):
        year = 1980 + (image.TZ_DATE >> 9)
        month = (image.TZ_DATE >> 5) & 0x0F
        day = image.TZ_DATE & 0x1F
        hour = image.TZ_TIME >> 11
        minute = (image.TZ_TIME >> 5) & 0x3F

        assert (year, month, day, hour, minute) == (1996, 12, 24, 23, 32)


class TestFatTables:
    def test_both_copies_start_with_the_media_descriptor(self, blank):
        first = image.fat_lba(0) * image.SECTOR
        second = image.fat_lba(1) * image.SECTOR

        assert blank[first : first + 4] == b"\xf8\xff\xff\xff"
        assert blank[second : second + 4] == b"\xf8\xff\xff\xff"

    def test_no_cluster_is_allocated_on_a_blank_volume(self, blank):
        start = image.fat_lba(0) * image.SECTOR
        table = blank[start + 4 : start + image.SECTORS_PER_FAT * image.SECTOR]

        assert table.count(0) == len(table)


class TestNoVolumeLabel:
    """Images carry no volume label at all.

    A label is a name, and a name is a thing that differs between disks for no
    benefit the unit uses. Leaving it out makes every blank volume byte-identical
    and frees the first root slot for a file.

    An empty string is not the same as absent: passing one used to write eleven
    spaces into a directory entry, which is a label whose name happens to be
    blank. Nothing here writes that entry at all.
    """

    def root_at(self, raw: bytes) -> int:
        return (
            image.PART_START_LBA + image.RESERVED_SECTORS + image.NUM_FATS * image.SECTORS_PER_FAT
        ) * image.SECTOR

    def test_the_boot_record_carries_no_label(self):
        raw = image.blank_image()

        vbr = raw[image.PART_START_LBA * image.SECTOR :][:512]

        assert vbr[43:54] == b" " * 11

    def test_the_root_directory_starts_empty(self):
        raw = image.blank_image()

        assert raw[self.root_at(raw)] == 0x00

    def test_no_entry_anywhere_claims_to_be_a_label(self):
        raw = image.blank_image()
        root = self.root_at(raw)

        for slot in range(image.ROOT_ENTRIES):
            entry = raw[root + slot * 32 : root + (slot + 1) * 32]
            assert not entry[11] & image.ATTR_VOLUME_LABEL

    def test_every_blank_volume_is_byte_identical(self):
        assert image.blank_image() == image.blank_image()

    def test_the_serial_is_zero(self):
        vbr = image.blank_image()[image.PART_START_LBA * image.SECTOR :][:512]

        assert struct.unpack("<I", vbr[39:43])[0] == image.NO_SERIAL

    def test_two_volumes_holding_the_same_files_are_the_same_bytes(self):
        one, two = writer.Volume(), writer.Volume()
        for volume in (one, two):
            volume.add_file(writer.ROOT, "GAME", "Z64", b"\x01" * 4096)

        assert one.to_bytes() == two.to_bytes()

    def test_the_first_root_slot_is_available_to_a_file(self):
        volume = writer.Volume()
        volume.add_file(writer.ROOT, "GAME", "Z64", b"\x00" * 4096)

        raw = volume.to_bytes()
        first = raw[self.root_at(raw) : self.root_at(raw) + 11]

        assert first == b"GAME    Z64"
