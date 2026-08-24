import json

import pytest

from z64kit import compat, inventory


@pytest.fixture(scope="module")
def rules():
    return compat.load_rules()


def candidate(name, *, save="none", cic="6102", mib=8, patched=False):
    return compat.Candidate(
        key=name, title=name, save=save, cic=cic, size=mib * 1024 * 1024, has_patch=patched
    )


class TestEmptyInventory:
    def test_asserts_nothing_about_what_is_owned(self):
        held = inventory.Inventory()

        assert held.owns("boot") is False
        assert held.owns("eeprom16k") is False
        assert held.is_recorded is False

    def test_a_recorded_inventory_says_so_even_when_nothing_is_owned(self):
        held = inventory.Inventory(recorded=True)

        assert held.is_recorded is True
        assert held.owns("boot") is False


class TestQuestions:
    def test_asks_only_about_hardware_the_collection_needs(self, rules):
        games = [candidate("Wave Race 64 (USA)", save="eeprom512")]

        questions = inventory.questions(games, rules)

        assert [q.key for q in questions] == ["boot"]

    def test_asks_about_a_donor_when_a_title_needs_one(self, rules):
        games = [candidate("Pokemon Snap (USA)", save="flash128k")]

        keys = [q.key for q in inventory.questions(games, rules)]

        assert "flashram" in keys

    def test_does_not_ask_about_a_donor_a_patch_already_covers(self, rules):
        games = [candidate("Donkey Kong 64 (USA)", save="eeprom2k", patched=True)]

        keys = [q.key for q in inventory.questions(games, rules)]

        assert "eeprom16k" not in keys

    def test_names_how_many_titles_each_answer_affects(self, rules):
        games = [
            candidate("Pokemon Snap (USA)", save="flash128k"),
            candidate("StarCraft 64 (USA)", save="flash128k"),
        ]

        question = next(q for q in inventory.questions(games, rules) if q.key == "flashram")

        assert question.unlocks == 2

    def test_offers_an_example_cartridge_for_each_question(self, rules):
        games = [candidate("Pokemon Snap (USA)", save="flash128k")]

        question = next(q for q in inventory.questions(games, rules) if q.key == "flashram")

        assert question.examples

    def test_the_boot_question_comes_first(self, rules):
        games = [candidate("Pokemon Snap (USA)", save="flash128k")]

        assert inventory.questions(games, rules)[0].key == "boot"

    def test_an_empty_collection_still_asks_about_a_boot_cartridge(self, rules):
        assert [q.key for q in inventory.questions([], rules)] == ["boot"]


class TestShoppingList:
    def test_with_nothing_owned_every_requirement_is_outstanding(self, rules):
        games = [candidate("Pokemon Snap (USA)", save="flash128k")]

        result = inventory.shopping_list(games, inventory.Inventory(), rules)

        assert all(item.outstanding for item in result.items)

    def test_owning_a_donor_satisfies_its_requirement(self, rules):
        games = [candidate("Pokemon Snap (USA)", save="flash128k")]
        held = inventory.Inventory(owned=frozenset({"boot", "flashram"}), recorded=True)

        result = inventory.shopping_list(games, held, rules)

        assert all(not item.outstanding for item in result.items)

    def test_reports_which_titles_a_purchase_would_unlock(self, rules):
        games = [
            candidate("Pokemon Snap (USA)", save="flash128k"),
            candidate("Perfect Dark (USA)", save="eeprom2k"),
        ]

        result = inventory.shopping_list(games, inventory.Inventory(), rules)
        flash = next(i for i in result.items if i.key == "flashram")

        assert "Pokemon Snap (USA)" in flash.titles

    def test_a_title_needing_a_donor_is_still_blocked_without_it(self, rules):
        games = [candidate("Pokemon Snap (USA)", save="flash128k")]

        result = inventory.shopping_list(games, inventory.Inventory(), rules)

        assert "Pokemon Snap (USA)" in result.blocked

    def test_a_title_stops_being_blocked_once_the_donor_is_owned(self, rules):
        games = [candidate("Pokemon Snap (USA)", save="flash128k")]
        held = inventory.Inventory(owned=frozenset({"flashram"}), recorded=True)

        result = inventory.shopping_list(games, held, rules)

        assert result.blocked == ()

    def test_a_title_too_large_stays_blocked_whatever_is_owned(self, rules):
        games = [candidate("Conker's Bad Fur Day (USA)", mib=64)]
        held = inventory.Inventory(
            owned=frozenset({"boot", "flashram", "eeprom16k"}), recorded=True
        )

        result = inventory.shopping_list(games, held, rules)

        assert "Conker's Bad Fur Day (USA)" in result.cartridge_only

    def test_names_a_title_that_will_not_boot_without_a_donor(self, rules):
        games = [candidate("Mario Party 3 (USA)", save="eeprom2k")]

        result = inventory.shopping_list(games, inventory.Inventory(), rules)

        assert "Mario Party 3 (USA)" in result.will_not_boot

    def test_the_one_save_per_cartridge_rule_is_surfaced(self, rules):
        games = [candidate("Pokemon Snap (USA)", save="flash128k")]

        result = inventory.shopping_list(games, inventory.Inventory(), rules)

        assert result.one_save_per_cartridge is True


class TestPersistence:
    def test_a_saved_inventory_reloads_identically(self, tmp_path):
        path = tmp_path / "inventory.json"
        held = inventory.Inventory(owned=frozenset({"boot", "flashram"}), recorded=True)

        inventory.save(held, path)

        assert inventory.load(path) == held

    def test_loading_an_absent_file_yields_an_unrecorded_inventory(self, tmp_path):
        held = inventory.load(tmp_path / "nothing.json")

        assert held.is_recorded is False
        assert held.owned == frozenset()

    def test_the_saved_form_is_readable_json(self, tmp_path):
        path = tmp_path / "inventory.json"

        inventory.save(inventory.Inventory(owned=frozenset({"boot"}), recorded=True), path)
        raw = json.loads(path.read_text(encoding="utf-8"))

        assert raw["owned"] == ["boot"]
        assert raw["recorded"] is True

    def test_a_malformed_file_is_reported_rather_than_crashing(self, tmp_path):
        path = tmp_path / "inventory.json"
        path.write_text("{not json", encoding="utf-8")

        with pytest.raises(inventory.InventoryError):
            inventory.load(path)
