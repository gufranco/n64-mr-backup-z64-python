"""Deciding, per game, what to emit so the ROM on disk is never written.

Editing a ROM to turn anti-aliasing off reseals its checksum, and the checksum
sits inside the 64 bytes the unit matches to find a game's patch. So the edit
delivers the video change and silently drops the patch the game needs to boot.

Emitting a patch instead keeps the binding, because a patch records the checksums
of the ROM it was built against and the ROM is left alone. Where a game already
has a patch the two fold into one, since the unit applies one patch per ROM.

The invariant every case here defends: an outcome that could displace a patch a
game needs carries no patch at all. Emitting nothing costs a video change.
Emitting the wrong thing costs the game.
"""

from __future__ import annotations

import pytest
from tests.test_merge import rom_with_table, save_patch_for

from z64kit import aps, videopatch

VIDEO = {"antialiasing": False, "divot": False, "gamma_dither": False, "dither_filter": False}


class TestAGameWithNoPatchOfItsOwn:
    def test_it_emits_a_video_patch(self):
        rom = rom_with_table()

        outcome = videopatch.build_for(rom, None, **VIDEO)

        assert outcome.kind == videopatch.VIDEO_ONLY
        assert outcome.patch is not None

    def test_the_patch_turns_the_video_settings_off(self):
        rom = rom_with_table()

        outcome = videopatch.build_for(rom, None, **VIDEO)
        result = aps.apply(rom, aps.parse(outcome.patch), verify=True)

        assert videopatch.vi.audit(result).antialiasing_on == 0

    def test_the_patch_binds_to_the_untouched_original(self):
        rom = rom_with_table()

        outcome = videopatch.build_for(rom, None, **VIDEO)
        parsed = aps.parse(outcome.patch)

        assert (parsed.crc1, parsed.crc2) == aps.target_checksums(rom)

    def test_a_rom_the_video_stage_refuses_emits_nothing(self):
        from tests.conftest import make_rom

        outcome = videopatch.build_for(make_rom(), None, **VIDEO)

        assert outcome.kind == videopatch.SKIPPED
        assert outcome.patch is None


class TestAGameThatAlreadyHasAPatch:
    def test_it_folds_both_changes_into_one_patch(self):
        rom = rom_with_table()
        existing = save_patch_for(rom)

        outcome = videopatch.build_for(rom, existing, **VIDEO)
        result = aps.apply(rom, aps.parse(outcome.patch), verify=True)

        assert outcome.kind == videopatch.MERGED
        assert result[0x400:0x404] == b"\xc0\xde\xc0\xde"
        assert videopatch.vi.audit(result).antialiasing_on == 0

    def test_the_merged_patch_still_binds_to_the_untouched_original(self):
        rom = rom_with_table()

        outcome = videopatch.build_for(rom, save_patch_for(rom), **VIDEO)
        parsed = aps.parse(outcome.patch)

        assert (parsed.crc1, parsed.crc2) == aps.target_checksums(rom)

    def test_a_patch_the_merge_refuses_emits_nothing(self):
        rom = rom_with_table()
        foreign = save_patch_for(rom_with_table(ctrl=0x00003000))

        outcome = videopatch.build_for(rom, foreign, **VIDEO)

        assert outcome.kind == videopatch.SKIPPED
        assert outcome.patch is None

    def test_a_patch_in_a_format_this_cannot_read_emits_nothing(self):
        rom = rom_with_table()

        outcome = videopatch.build_for(rom, b"PATCH" + b"an IPS body", **VIDEO)

        assert outcome.kind == videopatch.SKIPPED
        assert outcome.patch is None
        assert "APS" in outcome.reason

    def test_a_game_already_at_the_wanted_settings_keeps_its_patch(self):
        rom = rom_with_table(ctrl=0x00000000)
        existing = save_patch_for(rom)

        outcome = videopatch.build_for(rom, existing, **VIDEO)

        assert outcome.kind == videopatch.SKIPPED
        assert outcome.patch is None


class TestTheInvariant:
    @pytest.mark.parametrize(
        "rom_factory,existing",
        [
            (rom_with_table, None),
            (rom_with_table, b"PATCH not an aps"),
            (rom_with_table, b"APS10 truncated"),
        ],
    )
    def test_a_skipped_outcome_never_carries_a_patch(self, rom_factory, existing):
        outcome = videopatch.build_for(rom_factory(), existing, **VIDEO)

        assert outcome.patch is None or outcome.kind != videopatch.SKIPPED

    def test_every_outcome_states_a_reason(self):
        rom = rom_with_table()

        for existing in (None, save_patch_for(rom), b"PATCH nope"):
            assert videopatch.build_for(rom, existing, **VIDEO).reason
