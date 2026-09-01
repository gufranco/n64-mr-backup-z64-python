import json

from z64kit import roster


def entry(**over):
    base = {
        "disk": "Zip Disk 01",
        "source_name": "Banjo-Kazooie (USA) (Rev 1).z64",
        "image_name": "BANJO.Z64",
        "sha256": roster.digest(b"rev one"),
        "crc1": "A4BF9306",
        "crc2": "BF0CDFD1",
        "size": 7,
        "game_code": "NBKE",
        "internal_name": "BANJO KAZOOIE",
        "region": "USA",
        "version": 0,
    }
    return roster.Entry(**{**base, **over})


class TestWhatAnEntryClaims:
    def test_the_binding_is_the_pair_a_patch_matches_on(self):
        assert entry().binding == "A4BF9306 BF0CDFD1"

    def test_a_patch_binding_makes_the_revision_a_requirement(self):
        assert entry(pinned_by=("banjo.hdr",)).required is True

    def test_without_one_the_entry_records_a_choice_rather_than_a_requirement(self):
        """Overstating this would invent a hardware requirement no evidence
        supports. Most of the collection is curation, not compulsion."""
        assert entry().required is False


class TestRoundTrippingTheFile:
    def test_what_is_written_reads_back_the_same(self, tmp_path):
        original = roster.Roster(
            generated="2026-08-27",
            entries=(entry(pinned_by=("banjo.hdr",)), entry(disk="Zip Disk 02")),
        )
        path = tmp_path / "roms.roster.json"
        path.write_text(roster.dumps(original), encoding="utf-8")

        assert roster.load(path) == original

    def test_writing_an_unchanged_collection_produces_an_identical_file(self, tmp_path):
        built = roster.Roster(generated="2026-08-27", entries=(entry(), entry(disk="Zip Disk 02")))

        assert roster.dumps(built) == roster.dumps(built)

    def test_entry_order_does_not_change_the_file(self):
        one, two = entry(disk="Zip Disk 02"), entry(disk="Zip Disk 01")
        forward = roster.Roster(generated="d", entries=(one, two))
        backward = roster.Roster(generated="d", entries=(two, one))

        assert roster.dumps(forward) == roster.dumps(backward)

    def test_a_file_missing_the_optional_fields_still_loads(self, tmp_path):
        path = tmp_path / "old.json"
        path.write_text(
            json.dumps(
                {
                    "generated": "2026-01-01",
                    "entries": [
                        {
                            "disk": "Zip Disk 01",
                            "source_name": "a.z64",
                            "image_name": "A.Z64",
                            "sha256": "00",
                            "crc1": "1",
                            "crc2": "2",
                            "size": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        loaded = roster.load(path)

        assert loaded.entries[0].pinned_by == ()
        assert loaded.schema == roster.SCHEMA

    def test_the_indexes_reach_every_entry(self):
        built = roster.Roster(generated="d", entries=(entry(),))

        assert built.by_sha256[entry().sha256] == entry()
        assert built.by_binding["A4BF9306 BF0CDFD1"] == entry()

    def test_the_pinned_view_holds_only_what_a_patch_requires(self):
        built = roster.Roster(
            generated="d", entries=(entry(pinned_by=("banjo.hdr",)), entry(disk="Zip Disk 02"))
        )

        assert len(built.pinned) == 1


class TestCheckingACollectionAgainstIt:
    def test_the_right_bytes_under_the_right_name_pass(self):
        report = roster.check(
            roster.Roster(generated="d", entries=(entry(),)),
            {"Banjo-Kazooie (USA) (Rev 1).z64": b"rev one"},
        )

        assert report.ok is True
        assert report.matched == 1
        assert report.findings == ()

    def test_the_right_bytes_under_another_name_still_pass(self):
        """The roster keys on content, and the build renames to 8.3 anyway, so a
        differently named file is worth reporting and is not a defect."""
        report = roster.check(
            roster.Roster(generated="d", entries=(entry(),)), {"banjo.z64": b"rev one"}
        )

        assert report.ok is True
        assert [one.kind for one in report.findings] == ["renamed"]

    def test_a_substituted_revision_a_patch_pins_is_reported_as_such(self):
        """The case this whole file exists for: the right name over the wrong
        bytes, where a patch pins the revision."""
        report = roster.check(
            roster.Roster(generated="d", entries=(entry(pinned_by=("banjo.hdr",)),)),
            {"Banjo-Kazooie (USA) (Rev 1).z64": b"rev two"},
        )

        assert report.ok is False
        assert [one.kind for one in report.findings] == ["wrong-revision"]
        assert "banjo.hdr" in report.findings[0].detail

    def test_a_substitution_no_patch_pins_is_reported_more_softly(self):
        report = roster.check(
            roster.Roster(generated="d", entries=(entry(),)),
            {"Banjo-Kazooie (USA) (Rev 1).z64": b"rev two"},
        )

        assert [one.kind for one in report.findings] == ["wrong-bytes"]
        assert "not pinned by any patch" in report.findings[0].detail

    def test_a_game_that_is_simply_absent_is_reported_as_missing(self):
        report = roster.check(roster.Roster(generated="d", entries=(entry(),)), {})

        assert report.ok is False
        assert [one.kind for one in report.findings] == ["missing"]

    def test_a_file_the_roster_does_not_name_is_listed_without_blocking(self):
        report = roster.check(
            roster.Roster(generated="d", entries=(entry(),)),
            {"Banjo-Kazooie (USA) (Rev 1).z64": b"rev one", "stranger.z64": b"x"},
        )

        assert report.ok is True
        assert report.extra == ("stranger.z64",)

    def test_a_renamed_file_is_not_also_counted_as_a_stranger(self):
        report = roster.check(
            roster.Roster(generated="d", entries=(entry(),)), {"banjo.z64": b"rev one"}
        )

        assert report.extra == ()

    def test_only_the_two_substitution_kinds_and_missing_block_a_build(self):
        kinds = {"missing", "wrong-revision", "wrong-bytes", "renamed"}
        blocking = {kind for kind in kinds if roster.Finding(kind, entry()).blocking}

        assert blocking == {"missing", "wrong-revision", "wrong-bytes"}


class TestFindingTheRightRomsInAnyPile:
    """The roster keys on content, so a collection renamed by any convention, or
    tipped into one flat folder, resolves exactly as a curated tree does."""

    def roster_of(self, *entries):
        return roster.Roster(generated="d", entries=entries)

    def test_a_rom_under_a_meaningless_name_is_still_found(self):
        known = self.roster_of(entry(sha256=roster.digest(b"rev one")))

        outcome = roster.resolve(known, {roster.digest(b"rev one"): "/pile/00000001.bin"})

        assert outcome.complete is True
        assert outcome.placements[0].source == "/pile/00000001.bin"
        assert outcome.placements[0].entry.image_name == "BANJO.Z64"

    def test_what_is_absent_is_reported_with_the_digest_to_hunt_for(self):
        known = self.roster_of(entry())

        outcome = roster.resolve(known, {})

        assert outcome.complete is False
        assert outcome.missing[0].sha256 == entry().sha256

    def test_an_absence_that_breaks_a_patch_is_separated_from_one_that_does_not(self):
        known = self.roster_of(
            entry(pinned_by=("banjo.zps",)), entry(source_name="Mario.z64", sha256="ff")
        )

        outcome = roster.resolve(known, {})

        assert len(outcome.missing) == 2
        assert [one.source_name for one in outcome.missing_pinned] == [entry().source_name]

    def test_files_the_roster_does_not_want_are_listed_rather_than_used(self):
        known = self.roster_of(entry())

        outcome = roster.resolve(
            known, {entry().sha256: "/pile/a.z64", roster.digest(b"other"): "/pile/b.z64"}
        )

        assert outcome.unused == ("/pile/b.z64",)

    def test_resolving_twice_places_the_same_files(self):
        known = self.roster_of(entry(), entry(source_name="Mario.z64", sha256=roster.digest(b"m")))
        pile = {entry().sha256: "/pile/one", roster.digest(b"m"): "/pile/two"}

        first = roster.resolve(known, pile)
        second = roster.resolve(known, pile)

        assert first == second

    def test_an_empty_roster_resolves_to_nothing_needed(self):
        outcome = roster.resolve(self.roster_of(), {roster.digest(b"x"): "/pile/x"})

        assert outcome.complete is True
        assert outcome.unused == ("/pile/x",)


class TestTheIdentityTheCartridgeCarriesInsideItself:
    """None of this decides anything, the digest already does. It is here so a
    person reading an entry recognises the game, since the filename is the one
    part of a dump anybody can change."""

    def test_the_internal_name_survives_a_round_trip(self, tmp_path):
        built = roster.Roster(generated="d", entries=(entry(),))
        path = tmp_path / "r.json"
        path.write_text(roster.dumps(built), encoding="utf-8")

        loaded = roster.load(path).entries[0]

        assert loaded.internal_name == "BANJO KAZOOIE"
        assert loaded.region == "USA"
        assert loaded.version == 0

    def test_a_file_written_before_these_fields_existed_still_loads(self, tmp_path):
        import json

        path = tmp_path / "old.json"
        path.write_text(
            json.dumps(
                {
                    "generated": "2026-01-01",
                    "entries": [
                        {
                            "disk": "Zip Disk 01",
                            "source_name": "a.z64",
                            "image_name": "A.Z64",
                            "sha256": "00",
                            "crc1": "1",
                            "crc2": "2",
                            "size": 1,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        loaded = roster.load(path).entries[0]

        assert loaded.internal_name == ""
        assert loaded.version == 0
