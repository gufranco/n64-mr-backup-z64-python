import pytest

from z64kit import compat


def title(name, *, save="none", cic="6102", mib=8, patched=False, bios=False):
    return compat.Candidate(
        key=name,
        title=name,
        save=save,
        cic=cic,
        size=mib * 1024 * 1024,
        has_patch=patched,
        has_bios_crack=bios,
    )


@pytest.fixture(scope="module")
def rules():
    return compat.load_rules()


class TestRules:
    def test_the_packaged_rules_load(self, rules):
        assert rules.memory_mib == 32

    def test_names_the_extensions_the_unit_recognises(self, rules):
        assert "Z64" in rules.rom_extensions
        assert "APS" in rules.patch_extensions
        assert "RAM" in rules.aux_extensions

    def test_excludes_the_little_endian_extension(self, rules):
        assert "N64" not in rules.rom_extensions

    def test_knows_which_save_chips_are_emulated(self, rules):
        assert rules.is_emulated("eeprom512") is True
        assert rules.is_emulated("sram32k") is True
        assert rules.is_emulated("eeprom2k") is False
        assert rules.is_emulated("flash128k") is False

    def test_every_claim_carries_a_source(self, rules):
        assert rules.memory_source
        assert rules.donor_source

    def test_maps_an_unemulated_chip_to_the_donor_that_serves_it(self, rules):
        assert rules.donor_for("eeprom2k") == "eeprom16k"
        assert rules.donor_for("flash128k") == "flashram"

    def test_an_emulated_chip_needs_no_donor(self, rules):
        assert rules.donor_for("sram32k") is None


class TestClassify:
    def test_a_title_with_no_save_chip_needs_nothing(self, rules):
        assert compat.classify(title("Quake II (USA)"), rules).status == "no-save-data"

    def test_an_emulated_chip_saves_unaided(self, rules):
        result = compat.classify(title("Wave Race 64 (USA)", save="eeprom512"), rules)

        assert result.status == "native"
        assert result.blocked is False

    def test_an_unemulated_chip_without_help_is_blocked(self, rules):
        result = compat.classify(title("Pokemon Snap (USA)", save="flash128k"), rules)

        assert result.status == "needs-donor"
        assert result.blocked is True
        assert result.donor == "flashram"

    def test_a_patch_on_the_disk_resolves_it(self, rules):
        result = compat.classify(
            title("Donkey Kong 64 (USA)", save="eeprom2k", patched=True), rules
        )

        assert result.status == "patched"
        assert result.blocked is False

    def test_a_bios_crack_also_resolves_it(self, rules):
        result = compat.classify(title("Yoshi's Story (USA)", save="eeprom2k", bios=True), rules)

        assert result.status == "bios-crack"
        assert result.blocked is False

    def test_a_title_too_large_cannot_load_at_all(self, rules):
        result = compat.classify(title("Conker's Bad Fur Day (USA)", mib=64), rules)

        assert result.status == "too-large"
        assert result.blocked is True

    def test_being_too_large_outranks_every_save_consideration(self, rules):
        result = compat.classify(
            title("Resident Evil 2 (USA)", save="flash128k", mib=64, patched=True), rules
        )

        assert result.status == "too-large"

    def test_a_title_at_the_memory_limit_still_loads(self, rules):
        result = compat.classify(title("Perfect Dark (USA)", mib=32), rules)

        assert result.status != "too-large"

    def test_a_non_default_boot_chip_is_reported(self, rules):
        result = compat.classify(title("F-Zero X (USA)", cic="6106"), rules)

        assert result.boot_chip_action

    def test_the_default_boot_chip_needs_no_action(self, rules):
        result = compat.classify(title("Super Mario 64 (USA)", cic="6102"), rules)

        assert result.boot_chip_action == ""

    def test_the_ninety_nine_percent_chip_warns_about_country_fix(self, rules):
        result = compat.classify(title("Perfect Dark (USA)", cic="6105"), rules)

        assert "Country Fix" in result.boot_chip_action

    def test_a_title_that_will_not_boot_without_a_donor_is_named(self, rules):
        result = compat.classify(title("Mario Party 3 (USA)", save="eeprom2k"), rules)

        assert result.will_not_boot is True

    def test_most_titles_boot_with_a_standard_cartridge(self, rules):
        result = compat.classify(title("Pokemon Snap (USA)", save="flash128k"), rules)

        assert result.will_not_boot is False


class TestSummarise:
    def test_counts_each_status(self, rules):
        candidates = [
            title("A", save="eeprom512"),
            title("B", save="flash128k"),
            title("C", save="eeprom2k", patched=True),
        ]

        summary = compat.summarise(candidates, rules)

        assert summary.counts["native"] == 1
        assert summary.counts["needs-donor"] == 1
        assert summary.counts["patched"] == 1

    def test_lists_the_donors_that_would_unlock_blocked_titles(self, rules):
        candidates = [
            title("Pokemon Snap (USA)", save="flash128k"),
            title("Perfect Dark (USA)", save="eeprom2k"),
        ]

        summary = compat.summarise(candidates, rules)

        assert set(summary.donors_needed) == {"flashram", "eeprom16k"}

    def test_reports_nothing_needed_when_everything_saves(self, rules):
        summary = compat.summarise([title("A", save="sram32k")], rules)

        assert summary.donors_needed == ()

    def test_counts_titles_needing_a_boot_chip_change(self, rules):
        candidates = [title("A", cic="6103"), title("B", cic="6102")]

        summary = compat.summarise(candidates, rules)

        assert summary.non_default_boot_chip == 1

    def test_an_empty_collection_summarises_without_failing(self, rules):
        summary = compat.summarise([], rules)

        assert summary.counts == {}
        assert summary.donors_needed == ()
