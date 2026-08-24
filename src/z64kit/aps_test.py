"""Tests for the APS patch format, pinned against the layout observed in real files."""

import struct

import pytest

from z64kit import aps


def build_header(crc1=0x11223344, crc2=0x55667788, cart=b"KJ", country=b"E", size=0x100000):
    out = bytearray(b"APS10")
    out += bytes([aps.TYPE_N64, 0])
    out += b" " * aps.DESCRIPTION_LENGTH
    out += bytes([0])
    out += cart + country
    out += struct.pack(">II", crc1, crc2)
    out += bytes(5)
    out += struct.pack("<I", size)
    assert len(out) == aps.RECORDS_OFFSET, len(out)
    return out


def record(offset, payload):
    return struct.pack("<I", offset) + bytes([len(payload)]) + bytes(payload)


class TestParse:
    def test_reads_the_stored_target_checksums(self):
        patch = aps.parse(bytes(build_header(crc1=0x36281F23, crc2=0x009756CF)))

        assert patch.crc1 == 0x36281F23
        assert patch.crc2 == 0x009756CF

    def test_reads_the_cart_id_and_country(self):
        patch = aps.parse(bytes(build_header(cart=b"ZL", country=b"E")))

        assert patch.cart_id == b"ZL"
        assert patch.country == b"E"

    def test_reads_a_literal_record(self):
        patch = aps.parse(bytes(build_header()) + record(0x40, b"\xaa\xbb"))

        assert patch.records == ((0x40, b"\xaa\xbb"),)

    def test_expands_a_run_length_record(self):
        raw = bytes(build_header()) + struct.pack("<I", 0x80) + bytes([0, 4, 0xFF])

        assert aps.parse(raw).records == ((0x80, b"\xff" * 4),)

    def test_reads_many_records_in_order(self):
        raw = bytes(build_header()) + record(0x10, b"\x01") + record(0x20, b"\x02")

        assert [offset for offset, _ in aps.parse(raw).records] == [0x10, 0x20]

    def test_rejects_a_foreign_magic(self):
        with pytest.raises(aps.FormatError, match="magic"):
            aps.parse(b"PATCH" + bytes(aps.RECORDS_OFFSET))

    def test_rejects_a_non_n64_patch_type(self):
        raw = bytearray(build_header())
        raw[5] = 0

        with pytest.raises(aps.FormatError, match="N64"):
            aps.parse(bytes(raw))

    def test_rejects_a_truncated_record_header(self):
        with pytest.raises(aps.FormatError, match="truncated"):
            aps.parse(bytes(build_header()) + b"\x01\x02")

    def test_rejects_a_record_whose_payload_runs_past_the_end(self):
        raw = bytes(build_header()) + struct.pack("<I", 0) + bytes([8]) + b"\x01\x02"

        with pytest.raises(aps.FormatError, match="truncated"):
            aps.parse(raw)

    def test_rejects_a_truncated_run_length_record(self):
        raw = bytes(build_header()) + struct.pack("<I", 0) + bytes([0, 4])

        with pytest.raises(aps.FormatError, match="truncated"):
            aps.parse(raw)


class TestApply:
    def test_writes_each_record_at_its_offset(self):
        patch = aps.parse(bytes(build_header()) + record(2, b"\xaa\xbb"))

        assert aps.apply(bytes(8), patch) == b"\x00\x00\xaa\xbb\x00\x00\x00\x00"

    def test_grows_the_rom_when_a_record_reaches_past_the_end(self):
        patch = aps.parse(bytes(build_header()) + record(6, b"\x99\x99"))

        assert aps.apply(bytes(4), patch) == b"\x00" * 6 + b"\x99\x99"

    def test_later_records_win_over_earlier_ones(self):
        raw = bytes(build_header()) + record(0, b"\x01") + record(0, b"\x02")

        assert aps.apply(bytes(1), aps.parse(raw)) == b"\x02"

    def test_verifies_the_target_checksums_when_asked(self):
        patch = aps.parse(bytes(build_header(crc1=0xDEADBEEF)))

        with pytest.raises(aps.TargetMismatchError, match="CRC1"):
            aps.apply(bytes(0x40), patch, verify=True)

    def test_accepts_a_rom_whose_checksums_match(self):
        rom = bytearray(0x40)
        rom[0x10:0x18] = struct.pack(">II", 0x36281F23, 0x009756CF)
        patch = aps.parse(bytes(build_header(crc1=0x36281F23, crc2=0x009756CF)))

        assert aps.apply(bytes(rom), patch, verify=True) is not None


class TestBuild:
    def test_round_trips_through_parse(self):
        original = bytes(0x100)
        patched = bytearray(original)
        patched[0x40:0x44] = b"\xde\xad\xbe\xef"

        raw = aps.build(original, bytes(patched))

        assert aps.apply(original, aps.parse(raw)) == bytes(patched)

    def test_carries_the_original_checksums_not_the_patched_ones(self):
        original = bytearray(0x100)
        original[0x10:0x18] = struct.pack(">II", 0xAAAAAAAA, 0xBBBBBBBB)
        patched = bytearray(original)
        patched[0x10:0x18] = struct.pack(">II", 0xCCCCCCCC, 0xDDDDDDDD)

        patch = aps.parse(aps.build(bytes(original), bytes(patched)))

        assert (patch.crc1, patch.crc2) == (0xAAAAAAAA, 0xBBBBBBBB)

    def test_emits_no_records_when_nothing_changed(self):
        original = bytes(0x100)

        assert aps.parse(aps.build(original, original)).records == ()

    def test_splits_a_long_change_across_records(self):
        original = bytes(0x400)
        patched = b"\xff" * 0x400

        patch = aps.parse(aps.build(original, patched))

        assert all(len(payload) <= aps.MAX_RECORD for _, payload in patch.records)

    def test_reproduces_a_long_change_exactly(self):
        original = bytes(0x400)
        patched = bytes(range(256)) * 4

        raw = aps.build(original, patched)

        assert aps.apply(original, aps.parse(raw)) == patched

    def test_carries_the_description_through(self):
        raw = aps.build(bytes(0x40), bytes(0x40), description="merged")

        assert aps.parse(raw).description == "merged"

    def test_refuses_a_description_that_does_not_fit(self):
        with pytest.raises(ValueError, match="description"):
            aps.build(bytes(0x40), bytes(0x40), description="x" * 80)

    def test_records_the_patched_size(self):
        raw = aps.build(bytes(0x40), bytes(0x800))

        assert aps.parse(raw).size == 0x800


class TestRunLengthEncoding:
    def test_encodes_a_long_uniform_change_as_a_run(self):
        raw = aps.build(bytes(0x300), b"\xff" * 0x300)

        assert len(raw) < aps.RECORDS_OFFSET + 0x100

    def test_a_run_still_reproduces_the_bytes(self):
        original, patched = bytes(0x300), b"\xff" * 0x300

        assert aps.apply(original, aps.parse(aps.build(original, patched))) == patched

    def test_leaves_a_short_uniform_change_as_a_literal(self):
        patch = aps.parse(aps.build(bytes(0x40), b"\xff" * 4 + bytes(0x3C)))

        assert patch.records == ((0, b"\xff" * 4),)

    def test_mixes_runs_and_literals_in_one_patch(self):
        original = bytes(0x400)
        patched = b"\xaa" * 0x200 + bytes(0x100) + b"\x01\x02\x03" + bytes(0xFD)

        assert aps.apply(original, aps.parse(aps.build(original, patched))) == patched


class TestShortRom:
    def test_refuses_a_rom_too_short_to_hold_a_header(self):
        with pytest.raises(ValueError, match="header"):
            aps.build(bytes(0x10), bytes(0x10))

    def test_refuses_to_read_checksums_from_a_short_rom(self):
        with pytest.raises(ValueError, match="header"):
            aps.target_checksums(bytes(4))


class TestApplyingAPatchToTheWrongRom:
    """The binding is checked before a byte is written, when asked to check it.

    A patch carries the checksums of the ROM it was built against. Applying it
    to a different dump produces a file that boots into whatever the records
    happened to overwrite, so the refusal names which half of the pair differs
    rather than saying the patch is bad.
    """

    def _rom(self, crc1: int, crc2: int) -> bytes:
        from z64kit.conftest import make_rom

        return make_rom(crc1=crc1, crc2=crc2)

    def test_a_first_checksum_that_does_not_match_is_refused(self):
        built = aps.build(self._rom(0x11111111, 0x22222222), self._rom(0x11111111, 0x22222222))
        parsed = aps.parse(built)

        with pytest.raises(aps.TargetMismatchError, match="CRC1 mismatch"):
            aps.apply(self._rom(0x99999999, 0x22222222), parsed, verify=True)

    def test_a_second_checksum_that_does_not_match_is_refused(self):
        built = aps.build(self._rom(0x11111111, 0x22222222), self._rom(0x11111111, 0x22222222))
        parsed = aps.parse(built)

        with pytest.raises(aps.TargetMismatchError, match="CRC2 mismatch"):
            aps.apply(self._rom(0x11111111, 0x99999999), parsed, verify=True)
