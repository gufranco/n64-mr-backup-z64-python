import dataclasses

import pytest

from z64kit import compat, inventory
from z64kit.report import catalogue, tiers


@pytest.fixture(scope="module")
def rules():
    return compat.load_rules()


def row(**over):
    base = {
        "disk": "Zip Disk 01",
        "title": "Wave Race 64 (USA)",
        "mib": 8,
        "cic": "6102",
        "save": "eeprom512",
        "status": "native",
    }
    base.update(over)
    return catalogue.Row(**base)


class TestStatusLabel:
    """The old flag column carried six markers and five said what the rest of the
    row already said. Only the companion save file had nowhere else to live."""

    def test_a_plain_status_reads_as_itself(self):
        assert catalogue.status_label("native", needs_file=False) == "saves"

    def test_a_companion_requirement_is_marked(self):
        assert catalogue.NEEDS_FILE in catalogue.status_label("native", needs_file=True)

    def test_the_status_survives_the_marker(self):
        assert catalogue.status_label("patched", needs_file=True).startswith("patched")

    def test_an_unknown_status_is_printed_rather_than_dropped(self):
        assert catalogue.status_label("something-new", needs_file=False) == "something-new"


class TestBuild:
    def test_produces_a_compilable_document(self, rules):
        out = catalogue.build([row()], rules=rules, held=inventory.Inventory(), generated="today")

        assert out.startswith(r"\documentclass")
        assert r"\end{document}" in out

    def test_names_every_disk(self, rules):
        rows = [row(disk="Zip Disk 01"), row(disk="Zip Disk 02", title="Other")]

        out = catalogue.build(rows, rules=rules, held=inventory.Inventory(), generated="today")

        assert "Zip Disk 01" in out
        assert "Zip Disk 02" in out

    def test_escapes_a_title_containing_latex_syntax(self, rules):
        out = catalogue.build(
            [row(title="Command & Conquer (USA)")],
            rules=rules,
            held=inventory.Inventory(),
            generated="today",
        )

        assert r"Command \& Conquer" in out

    def test_states_that_nothing_is_claimed_when_no_inventory_is_recorded(self, rules):
        out = catalogue.build([row()], rules=rules, held=inventory.Inventory(), generated="today")

        assert "does not claim" in out

    def test_omits_that_caveat_once_an_inventory_exists(self, rules):
        held = inventory.Inventory(owned=frozenset({"boot"}), recorded=True)

        out = catalogue.build([row()], rules=rules, held=held, generated="today")

        assert "does not claim" not in out

    def test_counts_titles_by_status(self, rules):
        rows = [row(status="native"), row(status="needs-donor", title="Other")]

        out = catalogue.build(rows, rules=rules, held=inventory.Inventory(), generated="today")

        assert "Cannot save without hardware" in out

    def test_it_counts_games_needing_a_companion_file(self, rules):
        rows = [row(needs_file=True), row(title="Other")]

        out = catalogue.build(rows, rules=rules, held=inventory.Inventory(), generated="today")

        assert "Needs a companion save file" in out

    def test_reports_the_boot_chip_action_for_a_non_default_chip(self, rules):
        out = catalogue.build(
            [row(cic="6105")], rules=rules, held=inventory.Inventory(), generated="today"
        )

        assert "Country Fix" in out

    def test_says_no_change_is_needed_for_the_default_chip(self, rules):
        out = catalogue.build([row()], rules=rules, held=inventory.Inventory(), generated="today")

        assert "no change needed" in out

    def test_cites_where_the_memory_limit_came_from(self, rules):
        out = catalogue.build([row()], rules=rules, held=inventory.Inventory(), generated="today")

        assert "manual" in out.lower()

    def test_an_empty_collection_still_produces_a_document(self, rules):
        out = catalogue.build([], rules=rules, held=inventory.Inventory(), generated="today")

        assert r"\end{document}" in out


class TestPerGameRequirements:
    def rows_with(self, requirement, title="Blocked Game (USA)"):
        return [
            catalogue.Row(
                disk="Zip Disk 01",
                title=title,
                mib=16,
                cic="6102",
                save="EEPROM 16Kb",
                status="needs-donor",
                requirement=requirement,
            )
        ]

    def test_a_blocked_game_gets_its_own_section(self):
        doc = catalogue.build(
            self.rows_with("Needs a 16 Kbit EEPROM donor."),
            rules=compat.load_rules(),
            held=inventory.Inventory(),
            generated="2026-08-20",
        )

        assert "What each affected game needs" in doc

    def test_the_sentence_reaches_the_document(self):
        doc = catalogue.build(
            self.rows_with("Needs a 16 Kbit EEPROM donor, for example Star Wars Episode I Racer."),
            rules=compat.load_rules(),
            held=inventory.Inventory(),
            generated="2026-08-20",
        )

        assert "Star Wars Episode I Racer" in doc

    def test_the_game_title_appears_beside_its_requirement(self):
        """Trimmed, like everywhere else the title is printed."""
        doc = catalogue.build(
            self.rows_with("Needs a FlashRAM donor."),
            rules=compat.load_rules(),
            held=inventory.Inventory(),
            generated="2026-08-20",
        )

        assert "Blocked Game" in doc
        assert "(USA)" not in doc

    def test_a_collection_with_nothing_blocked_omits_the_section(self):
        rows = [
            catalogue.Row(
                disk="Zip Disk 01",
                title="Fine Game (USA)",
                mib=8,
                cic="6102",
                save="EEPROM 4Kb",
                status="native",
                requirement="",
            )
        ]

        doc = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="2026-08-20"
        )

        assert "What each affected game needs" not in doc

    def test_two_games_needing_the_same_thing_are_both_listed(self):
        rows = self.rows_with("Needs a FlashRAM donor.", title="Game A") + self.rows_with(
            "Needs a FlashRAM donor.", title="Game B"
        )

        doc = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="2026-08-20"
        )

        assert "Game A" in doc
        assert "Game B" in doc

    def test_the_requirement_defaults_to_empty_so_existing_callers_keep_working(self):
        row = catalogue.Row(
            disk="d",
            title="t",
            mib=1,
            cic="6102",
            save="None",
            status="native",
        )

        assert row.requirement == ""


@dataclasses.dataclass(frozen=True)
class FakeGame:
    filename: str
    stem: str
    size: int = 16 * 1024 * 1024
    cic: str = "6102"
    crc1: str = "AABBCCDD"
    true_extension: str = "Z64"
    checksum_valid: bool = True
    path: str = "/nonexistent/not-a-real-rom.z64"


class TestRowsFromCarriesRequirements:
    def test_a_game_needing_a_donor_gets_a_sentence(self):
        layout = [("Zip Disk 01", [FakeGame(filename="dk64.z64", stem="Donkey Kong 64 (USA)")])]

        rows = catalogue.rows_from(
            layout,
            {"dk64.z64": "eeprom2k"},
            compat.load_rules(),
            set(),
        )

        assert "donor" in rows[0].requirement.lower()

    def test_a_game_needing_nothing_gets_an_empty_sentence(self):
        layout = [("Zip Disk 01", [FakeGame(filename="ok.z64", stem="Fine Game (USA)")])]

        rows = catalogue.rows_from(layout, {"ok.z64": "eeprom512"}, compat.load_rules(), set())

        assert rows[0].requirement == ""


def video_row(title="A Game", disk="Zip Disk 01", **video):
    return catalogue.Row(
        disk=disk,
        title=title,
        mib=16,
        cic="6102",
        save="none",
        status="native",
        video=catalogue.Video(**video) if video or video == {} else None,
    )


class TestVideoState:
    """Two settings that live in different places and fail for different reasons."""

    def test_anti_aliasing_needs_a_mode_table(self):
        assert catalogue.Video(modes=0, antialiasing_on=0).aa_patchable is False

    def test_anti_aliasing_needs_it_to_be_on_in_the_first_place(self):
        assert catalogue.Video(modes=8, antialiasing_on=0).aa_patchable is False

    def test_anti_aliasing_is_patchable_when_a_table_has_it_on(self):
        assert catalogue.Video(modes=8, antialiasing_on=6).aa_patchable is True

    def test_the_filter_needs_no_mode_table(self):
        """GoldenEye 007 carries the routine and no table."""
        assert catalogue.Video(modes=0, dither_requests=1).dither_patchable is True

    def test_a_rom_that_never_switches_the_filter_on_is_not_a_gap(self):
        state = catalogue.Video(modes=8, dither_requests=0)

        assert state.dither_patchable is False
        assert "unreachable" not in state.summary or state.modes == 0

    def test_an_invalid_checksum_blocks_everything(self):
        state = catalogue.Video(modes=8, antialiasing_on=6, dither_requests=1, checksum_valid=False)

        assert state.aa_patchable is False
        assert state.dither_patchable is False
        assert "no boot chip" in state.summary

    def test_the_summary_names_both_when_both_apply(self):
        state = catalogue.Video(modes=8, antialiasing_on=6, dither_requests=1)

        assert "anti-aliasing" in state.summary
        assert "dedither" in state.summary


class TestVideoSection:
    def test_the_document_carries_a_video_section(self):
        rows = [video_row(modes=8, antialiasing_on=6, dither_requests=1)]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert "Video" in out

    def test_what_a_game_gives_up_is_in_its_own_disk_listing(self):
        """The section carries counts only. A second per-game table would repeat
        the Video column and add a page."""
        rows = [video_row(title="Super Mario 64", modes=10, antialiasing_on=6, dither_requests=1)]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert "Super Mario 64" in out
        assert "removes anti-aliasing and dedither" in out

    def test_no_game_is_listed_twice(self):
        rows = [video_row(title="Super Mario 64", modes=10, antialiasing_on=6, dither_requests=1)]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert out.count("Super Mario 64") == 1

    def test_it_explains_that_the_filter_is_the_main_blur(self):
        rows = [video_row(modes=8, antialiasing_on=6)]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert "dedither filter" in out

    def test_a_refused_game_says_so_in_its_own_row(self):
        """A separate refused list repeated the Video column on the same games."""
        rows = [
            video_row(title="Pokemon Stadium", modes=8, dither_requests=1, checksum_valid=False)
        ]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert "refused, no boot chip" in out
        assert out.count("Pokemon Stadium") == 1

    def test_a_count_of_zero_is_left_out_rather_than_printed(self):
        rows = [video_row(modes=8, antialiasing_on=6, dither_requests=1)]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert "Could not be read" not in out

    def test_the_disk_listing_carries_a_video_column(self):
        rows = [video_row(modes=8, antialiasing_on=6, dither_requests=1)]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert "Video" in out
        assert "dedither" in out

    def test_a_game_that_could_not_be_read_says_so_rather_than_claiming_it_is_clean(self):
        rows = [
            catalogue.Row(
                disk="Zip Disk 01",
                title="Unknown",
                mib=8,
                cic="6102",
                save="none",
                status="native",
            )
        ]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert catalogue.VIDEO_UNREAD in out

    def test_the_counts_survive_when_nothing_was_read(self):
        rows = [
            catalogue.Row(
                disk="Zip Disk 01",
                title="Unknown",
                mib=8,
                cic="6102",
                save="none",
                status="native",
            )
        ]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert "Video" not in out.split("Disk contents")[0].split("Flags")[0]


class TestVideoFor:
    def test_an_unreadable_rom_is_unknown_rather_than_clean(self):
        game = FakeGame(filename="x.z64", stem="X", path="/nonexistent/x.z64")

        assert catalogue.video_for(game) is None


class TestTitlesAreTrimmedForPrint:
    """The catalogue is USA-only and says so, so (USA) on all 292 rows is six
    characters of nothing repeated 292 times. Language lists are the same: the
    unit does not choose a language and the reader cannot act on the list."""

    def test_the_region_tag_goes(self):
        assert catalogue.printable_title("Super Mario 64 (USA)") == "Super Mario 64"

    def test_a_language_list_goes(self):
        found = catalogue.printable_title("FIFA - Road to World Cup 98 (USA) (En,Fr,De,Es)")

        assert found == "FIFA - Road to World Cup 98"

    def test_a_revision_stays_because_it_identifies_the_dump(self):
        found = catalogue.printable_title("San Francisco Rush (USA) (Rev 1)")

        assert "Rev 1" in found

    def test_the_revision_loses_only_its_brackets(self):
        assert catalogue.printable_title("Wave Race 64 (USA) (Rev 1)") == "Wave Race 64 Rev 1"

    def test_a_qualifier_that_names_a_different_game_stays(self):
        """Master Quest and the GameCube disc are separate releases, not noise."""
        found = catalogue.printable_title(
            "Legend of Zelda, The - Ocarina of Time - Master Quest (USA) (GameCube)"
        )

        assert "Master Quest" in found
        assert "GameCube" in found

    def test_a_title_with_nothing_to_trim_is_unchanged(self):
        assert catalogue.printable_title("Body Harvest") == "Body Harvest"

    def test_it_leaves_no_double_spaces_behind(self):
        assert "  " not in catalogue.printable_title("Mario Kart 64 (USA) (Rev 1)")

    def test_the_trimmed_title_reaches_the_document(self):
        rows = [row(title="Super Mario 64 (USA)")]

        out = catalogue.build(
            rows, rules=compat.load_rules(), held=inventory.Inventory(), generated="today"
        )

        assert "Super Mario 64" in out
        assert "(USA)" not in out


class TestTierBands:
    """The reader's own ranking, which splits the disk list into sections.

    The bands come from a file the reader writes. When there are none the
    catalogue is a flat list of disks, and when there are some each one opens a
    section, so the heading has to appear once per band rather than once per
    disk inside it.
    """

    def bands(self):
        return (
            tiers.Band(name="S", label="Best", through_disk=1),
            tiers.Band(name="A", label="", through_disk=9),
        )

    def rows(self):
        return [row(disk="Zip Disk 01"), row(disk="Zip Disk 02")]

    def test_each_band_opens_a_section(self):
        out = catalogue.build(
            self.rows(),
            rules=compat.load_rules(),
            held=inventory.Inventory(),
            generated="today",
            bands=self.bands(),
        )

        assert "S-tier: Best" in out
        assert "A-tier" in out

    def test_the_note_explaining_the_bands_is_printed(self):
        out = catalogue.build(
            self.rows(),
            rules=compat.load_rules(),
            held=inventory.Inventory(),
            generated="today",
            bands=self.bands(),
        )

        assert "the ranking is the" in out.lower()

    def test_without_bands_no_section_appears(self):
        out = catalogue.build(
            self.rows(),
            rules=compat.load_rules(),
            held=inventory.Inventory(),
            generated="today",
        )

        assert "-tier" not in out
