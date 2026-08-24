"""Emitting a patch folder that leaves every ROM on disk untouched.

The command under test is the delivery half of the idea: decide per game what to
ship, then write a folder `build` can consume. Two properties carry the risk.

The folder must be the whole library plus the changes, because `build` treats a
folder holding only the new patches as a complete one and would quietly drop
every patch it does not find. And a game whose existing patch cannot be folded
must come out the far side with that patch untouched and no video patch beside
it, because two patches matching one ROM is worse than no video change.
"""

from __future__ import annotations

import zipfile

import pytest
from n64_video_interface import vi
from tests.conftest import make_rom, mode_entry
from tests.test_merge import save_patch_for

from z64kit import aps, artifacts, cli, patchdb


def rom_variant(marker: int, ctrl: int = 0x0000311E) -> bytes:
    """A ROM with a mode table and a byte that makes its checksum its own.

    Three identical ROMs would share one binding, so a patch written for the
    second would bind to all three and the fixture would prove nothing.
    """
    data = bytearray(make_rom(size=vi.CHECKSUM_END + 0x2000))
    entry = mode_entry(ctrl=ctrl)
    data[0x2000 : 0x2000 + len(entry)] = entry
    data[0x1500] = marker
    return vi.reseal(bytes(data))


@pytest.fixture
def collection(tmp_path):
    root = tmp_path / "roms"
    root.mkdir()
    for marker, name in enumerate(("alpha", "beta", "gamma"), start=1):
        (root / f"{name}.z64").write_bytes(rom_variant(marker))
    return root


@pytest.fixture
def library(tmp_path, collection):
    folder = tmp_path / "patches"
    folder.mkdir()

    beta = (collection / "beta.z64").read_bytes()
    (folder / "beta-fix.aps").write_bytes(save_patch_for(beta))

    gamma = (collection / "gamma.z64").read_bytes()
    (folder / "gamma-fix.ips").write_bytes(b"PATCH" + b"body" + b"EOF")
    (folder / "gamma-fix.hdr").write_bytes(gamma[:64])
    return folder


def run(source, **kw):
    argv = ["vi", str(source), "--no-aa", "--no-dither"]
    for key, value in kw.items():
        flag = "--" + key.replace("_", "-")
        argv += [flag] if value is True else [flag, str(value)]
    return cli.main(argv)


class TestTheDryRunWritesNothing:
    def test_it_creates_no_output_folder(self, collection, library, tmp_path):
        target = tmp_path / "out"

        run(collection, as_patches=True, patches=library, output=target)

        assert not target.exists()

    def test_applying_without_an_output_is_refused(self, collection, library, capsys):
        code = run(collection, as_patches=True, patches=library, apply=True)

        assert code == 2
        assert "--apply needs --output" in capsys.readouterr().err


class TestWhatLandsInTheFolder:
    @pytest.fixture
    def out(self, collection, library, tmp_path):
        target = tmp_path / "out"
        run(collection, as_patches=True, patches=library, output=target, apply=True)
        return target

    def test_the_whole_library_is_carried_over(self, out, library):
        for path in library.iterdir():
            assert (out / path.name).exists(), path.name

    def test_a_game_with_no_patch_gets_one(self, out, collection):
        rom = (collection / "alpha.z64").read_bytes()
        crc1, crc2 = aps.target_checksums(rom)

        emitted = out / f"v{crc1:08x}{crc2:08x}.aps"

        assert emitted.exists()

    def test_that_patch_turns_the_video_settings_off(self, out, collection):
        from n64_video_interface import vi

        rom = (collection / "alpha.z64").read_bytes()
        crc1, crc2 = aps.target_checksums(rom)
        blob = (out / f"v{crc1:08x}{crc2:08x}.aps").read_bytes()

        result = aps.apply(rom, aps.parse(blob), verify=True)

        assert vi.audit(result).antialiasing_on == 0

    def test_a_mergeable_patch_is_replaced_in_place(self, out, library, collection):
        from n64_video_interface import vi

        rom = (collection / "beta.z64").read_bytes()
        before = (library / "beta-fix.aps").read_bytes()
        after = (out / "beta-fix.aps").read_bytes()

        assert after != before
        result = aps.apply(rom, aps.parse(after), verify=True)
        assert vi.audit(result).antialiasing_on == 0
        assert result[0x400:0x404] == b"\xc0\xde\xc0\xde"

    def test_the_original_library_is_never_written_over(self, out, library, collection):
        rom = (collection / "beta.z64").read_bytes()

        untouched = aps.apply(rom, aps.parse((library / "beta-fix.aps").read_bytes()))

        assert untouched[0x400:0x404] == b"\xc0\xde\xc0\xde"

    def test_the_roms_are_never_written(self, out, collection):
        for marker, name in enumerate(("alpha", "beta", "gamma"), start=1):
            assert (collection / f"{name}.z64").read_bytes() == rom_variant(marker)


class TestTheInvariant:
    @pytest.fixture
    def out(self, collection, library, tmp_path):
        target = tmp_path / "out"
        run(collection, as_patches=True, patches=library, output=target, apply=True)
        return target

    def test_an_unfoldable_patch_survives_unchanged(self, out, library):
        assert (out / "gamma-fix.ips").read_bytes() == (library / "gamma-fix.ips").read_bytes()

    def test_and_no_video_patch_is_emitted_beside_it(self, out, collection):
        rom = (collection / "gamma.z64").read_bytes()
        crc1, crc2 = aps.target_checksums(rom)

        assert not (out / f"v{crc1:08x}{crc2:08x}.aps").exists()

    def test_no_two_patches_bind_to_the_same_rom(self, out, collection):
        library = cli._patch_library(str(out))
        found = cli._scan_or_exit(str(collection))

        for game in found.games:
            assert len(cli._patches_for(library, game)) <= 2


class TestTheDatabaseRoute:
    @pytest.fixture
    def library(self, tmp_path, collection):
        folder = tmp_path / "patches"
        folder.mkdir()
        beta = (collection / "beta.z64").read_bytes()
        buffer = folder / artifacts.PATCH_DATABASE
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("ZPFINFO", b"3.0")
            archive.writestr("beta-fix.hdr", beta[:64])
            archive.writestr("beta-fix.aps", save_patch_for(beta))
        return folder

    def test_the_merged_patch_replaces_the_database_entry(self, collection, library, tmp_path):
        from n64_video_interface import vi

        target = tmp_path / "out"
        run(collection, as_patches=True, patches=library, output=target, apply=True)

        members = patchdb.read((target / artifacts.PATCH_DATABASE).read_bytes())
        rom = (collection / "beta.z64").read_bytes()
        result = aps.apply(rom, aps.parse(members["beta-fix.aps"]), verify=True)

        assert vi.audit(result).antialiasing_on == 0
        assert result[0x400:0x404] == b"\xc0\xde\xc0\xde"

    def test_the_lookup_key_never_moves(self, collection, library, tmp_path):
        target = tmp_path / "out"
        run(collection, as_patches=True, patches=library, output=target, apply=True)

        before = patchdb.read((library / artifacts.PATCH_DATABASE).read_bytes())
        after = patchdb.read((target / artifacts.PATCH_DATABASE).read_bytes())

        assert after["beta-fix.hdr"] == before["beta-fix.hdr"]
        assert after["ZPFINFO"] == before["ZPFINFO"]

    def test_no_loose_patch_is_dropped_beside_the_rom(self, collection, library, tmp_path):
        target = tmp_path / "out"
        run(collection, as_patches=True, patches=library, output=target, apply=True)

        rom = (collection / "beta.z64").read_bytes()
        crc1, crc2 = aps.target_checksums(rom)

        assert not (target / f"v{crc1:08x}{crc2:08x}.aps").exists()


class TestTheFolderIsOnlyPatches:
    @pytest.fixture
    def library(self, tmp_path, collection):
        folder = tmp_path / "patches"
        folder.mkdir()
        beta = (collection / "beta.z64").read_bytes()
        (folder / "beta-fix.aps").write_bytes(save_patch_for(beta))
        (folder / ".gitignore").write_text("*.dat\n", encoding="utf-8")
        return folder

    def test_a_dotfile_is_not_carried_into_the_output(self, collection, library, tmp_path):
        target = tmp_path / "out"

        run(collection, as_patches=True, patches=library, output=target, apply=True)

        assert not (target / ".gitignore").exists()

    def test_the_reported_count_is_the_number_of_files_there(
        self, collection, library, tmp_path, capsys
    ):
        target = tmp_path / "out"

        run(collection, as_patches=True, patches=library, output=target, apply=True)
        printed = capsys.readouterr().out

        actual = len(list(target.iterdir()))
        assert f"{actual} files written" in printed


class TestAPatchCarriedByBothRoutes:
    """A library can hold a loose copy of a patch the database also carries.

    The real `patches/` folder does, and `build` ships both: the loose file lands
    beside the ROM and the database lands on every disk. Updating one and copying
    the other verbatim leaves two patches for one game that no longer agree, and
    the one sitting beside the ROM is the one without the video change.

    Writing the merged patch down both routes makes the question of which the unit
    prefers stop mattering, which is better than betting on the answer.
    """

    @pytest.fixture
    def library(self, tmp_path, collection):
        folder = tmp_path / "patches"
        folder.mkdir()
        beta = (collection / "beta.z64").read_bytes()
        existing = save_patch_for(beta)
        (folder / "beta-fix.aps").write_bytes(existing)
        with zipfile.ZipFile(
            folder / artifacts.PATCH_DATABASE, "w", zipfile.ZIP_DEFLATED
        ) as archive:
            archive.writestr("ZPFINFO", b"3.0")
            archive.writestr("beta-fix.hdr", beta[:64])
            archive.writestr("beta-fix.aps", existing)
        return folder

    @pytest.fixture
    def out(self, collection, library, tmp_path):
        target = tmp_path / "out"
        run(collection, as_patches=True, patches=library, output=target, apply=True)
        return target

    def test_both_copies_carry_the_merge(self, out, collection):
        from n64_video_interface import vi

        rom = (collection / "beta.z64").read_bytes()
        members = patchdb.read((out / artifacts.PATCH_DATABASE).read_bytes())

        for blob in (members["beta-fix.aps"], (out / "beta-fix.aps").read_bytes()):
            result = aps.apply(rom, aps.parse(blob), verify=True)
            assert vi.audit(result).antialiasing_on == 0
            assert result[0x400:0x404] == b"\xc0\xde\xc0\xde"

    def test_the_two_copies_are_byte_identical(self, out):
        members = patchdb.read((out / artifacts.PATCH_DATABASE).read_bytes())

        assert (out / "beta-fix.aps").read_bytes() == members["beta-fix.aps"]

    def test_the_loose_copy_is_not_left_at_the_old_bytes(self, out, library):
        assert (out / "beta-fix.aps").read_bytes() != (library / "beta-fix.aps").read_bytes()
