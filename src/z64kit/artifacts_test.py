import hashlib
import json
import zlib

import pytest

from z64kit import artifacts


def entry_dict(**over):
    base = {
        "name": "dk64-usa",
        "kind": "patch",
        "filename": "dk64-usa.aps",
        "size": 8,
        "sha256": hashlib.sha256(b"payload!").hexdigest(),
        "crc32": f"{zlib.crc32(b'payload!'):08x}",
        "target_crc1": "EC58EABF",
        "target_crc2": "AD7C7169",
        "game": "Donkey Kong 64 (USA)",
        "description": "Boot and save fix",
        "provenance": "Unofficial Z64 Patch File v3.0U",
        "companions": ["dk64-usa.ram"],
    }
    base.update(over)
    return base


@pytest.fixture
def manifest(tmp_path):
    path = tmp_path / "artifacts.manifest.json"
    payload = {
        "schema": 1,
        "note": "Identification only. No payload bytes are stored here.",
        "entries": [entry_dict()],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return artifacts.load_manifest(path)


class TestLoadManifest:
    def test_indexes_entries_by_sha256(self, manifest):
        digest = hashlib.sha256(b"payload!").hexdigest()

        assert digest in manifest.by_sha256

    def test_exposes_entry_fields(self, manifest):
        entry = manifest.by_sha256[hashlib.sha256(b"payload!").hexdigest()]

        assert entry.name == "dk64-usa"
        assert entry.kind == "patch"
        assert entry.companions == ("dk64-usa.ram",)

    def test_rejects_an_entry_carrying_payload_bytes(self, tmp_path):
        path = tmp_path / "bad.json"
        bad = entry_dict()
        bad["payload"] = "deadbeef"
        path.write_text(json.dumps({"schema": 1, "entries": [bad]}), encoding="utf-8")

        with pytest.raises(artifacts.ManifestError, match="payload"):
            artifacts.load_manifest(path)

    def test_rejects_an_unknown_schema_version(self, tmp_path):
        path = tmp_path / "future.json"
        path.write_text(json.dumps({"schema": 99, "entries": []}), encoding="utf-8")

        with pytest.raises(artifacts.ManifestError, match="schema"):
            artifacts.load_manifest(path)

    def test_exposes_every_entry_as_a_tuple(self, manifest):
        assert len(manifest.entries()) == 1

    def test_rejects_an_entry_missing_a_required_field(self, tmp_path):
        path = tmp_path / "incomplete.json"
        short = entry_dict()
        del short["sha256"]
        path.write_text(json.dumps({"schema": 1, "entries": [short]}), encoding="utf-8")

        with pytest.raises(artifacts.ManifestError, match="sha256"):
            artifacts.load_manifest(path)


class TestIdentify:
    def test_recognises_a_known_artifact(self, manifest):
        found = artifacts.identify(b"payload!", manifest)

        assert found is not None
        assert found.name == "dk64-usa"

    def test_returns_none_for_unknown_content(self, manifest):
        assert artifacts.identify(b"something else", manifest) is None


class TestVerify:
    def test_accepts_matching_content(self, manifest):
        entry = manifest.by_sha256[hashlib.sha256(b"payload!").hexdigest()]

        result = artifacts.verify(b"payload!", entry)

        assert result.ok is True
        assert result.reason == ""

    def test_rejects_on_size_before_hashing(self, manifest):
        entry = manifest.by_sha256[hashlib.sha256(b"payload!").hexdigest()]

        result = artifacts.verify(b"short", entry)

        assert result.ok is False
        assert "size" in result.reason

    def test_rejects_on_digest_when_size_matches(self, manifest):
        entry = manifest.by_sha256[hashlib.sha256(b"payload!").hexdigest()]

        result = artifacts.verify(b"payloadX", entry)

        assert result.ok is False
        assert "sha256" in result.reason


class TestDiagnose:
    def test_names_a_size_near_miss(self, manifest):
        message = artifacts.diagnose(b"payloadXY", manifest)

        assert "not recognised" in message
        assert "9 bytes" in message

    def test_reports_the_computed_digest_so_it_can_be_searched(self, manifest):
        message = artifacts.diagnose(b"zzz", manifest)

        assert hashlib.sha256(b"zzz").hexdigest() in message

    def test_confirms_a_known_artifact_instead_of_complaining(self, manifest):
        message = artifacts.diagnose(b"payload!", manifest)

        assert "dk64-usa" in message
        assert "not recognised" not in message

    def test_points_at_a_same_size_entry_when_one_exists(self, manifest):
        message = artifacts.diagnose(b"payloadX", manifest)

        assert "size matches dk64-usa" in message
        assert "modified or truncated" in message


class TestWriteManifest:
    def test_a_written_manifest_loads_back_unchanged(self, tmp_path):
        entry = artifacts.build_entry(
            name="x",
            kind="patch",
            filename="x.aps",
            data=b"payload!",
            provenance="test",
            game="Game (USA)",
            description="Save fix",
            companions=("x.ram",),
        )
        path = tmp_path / "out.json"

        artifacts.write_manifest([entry], path, note="identification only")
        loaded = artifacts.load_manifest(path)

        assert loaded.by_sha256[entry.sha256] == entry

    def test_optional_fields_are_omitted_when_absent(self, tmp_path):
        entry = artifacts.build_entry(
            name="bare",
            kind="save",
            filename="bare.ram",
            data=b"x",
            provenance="test",
        )
        path = tmp_path / "bare.json"

        artifacts.write_manifest([entry], path, note="n")
        raw = json.loads(path.read_text(encoding="utf-8"))

        assert "game" not in raw["entries"][0]
        assert "companions" not in raw["entries"][0]
        assert "target_crc1" not in raw["entries"][0]


class TestBuildEntry:
    def test_computes_every_digest_from_the_bytes(self):
        entry = artifacts.build_entry(
            name="x",
            kind="patch",
            filename="x.aps",
            data=b"payload!",
            provenance="test",
        )

        assert entry.size == 8
        assert entry.sha256 == hashlib.sha256(b"payload!").hexdigest()
        assert entry.crc32 == f"{zlib.crc32(b'payload!'):08x}"

    def test_extracts_target_checksums_from_an_aps_payload(self):
        blob = bytearray(b"APS10" + bytes(0x60))
        blob[0x3D:0x41] = bytes.fromhex("EC58EABF")
        blob[0x41:0x45] = bytes.fromhex("AD7C7169")

        entry = artifacts.build_entry(
            name="dk",
            kind="patch",
            filename="dk.aps",
            data=bytes(blob),
            provenance="test",
        )

        assert entry.target_crc1 == "EC58EABF"
        assert entry.target_crc2 == "AD7C7169"

    def test_leaves_target_checksums_empty_for_a_non_aps_payload(self):
        entry = artifacts.build_entry(
            name="k",
            kind="patch",
            filename="k.ips",
            data=b"PATCHEOF",
            provenance="test",
        )

        assert entry.target_crc1 is None

    def test_serialises_without_any_payload_field(self):
        entry = artifacts.build_entry(
            name="x",
            kind="patch",
            filename="x.aps",
            data=b"payload!",
            provenance="test",
        )

        as_dict = artifacts.entry_to_dict(entry)

        assert "payload" not in as_dict
        assert as_dict["sha256"] == entry.sha256


class TestShippedManifest:
    def test_the_packaged_manifest_loads(self):
        manifest = artifacts.load_default_manifest()

        assert len(manifest.by_sha256) > 0

    def test_the_packaged_manifest_stores_no_payloads(self):
        raw = json.loads(artifacts.DEFAULT_MANIFEST_PATH.read_text(encoding="utf-8"))

        for item in raw["entries"]:
            assert "payload" not in item
            assert "data" not in item


class TestRegionAndGameCode:
    def entry(self, **kw):
        base = {
            "name": "x",
            "kind": "patch",
            "filename": "x.aps",
            "size": 1,
            "sha256": "a" * 64,
            "crc32": "0" * 8,
            "provenance": "test",
        }
        base.update(kw)
        return base

    def test_a_region_survives_a_round_trip(self):
        entry = artifacts._entry_from_dict(self.entry(region="EUR"))

        assert artifacts.entry_to_dict(entry)["region"] == "EUR"

    def test_a_game_code_survives_a_round_trip(self):
        entry = artifacts._entry_from_dict(self.entry(game_code="NZLP"))

        assert artifacts.entry_to_dict(entry)["game_code"] == "NZLP"

    def test_both_default_to_empty_when_absent(self):
        entry = artifacts._entry_from_dict(self.entry())

        assert entry.region is None
        assert entry.game_code is None

    def test_an_absent_region_is_not_written_back(self):
        entry = artifacts._entry_from_dict(self.entry())

        assert "region" not in artifacts.entry_to_dict(entry)


class TestTheRealManifestIsBroad:
    def test_the_scope_is_usa_and_is_stated_rather_than_implied(self):
        manifest = artifacts.load_default_manifest()

        regions = {e.region for e in manifest.entries() if e.region}

        assert regions == {"USA"}

    def test_it_covers_far_more_than_a_dozen_games(self):
        manifest = artifacts.load_default_manifest()

        games = {e.game_code for e in manifest.entries() if e.game_code}

        assert len(games) >= 50

    def test_every_patch_entry_names_the_game_it_targets(self):
        manifest = artifacts.load_default_manifest()

        unnamed = [
            e.filename for e in manifest.entries() if e.kind in ("patch", "crack") and not e.game
        ]

        assert unnamed == [], f"patches with no game named: {unnamed}"

    def test_every_patch_carries_target_checksums(self):
        manifest = artifacts.load_default_manifest()

        unbound = [
            e.filename
            for e in manifest.entries()
            if e.kind in ("patch", "crack") and not (e.target_crc1 and e.target_crc2)
        ]

        assert unbound == [], f"patches with no binding: {unbound}"

    def test_no_two_entries_share_a_filename(self):
        manifest = artifacts.load_default_manifest()
        names = [e.filename for e in manifest.entries()]

        assert len(names) == len(set(names))

    def test_a_header_sidecar_is_a_companion_of_its_patch(self):
        manifest = artifacts.load_default_manifest()
        headers = {e.filename for e in manifest.entries() if e.kind == "header"}

        claimed = {c for e in manifest.entries() for c in e.companions}

        assert headers <= claimed, f"orphan headers: {sorted(headers - claimed)}"


def _entry(**over):
    base = {
        "name": "Test patch",
        "kind": "patch",
        "filename": "test.aps",
        "size": 16,
        "sha256": "0" * 64,
        "crc32": "00000000",
        "provenance": "made up for a test",
    }
    return artifacts.ArtifactEntry(**{**base, **over})


class TestTheManifestRoundTrips:
    """Every optional field, because the writer drops the ones that are empty.

    A manifest is written from these dictionaries and read back into these
    objects. A field the writer forgets is a field the reader never sees again,
    and the only place that shows up is a patch that stops being recognised.
    """

    def test_a_bare_entry_carries_only_the_required_keys(self):
        out = artifacts.entry_to_dict(_entry())

        assert set(out) == {
            "name",
            "kind",
            "filename",
            "size",
            "sha256",
            "crc32",
            "provenance",
        }

    def test_every_optional_field_survives_the_trip(self):
        rich = _entry(
            target_crc1="11111111",
            target_crc2="22222222",
            game="A Game",
            description="Boot and save fix",
            companions=("test.ram",),
            region="USA",
            game_code="NTS",
            checksum_after="33333333",
            in_patch_database=True,
        )

        out = artifacts.entry_to_dict(rich)
        back = artifacts._entry_from_dict(out)

        assert out["target_crc1"] == "11111111"
        assert out["target_crc2"] == "22222222"
        assert out["checksum_after"] == "33333333"
        assert out["in_patch_database"] is True
        assert back == rich


class TestWhoOwnsACompanion:
    def test_a_file_no_patch_claims_has_no_owner(self):
        manifest = artifacts.Manifest(by_sha256={"a": _entry()})

        assert artifacts.owning_patch(manifest, "orphan.ram") is None

    def test_a_file_a_patch_lists_resolves_to_that_patch(self):
        owner = _entry(companions=("test.ram",))
        manifest = artifacts.Manifest(by_sha256={"a": owner})

        assert artifacts.owning_patch(manifest, "test.ram") is owner

    def test_a_file_the_manifest_never_names_is_not_in_the_database(self):
        manifest = artifacts.Manifest(by_sha256={"a": _entry()})

        assert artifacts._in_database(manifest, "nothing.aps") is False


class TestTheGeneratedFolderReadme:
    """The row for a save file, which has no game of its own to name.

    A companion is meaningless apart from the patch it ships with, so the row
    borrows the game and says which patch it belongs to. Without that the column
    is blank and the reader cannot tell what the file is for.
    """

    def test_a_companion_borrows_the_game_from_its_patch(self):
        owner = _entry(filename="game.aps", game="A Game", companions=("game.ram",))
        save = _entry(filename="game.ram", kind="save", game=None, description=None)
        manifest = artifacts.Manifest(by_sha256={"a": owner, "b": save})

        row = artifacts._folder_row(save, manifest)

        assert "A Game" in row
        assert "`game.aps`" in row

    def test_an_entry_bound_to_no_checksum_says_so(self):
        row = artifacts._folder_row(_entry(), artifacts.Manifest())

        assert "not bound to a checksum" in row

    def test_an_entry_bound_to_a_checksum_prints_the_pair(self):
        row = artifacts._folder_row(
            _entry(target_crc1="11111111", target_crc2="22222222"), artifacts.Manifest()
        )

        assert "`11111111`" in row
        assert "`22222222`" in row
