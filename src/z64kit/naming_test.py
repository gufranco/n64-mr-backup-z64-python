import pytest

from z64kit import naming

GOLDEN = [
    ("Super Mario 64 (USA)", "MARIO64"),
    ("Legend of Zelda, The - Ocarina of Time (USA) (Rev 2)", "ZELDAOOT"),
    ("Legend of Zelda, The - Majora's Mask (USA)", "ZELDAMM"),
    ("GoldenEye 007 (USA)", "GOLDE007"),
    ("Banjo-Kazooie (USA) (Rev 1)", "BANJOK"),
    ("Banjo-Tooie (USA)", "BANJOT"),
    ("Conker's Bad Fur Day (USA)", "CBFD"),
    ("Perfect Dark (USA) (Rev 1)", "PERFECTD"),
    ("Mario Kart 64 (USA)", "MARIOK64"),
    ("Star Fox 64 (USA) (Rev 1)", "STAFOX64"),
    ("Diddy Kong Racing (USA) (En,Fr) (Rev 1)", "DIDDYKR"),
    ("Super Smash Bros. (USA)", "SMASBROS"),
    ("Resident Evil 2 (USA) (Rev 1)", "RESEVIL2"),
    ("1080 Snowboarding (Japan, USA) (En,Ja)", "1080SNOW"),
    ("Donkey Kong 64 (USA)", "DONKEK64"),
    ("Turok - Dinosaur Hunter (USA) (Rev 2)", "TUROKDH"),
    ("Turok 2 - Seeds of Evil (USA) (Rev 1)", "TURO2SOE"),
    ("Turok 3 - Shadow of Oblivion (USA)", "TURO3SOO"),
    ("S.C.A.R.S. (USA)", "SCRS"),
    ("Charlie Blast's Territory (USA)", "CHARLIBT"),
    ("Magical Tetris Challenge (USA)", "MAGICATC"),
    ("Pokemon Puzzle League (USA)", "POKEMOPL"),
    ("SpaceStation Silicon Valley (USA) (Rev 1)", "SPACESSV"),
    ("AeroFighters Assault (USA)", "AEROFIGA"),
]


class TestCleanTitle:
    def test_strips_region_and_revision_tags(self):
        title, tags = naming.clean_title("Super Mario 64 (USA) (Rev 1).z64")

        assert title == "Super Mario 64"
        assert "USA" in tags

    def test_moves_a_trailing_article_out_of_the_way(self):
        title, _ = naming.clean_title("Legend of Zelda, The - Majora's Mask (USA)")

        assert title.startswith("Legend of Zelda -")

    def test_drops_a_leading_article(self):
        title, _ = naming.clean_title("The New Tetris (USA)")

        assert title == "New Tetris"

    def test_removes_possessive_endings(self):
        title, _ = naming.clean_title("Conker's Bad Fur Day (USA)")

        assert title == "Conker Bad Fur Day"

    def test_transliterates_accents_rather_than_dropping_them(self):
        title, _ = naming.clean_title("Coracao Valido (USA)")

        assert title == "Coracao Valido"


class TestShorten:
    @pytest.mark.parametrize(("raw", "expected"), GOLDEN, ids=[g[1] for g in GOLDEN])
    def test_reproduces_the_validated_name(self, raw, expected):
        title, _ = naming.clean_title(raw)

        assert naming.shorten(title) == expected

    def test_never_exceeds_eight_characters(self):
        for raw, _ in GOLDEN:
            title, _ = naming.clean_title(raw)

            assert len(naming.shorten(title)) <= 8

    def test_never_produces_fewer_than_three_characters(self):
        for raw, _ in GOLDEN:
            title, _ = naming.clean_title(raw)

            assert len(naming.shorten(title)) >= 3

    def test_produces_only_uppercase_and_digits(self):
        for raw, _ in GOLDEN:
            title, _ = naming.clean_title(raw)

            assert naming.shorten(title).isalnum()

    def test_falls_back_when_a_title_has_no_usable_characters(self):
        assert naming.shorten("!!! ???") == "GAME"


class TestRegionLetter:
    @pytest.mark.parametrize(
        ("tags", "letter"),
        [(["USA"], "U"), (["Europe"], "E"), (["Japan"], "J"), (["Australia"], "A")],
    )
    def test_maps_a_known_region_tag(self, tags, letter):
        assert naming.region_letter(tags) == letter

    def test_falls_back_when_the_region_is_unknown(self):
        assert naming.region_letter(["Rev 1"]) == "X"


class TestAssignNames:
    def test_leaves_a_unique_name_alone(self):
        result, _, _ = naming.assign([("a", "Wave Race 64 (USA)")])

        assert result["a"] == "WAVER64"

    def test_disambiguates_a_collision_with_the_region_letter(self):
        items = [
            ("us", "Pokemon Snap (USA)"),
            ("eu", "Pokemon Snap (Europe)"),
            ("jp", "Pokemon Snap (Japan)"),
        ]

        result, _, _ = naming.assign(items)

        assert result["us"].endswith("U")
        assert result["eu"].endswith("E")
        assert result["jp"].endswith("J")
        assert len(set(result.values())) == 3

    def test_every_assigned_name_stays_within_eight_characters(self):
        items = [
            (str(i), f"Pokemon Stadium 2 ({r})")
            for i, r in enumerate(["USA", "Europe", "Japan", "France", "Germany"])
        ]

        result, _, _ = naming.assign(items)

        assert all(len(v) <= 8 for v in result.values())

    def test_falls_back_to_a_counter_when_regions_also_collide(self):
        items = [("a", "Bomberman 64 (USA)"), ("b", "Bomberman 64 (USA) (Rev 1)")]

        result, _, _ = naming.assign(items)

        assert len(set(result.values())) == 2

    def test_assignment_does_not_depend_on_input_order(self):
        items = [("a", "Pokemon Snap (USA)"), ("b", "Pokemon Snap (Europe)")]

        forward, _, _ = naming.assign(items)
        reverse, _, _ = naming.assign(list(reversed(items)))

        assert forward == reverse
