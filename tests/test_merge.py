"""Tests for folding a video change into a patch the game already needs."""

import struct

import pytest
from n64_video_interface import checksum, vi
from tests.conftest import make_rom, mode_entry

from z64kit import aps, merge


def rom_with_table(ctrl=0x0000311E):
    data = bytearray(make_rom(size=vi.CHECKSUM_END + 0x2000))
    entry = mode_entry(ctrl=ctrl)
    data[0x2000 : 0x2000 + len(entry)] = entry
    return vi.reseal(bytes(data))


def save_patch_for(rom, at=0x400, payload=b"\xc0\xde\xc0\xde"):
    """A stand-in for a vendor save fix: it edits code and reseals the header."""
    patched = bytearray(rom)
    patched[at : at + len(payload)] = payload
    resealed = vi.reseal(bytes(patched))
    return aps.build(rom, resealed, description="save fix")


class TestMerge:
    def test_the_merged_patch_binds_to_the_untouched_original(self):
        rom = rom_with_table()

        result = merge.merge(rom, save_patch_for(rom), antialiasing=False)

        assert aps.parse(result.patch).crc1 == aps.target_checksums(rom)[0]

    def test_the_merged_patch_carries_both_changes(self):
        rom = rom_with_table()

        result = merge.merge(rom, save_patch_for(rom), antialiasing=False)
        final = aps.apply(rom, aps.parse(result.patch), verify=True)

        assert final[0x400:0x404] == b"\xc0\xde\xc0\xde"
        assert struct.unpack(">I", final[0x2004:0x2008])[0] != 0x0000311E

    def test_the_merged_result_carries_one_valid_checksum(self):
        rom = rom_with_table()

        result = merge.merge(rom, save_patch_for(rom), antialiasing=False)
        final = aps.apply(rom, aps.parse(result.patch))

        assert checksum.compute(final, "6102") == aps.target_checksums(final)

    def test_the_original_rom_is_never_modified(self):
        rom = rom_with_table()
        before = bytes(rom)

        merge.merge(rom, save_patch_for(rom), antialiasing=False)

        assert rom == before

    def test_reports_which_video_words_changed(self):
        rom = rom_with_table()

        result = merge.merge(rom, save_patch_for(rom), antialiasing=False)

        assert result.video_changes and all(len(c) == 3 for c in result.video_changes)

    def test_refuses_a_patch_built_for_a_different_rom(self):
        rom = rom_with_table()
        other = bytearray(rom)
        other[0x10:0x14] = b"\xde\xad\xbe\xef"

        with pytest.raises(aps.TargetMismatchError):
            merge.merge(bytes(other), save_patch_for(rom), antialiasing=False)

    def test_refuses_when_the_existing_patch_leaves_an_invalid_checksum(self):
        rom = rom_with_table()
        broken = bytearray(rom)
        broken[0x3000:0x3004] = b"\x01\x02\x03\x04"
        patch = aps.build(rom, bytes(broken), description="does not reseal")

        with pytest.raises(merge.UnsafeMergeError, match="checksum"):
            merge.merge(rom, patch, antialiasing=False)

    def test_reports_no_change_when_the_video_settings_already_match(self):
        rom = rom_with_table()

        result = merge.merge(rom, save_patch_for(rom), antialiasing=True)

        assert result.video_changes == ()

    def test_keeps_the_existing_patch_when_video_needs_nothing(self):
        rom = rom_with_table()
        existing = save_patch_for(rom)

        result = merge.merge(rom, existing, antialiasing=True)

        assert result.patch == existing

    def test_names_the_cic_used_to_reseal(self):
        rom = rom_with_table()

        result = merge.merge(rom, save_patch_for(rom), antialiasing=False)

        assert result.cic == "6102"

    def test_the_description_records_that_it_is_a_merge(self):
        rom = rom_with_table()

        result = merge.merge(rom, save_patch_for(rom), antialiasing=False)

        assert "merge" in aps.parse(result.patch).description.lower()


class TestRefusal:
    def test_refuses_when_no_video_mode_table_can_be_proven(self):
        rom = vi.reseal(bytes(make_rom(size=vi.CHECKSUM_END + 0x2000)))

        with pytest.raises(merge.UnsafeMergeError, match="mode table"):
            merge.merge(rom, save_patch_for(rom), antialiasing=False)

    def test_never_emits_a_patch_built_from_a_refusal(self):
        rom = vi.reseal(bytes(make_rom(size=vi.CHECKSUM_END + 0x2000)))

        with pytest.raises(merge.UnsafeMergeError):
            merge.merge(rom, save_patch_for(rom), antialiasing=False)


class TestRefusalIsNeverSilent:
    def test_refuses_when_the_checksum_cannot_identify_a_boot_chip(self):
        rom = bytearray(rom_with_table())
        rom[0x10:0x18] = b"\x00" * 8
        original = bytes(rom)
        patched = bytearray(original)
        patched[0x3000:0x3004] = b"\x11\x22\x33\x44"

        with pytest.raises(merge.UnsafeMergeError, match="checksum"):
            merge.merge(original, aps.build(original, bytes(patched)), antialiasing=False)

    def test_a_refusal_from_the_video_stage_is_raised_not_swallowed(self, monkeypatch):
        rom = rom_with_table()
        existing = save_patch_for(rom)
        monkeypatch.setattr(
            vi, "safe_patch", lambda *_, **__: vi.PatchResult(False, "the edit did not take")
        )

        with pytest.raises(merge.UnsafeMergeError, match="did not take"):
            merge.merge(rom, existing, antialiasing=False)
