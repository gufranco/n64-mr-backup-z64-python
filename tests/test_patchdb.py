"""The unit's patch database is a ZIP container, and rebuilding it must be surgical.

A patch that lives inside `z64patch.dat` cannot be replaced by dropping a file
beside the ROM, because which of the two the unit prefers has never been settled
on hardware. Rewriting the entry in place sidesteps the question: there is still
exactly one patch for that game.

That only holds if the rebuild changes nothing else. The `.hdr` beside each patch
is the ROM's untouched 64-byte header and is the key the unit matches on, so
moving one byte of it loses the game. Every guard here exists to make a rebuild
that quietly drops, reorders, or re-keys a member impossible rather than unlikely.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from z64kit import patchdb


def make_database(members: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, blob in members:
            archive.writestr(name, blob)
    return buffer.getvalue()


@pytest.fixture
def database() -> bytes:
    return make_database(
        [
            ("ZPFINFO", b"3.0"),
            ("dk64-usa.hdr", bytes(range(64))),
            ("dk64-usa.aps", b"APS10" + b"original dk64 payload"),
            ("zoot-usa.hdr", bytes(range(64, 128))),
            ("zoot-usa.aps", b"APS10" + b"original zoot payload"),
        ]
    )


class TestReading:
    def test_it_returns_every_member(self, database):
        members = patchdb.read(database)

        assert set(members) == {
            "ZPFINFO",
            "dk64-usa.hdr",
            "dk64-usa.aps",
            "zoot-usa.hdr",
            "zoot-usa.aps",
        }

    def test_it_returns_the_bytes_unchanged(self, database):
        members = patchdb.read(database)

        assert members["dk64-usa.aps"] == b"APS10" + b"original dk64 payload"
        assert members["dk64-usa.hdr"] == bytes(range(64))

    def test_it_refuses_something_that_is_not_a_database(self):
        with pytest.raises(patchdb.NotADatabaseError):
            patchdb.read(b"this is not a zip archive")


class TestRebuilding:
    def test_it_replaces_only_the_named_member(self, database):
        rebuilt = patchdb.rebuild(database, {"dk64-usa.aps": b"APS10" + b"merged payload"})
        members = patchdb.read(rebuilt)

        assert members["dk64-usa.aps"] == b"APS10" + b"merged payload"
        assert members["zoot-usa.aps"] == b"APS10" + b"original zoot payload"

    def test_it_leaves_every_lookup_key_byte_identical(self, database):
        rebuilt = patchdb.rebuild(database, {"dk64-usa.aps": b"APS10" + b"merged payload"})
        before, after = patchdb.read(database), patchdb.read(rebuilt)

        assert after["dk64-usa.hdr"] == before["dk64-usa.hdr"]
        assert after["zoot-usa.hdr"] == before["zoot-usa.hdr"]

    def test_it_keeps_the_member_order(self, database):
        rebuilt = patchdb.rebuild(database, {"dk64-usa.aps": b"APS10" + b"merged payload"})

        assert list(patchdb.read(rebuilt)) == list(patchdb.read(database))

    def test_it_keeps_the_version_marker(self, database):
        rebuilt = patchdb.rebuild(database, {"dk64-usa.aps": b"APS10" + b"merged payload"})

        assert patchdb.read(rebuilt)["ZPFINFO"] == b"3.0"

    def test_replacing_nothing_returns_the_same_members(self, database):
        rebuilt = patchdb.rebuild(database, {})

        assert patchdb.read(rebuilt) == patchdb.read(database)

    def test_it_refuses_a_member_the_database_does_not_carry(self, database):
        with pytest.raises(patchdb.UnknownMemberError):
            patchdb.rebuild(database, {"mario-usa.aps": b"APS10"})

    def test_it_refuses_to_move_a_lookup_key(self, database):
        with pytest.raises(patchdb.LookupKeyError):
            patchdb.rebuild(database, {"dk64-usa.hdr": bytes(64)})

    def test_it_refuses_a_payload_that_is_not_a_patch(self, database):
        with pytest.raises(patchdb.NotAPatchError):
            patchdb.rebuild(database, {"dk64-usa.aps": b"IPS" + b"wrong format"})


class TestPatchNames:
    def test_it_pairs_a_patch_with_its_header(self, database):
        assert patchdb.patch_members(patchdb.read(database)) == {
            "dk64-usa.aps": "dk64-usa.hdr",
            "zoot-usa.aps": "zoot-usa.hdr",
        }

    def test_a_patch_with_no_header_is_not_paired(self):
        members = patchdb.read(make_database([("lonely.aps", b"APS10")]))

        assert patchdb.patch_members(members) == {}


class TestAgainstTheRealDatabase:
    """The synthetic fixtures above prove the guards. This proves the format.

    `z64patch.dat` is a user-supplied artifact and is not in the repository, so
    this skips where it is absent rather than failing. A container this code
    reads correctly in a fixture it wrote itself proves less than one it did not.
    """

    def database(self) -> bytes:
        path = Path(__file__).resolve().parent.parent / "patches" / "z64patch.dat"
        if not path.is_file():
            pytest.skip("the unit's patch database is not present on this machine")
        return path.read_bytes()

    def test_it_reads_the_container(self):
        members = patchdb.read(self.database())

        assert "ZPFINFO" in members
        assert any(name.lower().endswith(".aps") for name in members)

    def test_every_paired_header_is_exactly_64_bytes(self):
        members = patchdb.read(self.database())

        for patch, sidecar in patchdb.patch_members(members).items():
            assert len(members[sidecar]) == 64, patch

    def test_a_rebuild_that_replaces_nothing_changes_nothing(self):
        blob = self.database()

        rebuilt = patchdb.rebuild(blob, {})

        assert patchdb.read(rebuilt) == patchdb.read(blob)

    def test_a_rebuild_leaves_every_header_byte_identical(self):
        blob = self.database()
        members = patchdb.read(blob)
        victim = next(iter(patchdb.patch_members(members)))

        rebuilt = patchdb.read(patchdb.rebuild(blob, {victim: b"APS10" + b"stand in"}))

        assert rebuilt[victim] == b"APS10" + b"stand in"
        for name, blob_before in members.items():
            if name != victim:
                assert rebuilt[name] == blob_before, name
