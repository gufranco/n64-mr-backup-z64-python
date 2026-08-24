import pytest

from z64kit import scan
from z64kit.conftest import make_rom


def write_rom(folder, name, **kw):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(make_rom(**kw))
    return path


class TestScanFlatFolder:
    def test_finds_every_rom(self, tmp_path):
        write_rom(tmp_path, "One (USA).z64", cart="AA")
        write_rom(tmp_path, "Two (USA).z64", cart="BB")

        found = scan.scan(tmp_path)

        assert len(found.games) == 2

    def test_reports_no_disk_grouping_for_a_flat_folder(self, tmp_path):
        write_rom(tmp_path, "One (USA).z64")

        assert scan.scan(tmp_path).is_curated is False

    def test_reads_identity_from_the_content(self, tmp_path):
        write_rom(tmp_path, "Mislabelled.z64", title="REAL TITLE", cart="ZZ", region="E")

        game = scan.scan(tmp_path).games[0]

        assert game.internal_name == "REAL TITLE"
        assert game.game_code == "NZZE"
        assert game.region == "USA"

    def test_records_the_true_byte_order(self, tmp_path):
        write_rom(tmp_path, "Swapped.z64", order="v64")

        game = scan.scan(tmp_path).games[0]

        assert game.byte_order == "byteswapped"
        assert game.true_extension == "V64"

    def test_flags_a_file_whose_extension_lies(self, tmp_path):
        write_rom(tmp_path, "Swapped.z64", order="v64")

        game = scan.scan(tmp_path).games[0]

        assert game.extension_mismatch is True

    def test_accepts_a_file_whose_extension_is_honest(self, tmp_path):
        write_rom(tmp_path, "Plain.z64", order="z64")

        assert scan.scan(tmp_path).games[0].extension_mismatch is False

    def test_skips_a_file_with_an_extension_the_unit_ignores(self, tmp_path):
        write_rom(tmp_path, "Game (USA).z64")
        (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

        found = scan.scan(tmp_path)

        assert len(found.games) == 1
        assert any("notes.txt" in s.path for s in found.skipped)

    def test_skips_hidden_files(self, tmp_path):
        write_rom(tmp_path, "Game (USA).z64")
        (tmp_path / ".DS_Store").write_bytes(b"\x00" * 16)

        assert len(scan.scan(tmp_path).games) == 1

    def test_reports_a_file_that_is_not_a_rom_despite_its_extension(self, tmp_path):
        (tmp_path / "Broken (USA).z64").write_bytes(b"not a rom at all" * 8)

        found = scan.scan(tmp_path)

        assert found.games == ()
        assert any("no recognisable" in s.reason for s in found.skipped)

    def test_orders_games_deterministically(self, tmp_path):
        for name in ("Zebra (USA).z64", "Alpha (USA).z64", "Mike (USA).z64"):
            write_rom(tmp_path, name, cart=name[:2].upper())

        names = [g.filename for g in scan.scan(tmp_path).games]

        assert names == sorted(names)


class TestScanCuratedFolder:
    def test_detects_one_subfolder_per_disk(self, tmp_path):
        write_rom(tmp_path / "Zip Disk 01", "One (USA).z64", cart="AA")
        write_rom(tmp_path / "Zip Disk 02", "Two (USA).z64", cart="BB")

        found = scan.scan(tmp_path)

        assert found.is_curated is True
        assert found.disk_names == ("Zip Disk 01", "Zip Disk 02")

    def test_remembers_which_disk_each_game_came_from(self, tmp_path):
        write_rom(tmp_path / "Zip Disk 01", "One (USA).z64", cart="AA")
        write_rom(tmp_path / "Zip Disk 02", "Two (USA).z64", cart="BB")

        by_disk = {g.filename: g.disk for g in scan.scan(tmp_path).games}

        assert by_disk["One (USA).z64"] == "Zip Disk 01"
        assert by_disk["Two (USA).z64"] == "Zip Disk 02"

    def test_ignores_a_hidden_subfolder(self, tmp_path):
        write_rom(tmp_path / "Zip Disk 01", "One (USA).z64")
        write_rom(tmp_path / ".backup", "Old (USA).z64", cart="XX")

        found = scan.scan(tmp_path)

        assert found.disk_names == ("Zip Disk 01",)
        assert len(found.games) == 1

    def test_a_custom_prefix_is_honoured(self, tmp_path):
        write_rom(tmp_path / "Disc A", "One (USA).z64")

        found = scan.scan(tmp_path, disk_prefix="Disc")

        assert found.is_curated is True


class TestCompanionFiles:
    def test_a_patch_beside_a_rom_is_collected(self, tmp_path):
        write_rom(tmp_path, "Game (USA).z64")
        (tmp_path / "Game (USA).aps").write_bytes(b"APS10" + bytes(0x60))

        found = scan.scan(tmp_path)

        assert len(found.companions) == 1
        assert found.companions[0].extension == "APS"

    def test_a_save_file_beside_a_rom_is_collected(self, tmp_path):
        write_rom(tmp_path, "Game (USA).z64")
        (tmp_path / "Game (USA).ram").write_bytes(bytes(65536))

        assert scan.scan(tmp_path).companions[0].extension == "RAM"

    def test_companions_are_not_counted_as_games(self, tmp_path):
        write_rom(tmp_path, "Game (USA).z64")
        (tmp_path / "Game (USA).ram").write_bytes(bytes(16))

        assert len(scan.scan(tmp_path).games) == 1


class TestTotals:
    def test_sums_the_bytes_of_every_game(self, tmp_path):
        write_rom(tmp_path, "One (USA).z64", cart="AA", size=4 * 1024 * 1024)
        write_rom(tmp_path, "Two (USA).z64", cart="BB", size=8 * 1024 * 1024)

        assert scan.scan(tmp_path).total_bytes == 12 * 1024 * 1024

    def test_an_empty_folder_scans_without_failing(self, tmp_path):
        found = scan.scan(tmp_path)

        assert found.games == ()
        assert found.total_bytes == 0

    def test_a_missing_folder_is_reported_clearly(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            scan.scan(tmp_path / "nope")


class TestALittleEndianDump:
    """The one byte order the unit's extension table does not list.

    A .n64 dump loads as garbage rather than failing cleanly, so the scan says
    so by name instead of leaving the reader to find out on hardware.
    """

    def test_it_is_named_in_the_warnings(self, tmp_path):
        """The dump is little endian and the filename says otherwise.

        A file actually named `.n64` is skipped on its extension before this
        line is reached. The case that gets here is a little endian dump wearing
        a `.z64` name, which is the one that would otherwise load as garbage.
        """
        from z64kit.conftest import make_rom

        root = tmp_path / "roms"
        root.mkdir()
        (root / "Game (USA).z64").write_bytes(make_rom(order="n64"))

        found = scan.scan(str(root))

        assert any("little endian" in warning for warning in found.warnings)


class TestAHiddenFile:
    def test_it_is_recorded_as_skipped_rather_than_scanned(self, tmp_path):
        from z64kit.conftest import make_rom

        root = tmp_path / "roms"
        root.mkdir()
        (root / ".DS_Store").write_bytes(b"junk")
        (root / "Game (USA).z64").write_bytes(make_rom())

        found = scan.scan(str(root))

        assert any(one.reason == "hidden file" for one in found.skipped)


class TestADirectoryInsideADiskFolder:
    """A folder nested inside a disk folder, which a reader can easily make.

    It is not a file, so it is passed over without being recorded as skipped.
    Recording it would put a directory in a list the reader reads as files that
    could not be used.
    """

    def test_it_is_neither_scanned_nor_recorded_as_skipped(self, tmp_path):
        from z64kit.conftest import make_rom

        root = tmp_path / "roms"
        disk = root / "Zip Disk 01"
        disk.mkdir(parents=True)
        (disk / "Game (USA).z64").write_bytes(make_rom())
        (disk / "extras").mkdir()

        found = scan.scan(str(root))

        assert len(found.games) == 1
        assert not any("extras" in one.path for one in found.skipped)
