import hashlib
import struct

import pytest

from z64kit.fat import image, writer


def payload(size, seed=0xAB):
    return bytes(((i * 37 + seed) & 0xFF) for i in range(size))


@pytest.fixture
def volume():
    return writer.Volume(label="Z64")


class TestNames:
    def test_pads_a_short_name_to_the_fat_layout(self):
        assert writer.pad83("MARIO64", "Z64") == b"MARIO64 Z64"

    def test_truncates_an_over_long_base(self):
        assert writer.pad83("VERYLONGNAME", "Z64") == b"VERYLONGZ64"

    def test_uppercases(self):
        assert writer.pad83("mario", "z64") == b"MARIO   Z64"

    def test_formats_a_stored_name_for_display(self):
        assert writer.display_name(b"MARIO64 Z64") == "MARIO64.Z64"

    def test_displays_an_extensionless_entry_without_a_dot(self):
        assert writer.display_name(b"SUBDIR     ") == "SUBDIR"


class TestAddFile:
    def test_a_written_file_reads_back_identically(self, volume):
        data = payload(9000)

        volume.add_file(writer.ROOT, "TEST", "BIN", data)

        assert volume.read_file("TEST", "BIN") == data

    def test_a_file_occupies_whole_clusters(self, volume):
        volume.add_file(writer.ROOT, "TEST", "BIN", payload(1))

        assert volume.free_clusters() == image.cluster_count() - 1

    def test_an_empty_file_still_gets_one_cluster(self, volume):
        volume.add_file(writer.ROOT, "EMPTY", "BIN", b"")

        assert volume.free_clusters() == image.cluster_count() - 1

    def test_files_are_laid_out_contiguously_in_order(self, volume):
        first = volume.add_file(writer.ROOT, "ONE", "BIN", payload(4096))
        second = volume.add_file(writer.ROOT, "TWO", "BIN", payload(4096))

        assert second.first_cluster == first.last_cluster + 1

    def test_reports_where_a_file_landed_on_the_media(self, volume):
        placed = volume.add_file(writer.ROOT, "ONE", "BIN", payload(4096))

        assert placed.start_lba == image.data_lba()
        assert 0 <= placed.media_percent < 1

    def test_refuses_a_duplicate_name(self, volume):
        volume.add_file(writer.ROOT, "SAME", "BIN", payload(16))

        with pytest.raises(writer.NameCollisionError, match="SAME"):
            volume.add_file(writer.ROOT, "SAME", "BIN", payload(16))

    def test_refuses_a_file_larger_than_the_volume(self, volume):
        with pytest.raises(writer.OutOfSpaceError):
            volume.add_file(writer.ROOT, "HUGE", "BIN", b"\x00" * (image.usable_capacity() + 1))

    def test_reports_remaining_space_accurately(self, volume):
        before = volume.free_bytes()

        volume.add_file(writer.ROOT, "ONE", "BIN", payload(2048 * 3))

        assert volume.free_bytes() == before - 2048 * 3


class TestDirectories:
    def test_a_subdirectory_can_hold_a_file(self, volume):
        sub = volume.make_dir(writer.ROOT, "GAMES")

        volume.add_file(sub, "INNER", "BIN", payload(64))

        assert volume.read_file("INNER", "BIN", parent=sub) == payload(64)

    def test_a_subdirectory_carries_the_dot_entries_dos_requires(self, volume):
        sub = volume.make_dir(writer.ROOT, "GAMES")

        entries = volume.list_dir(sub)

        assert entries[0].name == b".          "
        assert entries[1].name == b"..         "

    def test_the_parent_pointer_of_a_root_child_is_zero(self, volume):
        sub = volume.make_dir(writer.ROOT, "GAMES")

        entries = volume.list_dir(sub)

        assert entries[1].cluster == 0

    def test_the_root_directory_has_a_finite_capacity(self, volume):
        for index in range(image.ROOT_ENTRIES - 1):
            volume.add_file(writer.ROOT, f"F{index:07d}"[:8], "B", b"")

        with pytest.raises(writer.DirectoryFullError):
            volume.add_file(writer.ROOT, "OVERFLOW", "B", b"")

    def test_a_subdirectory_grows_beyond_its_first_cluster(self, volume):
        sub = volume.make_dir(writer.ROOT, "GAMES")
        per_cluster = image.SECTORS_PER_CLUSTER * image.SECTOR // writer.ENTRY_SIZE

        for index in range(per_cluster):
            volume.add_file(sub, f"F{index:07d}"[:8], "B", b"")

        assert len(volume.list_dir(sub)) == per_cluster + 2

    def test_a_grown_subdirectory_still_reads_back_every_file(self, volume):
        sub = volume.make_dir(writer.ROOT, "GAMES")
        per_cluster = image.SECTORS_PER_CLUSTER * image.SECTOR // writer.ENTRY_SIZE

        for index in range(per_cluster):
            volume.add_file(sub, f"F{index:07d}"[:8], "B", payload(8, seed=index))

        assert volume.read_file("F0000063"[:8], "B", parent=sub) == payload(8, seed=63)

    def test_refuses_a_duplicate_inside_a_subdirectory(self, volume):
        sub = volume.make_dir(writer.ROOT, "GAMES")
        volume.add_file(sub, "SAME", "BIN", b"")

        with pytest.raises(writer.NameCollisionError):
            volume.add_file(sub, "SAME", "BIN", b"")

    def test_refuses_a_duplicate_directory_name(self, volume):
        volume.make_dir(writer.ROOT, "GAMES")

        with pytest.raises(writer.NameCollisionError):
            volume.make_dir(writer.ROOT, "GAMES")

    def test_reading_a_missing_file_raises(self, volume):
        with pytest.raises(FileNotFoundError, match="NOPE"):
            volume.read_file("NOPE", "BIN")

    def test_long_name_entries_are_ignored_when_listing(self, volume):
        volume.add_file(writer.ROOT, "REAL", "BIN", b"")
        buffer = volume._dir_buffer(writer.ROOT)
        buffer[64] = 0x41
        buffer[64 + 11] = writer.ATTR_LONG_NAME
        volume._store_dir(writer.ROOT, buffer)

        listed = [e for e in volume.list_dir(writer.ROOT) if not e.is_label]

        assert len(listed) == 1


class TestFlushing:
    def test_subdirectory_content_survives_serialisation(self, volume):
        sub = volume.make_dir(writer.ROOT, "GAMES")
        volume.add_file(sub, "INNER", "BIN", payload(4096))

        raw = volume.to_bytes()
        sub_offset = (image.data_lba() + (sub - 2) * image.SECTORS_PER_CLUSTER) * image.SECTOR

        assert raw[sub_offset : sub_offset + 11] == b".          "
        assert raw[sub_offset + 32 : sub_offset + 43] == b"..         "

    def test_serialisation_does_not_mutate_the_volume(self, volume):
        volume.add_file(writer.ROOT, "TEST", "BIN", payload(2048))

        first = volume.to_bytes()
        second = volume.to_bytes()

        assert first == second


class TestSorting:
    def test_entries_are_sorted_by_stored_name(self, volume):
        for name in ("ZEBRA", "ALPHA", "MIKE"):
            volume.add_file(writer.ROOT, name, "BIN", b"")

        volume.sort_directories()
        listed = [
            e.name[:8].decode().rstrip() for e in volume.list_dir(writer.ROOT) if not e.is_label
        ]

        assert listed == ["ALPHA", "MIKE", "ZEBRA"]

    def test_the_volume_label_stays_first(self, volume):
        volume.add_file(writer.ROOT, "AAAA", "BIN", b"")

        volume.sort_directories()

        assert volume.list_dir(writer.ROOT)[0].is_label

    def test_directories_sort_before_files(self, volume):
        volume.add_file(writer.ROOT, "AAAA", "BIN", b"")
        volume.make_dir(writer.ROOT, "ZZZZ")

        volume.sort_directories()
        listed = [e for e in volume.list_dir(writer.ROOT) if not e.is_label]

        assert listed[0].is_dir

    def test_sorting_by_an_external_key_is_possible(self, volume):
        volume.add_file(writer.ROOT, "ZEBRA", "BIN", b"")
        volume.add_file(writer.ROOT, "ALPHA", "BIN", b"")

        volume.sort_directories(key={"ZEBRA.BIN": "aaa", "ALPHA.BIN": "zzz"})
        listed = [
            e.name[:8].decode().rstrip() for e in volume.list_dir(writer.ROOT) if not e.is_label
        ]

        assert listed == ["ZEBRA", "ALPHA"]

    def test_dot_entries_are_never_reordered(self, volume):
        sub = volume.make_dir(writer.ROOT, "GAMES")
        volume.add_file(sub, "AAA", "BIN", b"")

        volume.sort_directories()
        entries = volume.list_dir(sub)

        assert entries[0].name.startswith(b".")
        assert entries[1].name.startswith(b"..")


class TestTimestamps:
    def test_every_entry_carries_the_fixed_constant(self, volume):
        volume.add_file(writer.ROOT, "TEST", "BIN", b"")

        raw = volume.to_bytes()
        root = raw[image.root_lba() * image.SECTOR :]
        entry = root[32:64]

        assert struct.unpack_from("<H", entry, 22)[0] == image.TZ_TIME
        assert struct.unpack_from("<H", entry, 24)[0] == image.TZ_DATE


class TestDeterminism:
    def test_the_same_content_produces_the_same_bytes(self):
        def build():
            vol = writer.Volume(label="Z64")
            vol.add_file(writer.ROOT, "ONE", "BIN", payload(5000))
            vol.add_file(writer.ROOT, "TWO", "BIN", payload(9000, seed=3))
            vol.sort_directories()
            return vol.to_bytes()

        assert hashlib.sha256(build()).hexdigest() == hashlib.sha256(build()).hexdigest()

    def test_an_untouched_volume_equals_a_blank_image(self, volume):
        assert volume.to_bytes() == image.blank_image(label="Z64")


class TestVerification:
    def test_verifies_a_correctly_written_volume(self, volume):
        volume.add_file(writer.ROOT, "TEST", "BIN", payload(7000))

        assert volume.verify() == []

    def test_reports_the_file_when_a_cluster_is_corrupted(self, volume):
        volume.add_file(writer.ROOT, "TEST", "BIN", payload(7000))
        volume.corrupt_for_test(image.data_lba())

        assert volume.verify() == ["TEST.BIN"]
