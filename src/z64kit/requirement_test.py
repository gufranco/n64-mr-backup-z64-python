"""Tests for the plain-language sentence that says what a game still needs.

The reader is holding a printed catalogue and a shopping list, not a debugger. A
flag character tells them something is wrong; only a sentence tells them what to
buy or which cartridge to put in the slot.
"""

from z64kit import compat


def rules():
    return compat.load_rules()


def verdict(**kw):
    base = {
        "key": "GAME.Z64",
        "title": "Some Game (USA)",
        "status": compat.STATUS_NEEDS_DONOR,
        "blocked": True,
    }
    base.update(kw)
    return compat.Verdict(**base)


class TestRequirementSentence:
    def test_a_game_needing_nothing_says_nothing(self):
        line = compat.requirement_for(verdict(status="ok", blocked=False), rules())

        assert line == ""

    def test_a_donor_need_names_the_hardware(self):
        line = compat.requirement_for(verdict(donor="eeprom16k"), rules())

        assert "16 Kbit EEPROM" in line

    def test_a_donor_need_names_an_example_cartridge(self):
        line = compat.requirement_for(verdict(donor="eeprom16k"), rules())

        assert "Star Wars Episode I Racer" in line

    def test_a_flashram_need_names_its_own_example(self):
        line = compat.requirement_for(verdict(donor="flashram"), rules())

        assert "Command & Conquer" in line

    def test_says_the_save_goes_to_the_inserted_cartridge(self):
        line = compat.requirement_for(verdict(donor="eeprom16k"), rules())

        assert "save" in line.lower()

    def test_a_boot_chip_need_is_stated(self):
        line = compat.requirement_for(
            verdict(status="ok", blocked=False, boot_chip_action="swap to a 6105 cartridge"),
            rules(),
        )

        assert "6105" in line

    def test_a_game_that_will_not_boot_says_so_first(self):
        line = compat.requirement_for(verdict(donor="eeprom16k", will_not_boot=True), rules())

        assert line.lower().startswith("will not boot")

    def test_an_oversized_game_says_it_cannot_be_loaded(self):
        line = compat.requirement_for(
            verdict(status=compat.STATUS_TOO_LARGE, note="32 MiB limit"), rules()
        )

        assert "too large" in line.lower()

    def test_both_a_donor_and_a_boot_chip_are_reported_together(self):
        line = compat.requirement_for(
            verdict(donor="flashram", boot_chip_action="swap to a 6103 cartridge"), rules()
        )

        assert "FlashRAM" in line
        assert "6103" in line

    def test_the_sentence_is_one_line(self):
        line = compat.requirement_for(verdict(donor="eeprom16k"), rules())

        assert "\n" not in line

    def test_an_unknown_donor_key_does_not_crash(self):
        line = compat.requirement_for(verdict(donor="not-a-real-chip"), rules())

        assert "not-a-real-chip" in line


class TestDonorAlsoSolvingTheBootChip:
    def test_names_a_cartridge_that_solves_both_when_one_exists(self):
        line = compat.requirement_for(
            verdict(donor="eeprom16k", boot_chip_action="swap to a 6102 cartridge"), rules()
        )

        assert "Mario Tennis" in line or "Ridge Racer 64" in line

    def test_says_one_cartridge_covers_both(self):
        line = compat.requirement_for(
            verdict(donor="eeprom16k", boot_chip_action="swap to a 6102 cartridge"), rules()
        )

        assert "both" in line.lower()


class TestSentenceCasing:
    def test_every_sentence_after_the_first_starts_capitalised(self):
        line = compat.requirement_for(verdict(donor="flashram", will_not_boot=True), rules())

        for sentence in line.split(". "):
            assert sentence[:1] == sentence[:1].upper(), line

    def test_the_oversized_note_is_capitalised(self):
        line = compat.requirement_for(
            verdict(status=compat.STATUS_TOO_LARGE, note="the unit holds 32 MiB."), rules()
        )

        assert "The unit holds" in line

    def test_a_boot_chip_only_sentence_is_capitalised(self):
        line = compat.requirement_for(
            verdict(status="ok", blocked=False, boot_chip_action="swap to a 6105 cartridge"),
            rules(),
        )

        assert line.startswith("Swap")

    def test_no_double_full_stop_survives(self):
        line = compat.requirement_for(
            verdict(status=compat.STATUS_TOO_LARGE, note="the unit holds 32 MiB."), rules()
        )

        assert ".." not in line
