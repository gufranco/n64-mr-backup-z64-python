"""Tests for the printable hardware shopping list.

The catalogue says what each game needs in passing. This document answers the
question somebody asks before spending money: which cartridges do I have to buy,
what does each one unlock, and what stays impossible whatever I buy.
"""

from z64kit import compat, inventory
from z64kit.report import hardware


def candidates():
    return [
        compat.Candidate(key="dk64.z64", title="Donkey Kong 64 (USA)", save="eeprom2k"),
        compat.Candidate(key="cc.z64", title="Command & Conquer (USA)", save="flash128k"),
        compat.Candidate(key="mario.z64", title="Super Mario 64 (USA)", save="eeprom512"),
    ]


def build(held=None, games=None):
    rules = compat.load_rules()
    games = candidates() if games is None else games
    held = inventory.Inventory() if held is None else held
    return hardware.build(
        inventory.shopping_list(games, held, rules),
        rules=rules,
        held=held,
        generated="2026-08-20",
    )


class TestDocument:
    def test_it_has_a_title(self):
        assert "Hardware" in build()

    def test_it_names_the_generated_date(self):
        assert "2026-08-20" in build()

    def test_it_lists_a_donor_that_is_outstanding(self):
        assert "16 Kbit EEPROM" in build()

    def test_it_names_an_example_cartridge_to_buy(self):
        assert "Star Wars Episode I Racer" in build()

    def test_it_says_how_many_games_a_donor_unlocks(self):
        assert "unlocks" in build().lower()

    def test_it_states_the_boot_cartridge_requirement(self):
        assert "boot" in build().lower()

    def test_it_says_one_cartridge_holds_one_save(self):
        assert "one save" in build().lower() or "one game" in build().lower()

    def test_it_is_a_latex_document(self):
        doc = build()

        assert "\\section*{" in doc

    def test_it_escapes_a_title_with_latex_characters(self):
        games = [compat.Candidate(key="x.z64", title="Tom & Jerry 100% (USA)", save="flash128k")]

        doc = build(games=games)

        assert "100\\%" in doc or "\\&" in doc

    def test_an_empty_collection_still_produces_a_document(self):
        doc = build(games=[])

        assert "\\section*{" in doc

    def test_it_is_deterministic(self):
        assert build() == build()


class TestOwnedCartridgesChangeIt:
    def test_an_unrecorded_inventory_says_so(self):
        doc = build()

        assert "No hardware inventory has been recorded" in doc

    def test_a_recorded_inventory_does_not_carry_that_warning(self):
        held = inventory.Inventory(owned=frozenset({"eeprom16k"}), recorded=True)

        doc = build(held=held)

        assert "No hardware inventory has been recorded" not in doc

    def test_an_owned_donor_is_reported_as_held_rather_than_outstanding(self):
        rules = compat.load_rules()
        held = inventory.Inventory(owned=frozenset({"eeprom16k"}), recorded=True)
        result = inventory.shopping_list(candidates(), held, rules)

        doc = hardware.build(result, rules=rules, held=held, generated="2026-08-20")

        assert "Already have" in doc or "held" in doc.lower()


class TestWhatStaysImpossible:
    def test_a_title_too_large_to_load_is_named(self):
        games = [
            compat.Candidate(
                key="big.z64", title="Huge Game (USA)", save="none", size=64 * 1024 * 1024
            )
        ]

        assert "Huge Game" in build(games=games)

    def test_the_reason_it_cannot_load_is_given(self):
        games = [
            compat.Candidate(
                key="big.z64", title="Huge Game (USA)", save="none", size=64 * 1024 * 1024
            )
        ]

        doc = build(games=games)

        assert "32" in doc


class TestRenderedToDisk:
    def test_it_writes_a_tex_file(self, tmp_path):
        from z64kit.report import render

        result = render.write(build(), tmp_path / "hardware.tex")

        assert result.tex_path.exists()

    def test_the_tex_it_writes_is_the_document(self, tmp_path):
        from z64kit.report import render

        render.write(build(), tmp_path / "hardware.tex")

        assert "Hardware" in (tmp_path / "hardware.tex").read_text(encoding="utf-8")


class TestEveryBranchOfTheDocument:
    def test_a_donor_with_no_named_titles_still_appears(self):
        rules = compat.load_rules()
        result = inventory.ShoppingList(
            items=(
                inventory.ShoppingItem(
                    key="flashram",
                    label="FlashRAM donor",
                    reference="Command & Conquer",
                    outstanding=True,
                    unlocks=3,
                    titles=(),
                ),
            )
        )

        doc = hardware.build(
            result, rules=rules, held=inventory.Inventory(), generated="2026-08-20"
        )

        assert "FlashRAM donor" in doc
        assert "What a FlashRAM donor unlocks" not in doc

    def test_a_title_that_will_not_boot_gets_its_own_section(self):
        rules = compat.load_rules()
        result = inventory.ShoppingList(will_not_boot=("Mario Party 3",))

        doc = hardware.build(
            result, rules=rules, held=inventory.Inventory(), generated="2026-08-20"
        )

        assert "Will not start without a donor" in doc
        assert "Mario Party 3" in doc

    def test_a_warning_reaches_the_document(self):
        rules = compat.load_rules()
        result = inventory.ShoppingList(warnings=("something worth saying",))

        doc = hardware.build(
            result, rules=rules, held=inventory.Inventory(), generated="2026-08-20"
        )

        assert "something worth saying" in doc

    def test_the_boot_requirement_gets_its_own_section(self):
        rules = compat.load_rules()
        result = inventory.ShoppingList(boot_requirement="a cartridge must be in the slot")

        doc = hardware.build(
            result, rules=rules, held=inventory.Inventory(), generated="2026-08-20"
        )

        assert "Booting at all" in doc
        assert "must be in the slot" in doc

    def test_the_one_save_per_cartridge_note_is_conditional(self):
        rules = compat.load_rules()
        without = hardware.build(
            inventory.ShoppingList(one_save_per_cartridge=False),
            rules=rules,
            held=inventory.Inventory(),
            generated="2026-08-20",
        )
        with_note = hardware.build(
            inventory.ShoppingList(one_save_per_cartridge=True),
            rules=rules,
            held=inventory.Inventory(),
            generated="2026-08-20",
        )

        assert "One cartridge holds one game save" in with_note
        assert "One cartridge holds one game save" not in without
