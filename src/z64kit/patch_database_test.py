"""Tests for treating the unit's patch database as one file rather than 75.

The unit loads `z64patch.dat` from the ROM directory and finds patches inside it
by itself. Extracting those patches into a folder so the tool could place them
individually was work nobody needed: one file on the disk covers all of them, and
the reader only has to obtain one thing.

Only patches that are genuinely absent from the database still have to be supplied
on their own, and those are the ones this keeps asking for.
"""

from z64kit import artifacts

DATABASE = "z64patch.dat"


class TestTheDatabaseIsAFolderFile:
    def test_the_database_is_expected_in_the_folder(self):
        manifest = artifacts.load_default_manifest()

        names = {e.filename for e in artifacts.folder_entries(manifest)}

        assert DATABASE in names

    def test_the_database_is_not_listed_as_firmware(self):
        manifest = artifacts.load_default_manifest()

        entry = next(e for e in manifest.entries() if e.filename == DATABASE)

        assert entry.kind == "patch-db"

    def test_a_patch_inside_the_database_is_not_expected_separately(self):
        manifest = artifacts.load_default_manifest()

        names = {e.filename for e in artifacts.folder_entries(manifest)}

        assert "cc-usa.aps" not in names

    def test_a_patch_absent_from_the_database_is_still_expected(self):
        manifest = artifacts.load_default_manifest()

        names = {e.filename for e in artifacts.folder_entries(manifest)}

        assert "banjo.zps" in names

    def test_a_companion_save_is_still_expected(self):
        manifest = artifacts.load_default_manifest()

        names = {e.filename for e in artifacts.folder_entries(manifest)}

        assert "dk64-usa.ram" in names

    def test_the_folder_asks_for_far_fewer_files_than_before(self):
        manifest = artifacts.load_default_manifest()

        assert len(artifacts.folder_entries(manifest)) <= 20

    def test_every_patch_inside_the_database_is_marked_as_such(self):
        manifest = artifacts.load_default_manifest()

        inside = [e for e in manifest.entries() if e.in_patch_database]

        assert len(inside) >= 60

    def test_nothing_marked_as_inside_is_also_expected_separately(self):
        manifest = artifacts.load_default_manifest()
        names = {e.filename for e in artifacts.folder_entries(manifest)}

        for entry in manifest.entries():
            if entry.in_patch_database:
                assert entry.filename not in names


class TestTheDocumentExplainsIt:
    def test_it_names_the_database_as_the_one_file_to_obtain(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert DATABASE in text

    def test_it_says_the_unit_reads_the_database_itself(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "reads it" in text.lower() or "loads it" in text.lower()

    def test_it_still_lists_what_the_database_covers_for_reference(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        assert "cc-usa.aps" in text

    def test_the_reference_list_is_marked_as_not_needing_separate_copies(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())

        section = text.split("## Already inside the patch database")[1]

        assert "cc-usa.aps" in section

    def test_it_does_not_ask_the_reader_for_a_file_the_database_already_has(self):
        text = artifacts.render_folder_readme(artifacts.load_default_manifest())
        before = text.split("## Already inside the patch database")[0]

        assert "cc-usa.aps" not in before


class TestCapacity:
    def test_the_database_still_leaves_room_for_a_full_disk_of_games(self):
        from z64kit import packing
        from z64kit.fat import image

        manifest = artifacts.load_default_manifest()
        entry = next(e for e in manifest.entries() if e.filename == DATABASE)
        usable = image.usable_capacity()
        units = packing.units_for_capacity(usable)

        assert usable - units * packing.GRAIN >= entry.size

    def test_the_game_count_per_disk_is_unchanged_by_the_database(self):
        from z64kit import packing
        from z64kit.fat import image

        assert packing.units_for_capacity(image.usable_capacity()) == 23


class TestBuildPlacesTheDatabase:
    def test_the_database_is_written_to_the_disk(self, tmp_path):
        from z64kit import cli
        from z64kit.conftest import make_rom

        source = tmp_path / "roms"
        source.mkdir()
        (source / "game.z64").write_bytes(make_rom(size=4 * 1024 * 1024))
        supplied = tmp_path / "patches"
        supplied.mkdir()
        (supplied / DATABASE).write_bytes(b"PK\x03\x04" + bytes(1024))

        import argparse

        args = argparse.Namespace(
            source=str(source),
            output=str(tmp_path / "out"),
            force=False,
            patches=str(supplied),
            json=False,
        )
        assert cli.cmd_build(args) == 0

        raw = (tmp_path / "out" / "Disk_01.img").read_bytes()
        assert b"Z64PATCHDAT" in raw

    def test_a_missing_database_is_reported_and_not_fatal(self, tmp_path, capsys):
        from z64kit import cli
        from z64kit.conftest import make_rom

        source = tmp_path / "roms"
        source.mkdir()
        (source / "game.z64").write_bytes(make_rom(size=4 * 1024 * 1024))
        supplied = tmp_path / "patches"
        supplied.mkdir()

        import argparse

        args = argparse.Namespace(
            source=str(source),
            output=str(tmp_path / "out"),
            force=False,
            patches=str(supplied),
            json=False,
        )
        assert cli.cmd_build(args) == 0
        assert "z64patch.dat" in capsys.readouterr().out

    def test_the_folder_route_places_it_too(self, tmp_path):
        from z64kit import cli
        from z64kit.conftest import make_rom

        source = tmp_path / "roms"
        source.mkdir()
        (source / "game.z64").write_bytes(make_rom(size=4 * 1024 * 1024))
        supplied = tmp_path / "patches"
        supplied.mkdir()
        (supplied / DATABASE).write_bytes(b"PK\x03\x04" + bytes(1024))

        import argparse

        args = argparse.Namespace(
            source=str(source),
            output=str(tmp_path / "out"),
            force=False,
            patches=str(supplied),
            json=False,
        )
        assert cli.cmd_organise(args) == 0

        placed = list((tmp_path / "out").rglob(DATABASE))
        assert placed, "the database was not copied into the disk folder"
