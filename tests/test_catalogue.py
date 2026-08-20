import dataclasses

import pytest

from z64kit import compat, inventory
from z64kit.report import catalogue


@pytest.fixture(scope="module")
def rules():
    return compat.load_rules()


def row(**over):
    base = {
        "disk": "Zip Disk 01",
        "title": "Wave Race 64 (USA)",
        "name83": "WAVER64.Z64",
        "mib": 8,
        "cic": "6102",
        "save": "eeprom512",
        "status": "native",
        "flags": "",
        "crc1": "11223344",
    }
    base.update(over)
    return catalogue.Row(**base)


class TestFlags:
    def test_marks_a_patched_title(self, rules):
        verdict = compat.classify(
            compat.Candidate(key="k", title="t", save="eeprom2k", has_patch=True), rules
        )
        game = type("G", (), {"checksum_valid": True})()

        assert "P" in catalogue.flags_for(verdict, game, has_companion=False)

    def test_marks_a_title_that_cannot_save(self, rules):
        verdict = compat.classify(compat.Candidate(key="k", title="t", save="flash128k"), rules)
        game = type("G", (), {"checksum_valid": True})()

        assert "!" in catalogue.flags_for(verdict, game, has_companion=False)

    def test_marks_a_title_too_large_to_load(self, rules):
        verdict = compat.classify(
            compat.Candidate(key="k", title="t", size=64 * 1024 * 1024), rules
        )
        game = type("G", (), {"checksum_valid": True})()

        assert "X" in catalogue.flags_for(verdict, game, has_companion=False)

    def test_marks_a_companion_requirement(self, rules):
        verdict = compat.classify(compat.Candidate(key="k", title="t"), rules)
        game = type("G", (), {"checksum_valid": True})()

        assert "+" in catalogue.flags_for(verdict, game, has_companion=True)

    def test_marks_an_unverified_dump(self, rules):
        verdict = compat.classify(compat.Candidate(key="k", title="t"), rules)
        game = type("G", (), {"checksum_valid": False})()

        assert "?" in catalogue.flags_for(verdict, game, has_companion=False)

    def test_a_clean_native_title_carries_no_flags(self, rules):
        verdict = compat.classify(compat.Candidate(key="k", title="t", save="eeprom512"), rules)
        game = type("G", (), {"checksum_valid": True})()

        assert catalogue.flags_for(verdict, game, has_companion=False) == ""


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

    def test_explains_every_flag_it_uses(self, rules):
        out = catalogue.build([row()], rules=rules, held=inventory.Inventory(), generated="today")

        for flag, _ in catalogue.FLAG_LEGEND:
            assert flag in out

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
                name83="BLOCKED",
                mib=16,
                cic="6102",
                save="EEPROM 16Kb",
                status="needs-donor",
                flags="!",
                crc1="AABBCCDD",
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
        doc = catalogue.build(
            self.rows_with("Needs a FlashRAM donor."),
            rules=compat.load_rules(),
            held=inventory.Inventory(),
            generated="2026-08-20",
        )

        assert "Blocked Game (USA)" in doc

    def test_a_collection_with_nothing_blocked_omits_the_section(self):
        rows = [
            catalogue.Row(
                disk="Zip Disk 01",
                title="Fine Game (USA)",
                name83="FINE",
                mib=8,
                cic="6102",
                save="EEPROM 4Kb",
                status="native",
                flags="",
                crc1="11223344",
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
            name83="N",
            mib=1,
            cic="6102",
            save="None",
            status="native",
            flags="",
            crc1="0",
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


class TestRowsFromCarriesRequirements:
    def test_a_game_needing_a_donor_gets_a_sentence(self):
        layout = [("Zip Disk 01", [FakeGame(filename="dk64.z64", stem="Donkey Kong 64 (USA)")])]

        rows = catalogue.rows_from(
            layout,
            {"dk64.z64": "DK64"},
            {"dk64.z64": "eeprom2k"},
            compat.load_rules(),
            set(),
        )

        assert "donor" in rows[0].requirement.lower()

    def test_a_game_needing_nothing_gets_an_empty_sentence(self):
        layout = [("Zip Disk 01", [FakeGame(filename="ok.z64", stem="Fine Game (USA)")])]

        rows = catalogue.rows_from(
            layout, {"ok.z64": "FINE"}, {"ok.z64": "eeprom512"}, compat.load_rules(), set()
        )

        assert rows[0].requirement == ""
