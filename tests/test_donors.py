"""Which cartridges a reader could buy to satisfy a save-chip requirement.

The shopping list already says a 16 Kbit EEPROM donor is needed and names one
example. Someone standing in front of a shelf, or a search box, needs the rest:
every cartridge that carries the chip, and the code printed on the label so the
right one can be told from a reissue that does not carry it.

The catalogue this reads from is the save-type database, which lists prototypes,
kiosk units and romhacks alongside retail releases. Presenting all of them as
purchasable would be a claim the data does not support, so what is returned is
what the catalogue holds and the wording around it says exactly that.
"""

from __future__ import annotations

import pytest

from z64kit import db, donors


@pytest.fixture
def catalogue() -> db.Database:
    return db.parse(
        "\n".join(
            [
                "ID:NB7___ eeprom2k|cic6105 # Banjo-Tooie",
                "ID:NDK___ eeprom2k|cic6105 # Donkey Kong 64",
                "ID:NCC___ flash128k|cic6102 # Command & Conquer",
                "ID:NZS___ flash128k|cic6105 # Majora's Mask",
                "ID:NSM___ eeprom512|cic6102 # Super Mario 64",
                "ID:NKT___ none # Kart with no save",
            ]
        )
    )


class TestCataloguedDonors:
    def test_it_returns_every_cartridge_carrying_the_chip(self, catalogue):
        found = donors.catalogued(catalogue, "eeprom2k")

        assert [d.title for d in found] == ["Banjo-Tooie", "Donkey Kong 64"]

    def test_it_carries_the_code_printed_on_the_label(self, catalogue):
        found = donors.catalogued(catalogue, "flash128k")

        assert [(d.title, d.code) for d in found] == [
            ("Command & Conquer", "NCC"),
            ("Majora's Mask", "NZS"),
        ]

    def test_it_leaves_out_a_different_chip(self, catalogue):
        titles = [d.title for d in donors.catalogued(catalogue, "eeprom2k")]

        assert "Super Mario 64" not in titles

    def test_it_leaves_out_cartridges_that_save_nothing(self, catalogue):
        every = [
            d.title
            for tag in ("eeprom2k", "flash128k", "eeprom512")
            for d in donors.catalogued(catalogue, tag)
        ]

        assert "Kart with no save" not in every

    def test_it_sorts_by_title_so_the_page_is_scannable(self, catalogue):
        found = donors.catalogued(catalogue, "eeprom2k")

        assert [d.title for d in found] == sorted(d.title for d in found)

    def test_an_unknown_chip_yields_nothing(self, catalogue):
        assert donors.catalogued(catalogue, "sram96k") == ()

    def test_a_cartridge_with_no_title_is_left_out(self):
        catalogue = db.parse("ID:NXX___ eeprom2k")

        assert donors.catalogued(catalogue, "eeprom2k") == ()

    def test_the_same_title_is_not_listed_twice(self):
        catalogue = db.parse(
            "\n".join(
                [
                    "ID:NB7E__ eeprom2k # Banjo-Tooie",
                    "ID:NB7P__ eeprom2k # Banjo-Tooie",
                ]
            )
        )

        assert len(donors.catalogued(catalogue, "eeprom2k")) == 1


class TestTheSaveTagComesFromTheRules:
    def test_each_donor_names_the_chip_it_carries(self):
        from z64kit import compat

        rules = compat.load_rules()

        for key in rules.donors:
            assert compat.donor_save_tag(rules, key), key

    def test_the_tag_is_one_the_catalogue_uses(self):
        from z64kit import compat

        rules = compat.load_rules()

        for key in rules.donors:
            assert compat.donor_save_tag(rules, key) in db.SAVE_TAGS

    def test_an_unknown_donor_has_no_tag(self):
        from z64kit import compat

        assert compat.donor_save_tag(compat.load_rules(), "no-such-donor") == ""


class TestWildcardsInACode:
    """A pattern is not a code. Seven of the catalogue's 446 patterns say so.

    `_EP___` means the media letter varies, so Star Wars Episode I: Racer prints
    as `_EP` if the pattern is trimmed and handed over as if it were the string on
    the label. `NUB_2_` is worse: it reads as a code with an underscore in it.

    A wildcard is a real piece of information, that this position varies, so it
    is shown as one rather than silently dropped or passed through as an
    underscore a reader would take for part of the code.
    """

    def test_a_trailing_wildcard_is_dropped(self):
        catalogue = db.parse("ID:NB7___ eeprom2k # Banjo-Tooie")

        assert donors.catalogued(catalogue, "eeprom2k")[0].code == "NB7"

    def test_a_leading_wildcard_becomes_a_placeholder(self):
        catalogue = db.parse("ID:_EP___ eeprom2k # Star Wars Episode I: Racer")

        assert donors.catalogued(catalogue, "eeprom2k")[0].code == "?EP"

    def test_an_embedded_wildcard_becomes_a_placeholder(self):
        catalogue = db.parse("ID:NUB_2_ eeprom2k # Mario Kart 64 - Amped Up")

        assert donors.catalogued(catalogue, "eeprom2k")[0].code == "NUB?2"

    def test_no_underscore_survives_into_a_printed_code(self):
        catalogue = db.parse(
            "\n".join(
                [
                    "ID:NB7___ eeprom2k # Banjo-Tooie",
                    "ID:_EP___ eeprom2k # Star Wars Episode I: Racer",
                    "ID:NUB_2_ eeprom2k # Mario Kart 64 - Amped Up",
                ]
            )
        )

        for donor in donors.catalogued(catalogue, "eeprom2k"):
            assert "_" not in donor.code, donor
