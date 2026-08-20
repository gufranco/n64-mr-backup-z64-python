"""Proof that the writer reproduces images built before it existed, byte for byte.

Every test here needs a real ROM collection and a recorded digest list, so each
one skips when either is absent. That is what lets the rest of the suite run on a
machine that holds no game data at all.

Both locations are configurable. `Z64KIT_LIBRARY` points at the collection, one
folder per disk. `Z64KIT_GOLDEN` points at a file of `<sha256>  <folder name>`
lines. Neither is distributed: the digests describe one person's disks and prove
nothing about anybody else's.
"""

import hashlib
import os
from pathlib import Path

import pytest

from z64kit.fat import writer

pytestmark = pytest.mark.artifacts

LIBRARY = Path(os.environ.get("Z64KIT_LIBRARY", Path.home() / "Mr Backup z64"))
GOLDEN = Path(os.environ.get("Z64KIT_GOLDEN", Path(__file__).parent.parent / "golden-images.txt"))


def load_golden():
    if not GOLDEN.exists():
        pytest.skip("no golden digest list recorded")
    out = {}
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        digest, name = line.split()
        out[name] = digest
    return out


def disk_folder(number):
    folder = LIBRARY / f"Zip Disk {number:02d}"
    if not folder.is_dir():
        pytest.skip(f"{folder} not present")
    return folder


def build_disk(folder, label):
    """Reproduce the original layout: size descending, contiguous, from cluster two."""
    roms = sorted(
        (p for p in folder.iterdir() if p.suffix.lower() == ".z64"),
        key=lambda p: (-p.stat().st_size, p.name),
    )
    from z64kit import naming

    assigned, _, _ = naming.assign([(p.name, p.name) for p in roms])
    volume = writer.Volume(label=label)
    for path in roms:
        volume.add_file(writer.ROOT, assigned[path.name], "Z64", path.read_bytes())
    volume.sort_directories()
    return volume


class TestGoldenReproduction:
    @pytest.mark.parametrize("number", [2, 13, 48])
    def test_matches_the_recorded_digest(self, number):
        golden = load_golden()
        name = f"Zip_Disk_{number:02d}.img"
        if name not in golden:
            pytest.skip(f"{name} has no recorded digest")

        volume = build_disk(disk_folder(number), f"ZIP DISK {number:02d}")

        assert hashlib.sha256(volume.to_bytes()).hexdigest() == golden[name]

    def test_every_file_verifies_against_its_source(self):
        volume = build_disk(disk_folder(2), "ZIP DISK 02")

        assert volume.verify() == []

    def test_the_build_is_reproducible(self):
        first = build_disk(disk_folder(2), "ZIP DISK 02").to_bytes()
        second = build_disk(disk_folder(2), "ZIP DISK 02").to_bytes()

        assert hashlib.sha256(first).hexdigest() == hashlib.sha256(second).hexdigest()

    def test_free_space_collects_in_one_run_at_the_tail(self):
        volume = build_disk(disk_folder(2), "ZIP DISK 02")
        free = [c for c in range(2, volume._fat_limit()) if volume._fat_get(c) == 0]

        assert free == list(range(free[0], free[-1] + 1))


class TestPatchesActuallyReachTheDisk:
    """The guard for a silent failure: patches indexed as zero and nothing said.

    A patch folder holding only APS payloads produced an empty index, because the
    lookup demanded a `.hdr` sidecar that the APS format makes unnecessary. Every
    disk built that way was missing every patch and reported success.
    """

    PATCH_FOLDER = Path(__file__).parent.parent / "patches"

    def library(self):
        from z64kit import cli

        if not (self.PATCH_FOLDER / "zoot-usa.aps").exists():
            pytest.skip("the real payloads are not present on this machine")
        return cli._patch_library(str(self.PATCH_FOLDER))

    def test_a_folder_of_bare_aps_payloads_is_not_empty(self):
        assert len(self.library()) >= 12

    def test_a_game_on_a_real_disk_resolves_its_patch(self):
        from z64kit import cli, scan

        library = self.library()
        folder = disk_folder(1)
        found = scan.scan(str(folder))

        matched = [g for g in found.games if cli._patches_for(library, g)]

        assert matched, "no game on this disk resolved a patch"

    def test_the_resolved_patch_is_the_one_named_for_that_game(self):
        from z64kit import cli, scan

        library = self.library()
        found = scan.scan(str(disk_folder(1)))

        for game in found.games:
            for stem, _extension, _blob in cli._patches_for(library, game):
                assert stem in {
                    "cc-usa",
                    "dk64-usa",
                    "dx-btusc",
                    "ebikeusa",
                    "jfg-usa",
                    "kgsgood",
                    "mglf-usa",
                    "mten-usa",
                    "nbac2usa",
                    "swep1rus",
                    "zmm-usa",
                    "zoot-usa",
                }

    def test_a_companion_save_is_resolved_with_its_patch(self):
        library = self.library()

        with_companions = [
            entries for entries in library.values() if len({e[1] for e in entries}) > 1
        ]

        assert len(with_companions) == 3
