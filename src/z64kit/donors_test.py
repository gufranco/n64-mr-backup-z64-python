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


class TestCleanTitles:
    """The catalogue's names and No-Intro's names are not the same names.

    The rest of the report takes its titles from the collection's own files,
    which are No-Intro named. These tables took theirs from the catalogue, which
    writes a subtitle after a colon, appends the Japanese title in brackets, and
    keeps the accent in Pokemon. Two naming schemes in one document read as
    errors, and half of them are.
    """

    def test_a_bracketed_alternate_title_is_dropped(self):
        assert donors.clean_title("Jet Force Gemini [Star Twins]") == "Jet Force Gemini"

    def test_a_colon_subtitle_becomes_a_dash(self):
        assert donors.clean_title("GT 64: Championship Edition") == "GT 64 - Championship Edition"

    def test_a_region_or_revision_suffix_is_dropped(self):
        assert donors.clean_title("Pokemon Stadium (USA) (Rev 2)") == "Pokemon Stadium"

    def test_an_accent_is_folded_to_ascii(self):
        assert donors.clean_title("Pokémon Snap") == "Pokemon Snap"

    def test_both_forms_of_noise_go_at_once(self):
        assert (
            donors.clean_title("Pokémon Stadium 2 [Pocket Monsters Stadium - Kin Gin] (USA)")
            == "Pokemon Stadium 2"
        )

    def test_a_dash_already_in_the_title_survives(self):
        assert donors.clean_title("City Tour GrandPrix - Zen Nihon GT Senshuken") == (
            "City Tour GrandPrix - Zen Nihon GT Senshuken"
        )

    def test_a_clean_title_is_left_alone(self):
        assert donors.clean_title("Mario Tennis") == "Mario Tennis"


class TestACollectionSuppliesTheBetterName:
    """The catalogue abbreviates. A No-Intro named file does not.

    `Kirby 64` is the whole name the catalogue carries, and No-Intro calls the
    same cartridge `Kirby 64 - The Crystal Shards`. Where the reader already owns
    the game, their own filename is the more accurate source and is the one the
    rest of the document is already using.

    The link is the game code, matched by the same wildcard rule the catalogue
    itself uses, so a name is never attached to a cartridge by resemblance.
    """

    @pytest.fixture
    def catalogue(self) -> db.Database:
        return db.parse(
            "\n".join(
                [
                    "ID:NK4___ eeprom2k # Kirby 64",
                    "ID:NB7___ eeprom2k # Banjo-Tooie [Banjo to Kazooie no Daiboken 2]",
                ]
            )
        )

    def test_a_matching_collection_name_wins(self, catalogue):
        owned = {"NK4E": "Kirby 64 - The Crystal Shards"}

        found = donors.catalogued(catalogue, "eeprom2k", owned=owned)

        assert [d.title for d in found] == ["Banjo-Tooie", "Kirby 64 - The Crystal Shards"]

    def test_a_game_not_owned_keeps_the_cleaned_catalogue_name(self, catalogue):
        found = donors.catalogued(catalogue, "eeprom2k", owned={"NK4E": "Kirby 64 - Crystal"})

        assert "Banjo-Tooie" in [d.title for d in found]

    def test_a_code_matching_nothing_changes_no_name(self, catalogue):
        plain = donors.catalogued(catalogue, "eeprom2k")

        assert donors.catalogued(catalogue, "eeprom2k", owned={"NZZE": "Nope"}) == plain

    def test_the_collection_name_is_cleaned_too(self, catalogue):
        owned = {"NB7E": "Banjo-Tooie (USA) (Rev 1)"}

        found = donors.catalogued(catalogue, "eeprom2k", owned=owned)

        assert "Banjo-Tooie" in [d.title for d in found]
