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
