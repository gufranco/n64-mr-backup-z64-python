"""Quality tiers, which the tool cannot know and the collection has to state.

A game's quality is a judgement, not a property of the file, so nothing here
infers one. What a curated collection can say is the order it was arranged in,
and a tiers file names where one band ends and the next begins.

Absent that file the document is unchanged, because inventing tier boundaries
would assert a ranking nobody asked for.
"""

from __future__ import annotations

import json

import pytest

from z64kit.report import tiers


def write(path, payload):
    (path / tiers.FILENAME).write_text(json.dumps(payload), encoding="utf-8")
    return path


BANDS = {
    "tiers": [
        {"name": "S", "label": "Masterpieces", "through_disk": 3},
        {"name": "A", "label": "Essential classics", "through_disk": 8},
        {"name": "B", "label": "Very good", "through_disk": 15},
    ]
}


class TestLoading:
    def test_a_collection_without_the_file_has_no_tiers(self, tmp_path):
        assert tiers.load(tmp_path) == ()

    def test_it_reads_the_bands(self, tmp_path):
        found = tiers.load(write(tmp_path, BANDS))

        assert [b.name for b in found] == ["S", "A", "B"]

    def test_it_keeps_the_label(self, tmp_path):
        assert tiers.load(write(tmp_path, BANDS))[0].label == "Masterpieces"

    def test_it_sorts_bands_by_where_they_end(self, tmp_path):
        shuffled = {"tiers": list(reversed(BANDS["tiers"]))}

        found = tiers.load(write(tmp_path, shuffled))

        assert [b.through_disk for b in found] == [3, 8, 15]

    def test_malformed_json_is_refused_rather_than_ignored(self, tmp_path):
        (tmp_path / tiers.FILENAME).write_text("{not json", encoding="utf-8")

        with pytest.raises(tiers.TierFileError, match="could not be read"):
            tiers.load(tmp_path)

    def test_a_band_missing_its_boundary_is_refused(self, tmp_path):
        with pytest.raises(tiers.TierFileError, match="through_disk"):
            tiers.load(write(tmp_path, {"tiers": [{"name": "S", "label": "x"}]}))

    def test_a_band_missing_its_name_is_refused(self, tmp_path):
        with pytest.raises(tiers.TierFileError, match="name"):
            tiers.load(write(tmp_path, {"tiers": [{"label": "x", "through_disk": 3}]}))

    def test_an_empty_list_is_the_same_as_no_file(self, tmp_path):
        assert tiers.load(write(tmp_path, {"tiers": []})) == ()


class TestAssigning:
    def bands(self):
        return tiers.load.__wrapped__ if False else tiers.parse(BANDS)

    def test_the_first_disk_lands_in_the_first_band(self):
        assert tiers.band_for(1, self.bands()).name == "S"

    def test_the_boundary_disk_belongs_to_the_band_it_closes(self):
        assert tiers.band_for(3, self.bands()).name == "S"

    def test_the_next_disk_starts_the_next_band(self):
        assert tiers.band_for(4, self.bands()).name == "A"

    def test_a_disk_past_every_band_has_none(self):
        assert tiers.band_for(99, self.bands()) is None

    def test_no_bands_means_no_band(self):
        assert tiers.band_for(1, ()) is None


class TestReadingTheDiskNumber:
    def test_it_reads_a_padded_number(self):
        assert tiers.disk_number("Zip Disk 07") == 7

    def test_it_reads_an_unpadded_number(self):
        assert tiers.disk_number("Disk 7") == 7

    def test_it_takes_the_first_number_it_finds(self):
        assert tiers.disk_number("Zip Disk 12 of 48") == 12

    def test_a_name_with_no_number_has_none(self):
        assert tiers.disk_number("Extras") is None


class TestARefusedTierFile:
    """A hand-edited file, which is the only way this one arrives.

    Nothing generates a tier file. A reader writes it, so every shape a reader
    can get wrong has to come back as a sentence naming the file rather than as
    a traceback from json or a KeyError three frames down.
    """

    def test_something_that_is_not_an_object(self):
        with pytest.raises(tiers.TierFileError, match="must hold an object"):
            tiers.parse([1, 2, 3])

    def test_an_object_with_no_tiers_list(self):
        with pytest.raises(tiers.TierFileError, match="must hold an object"):
            tiers.parse({"bands": []})

    def test_a_tiers_value_that_is_not_a_list(self):
        with pytest.raises(tiers.TierFileError, match="must hold an object"):
            tiers.parse({"tiers": "S,A,B"})

    def test_a_tier_that_is_not_an_object(self):
        with pytest.raises(tiers.TierFileError, match="must be an object"):
            tiers.parse({"tiers": ["S"]})


class TestABandWithNoLabel:
    def test_the_heading_is_just_the_tier_name(self):
        assert tiers.Band(name="S", label="", through_disk=4).heading == "S-tier"

    def test_a_label_is_appended_when_there_is_one(self):
        assert tiers.Band(name="S", label="Best", through_disk=4).heading == "S-tier: Best"
