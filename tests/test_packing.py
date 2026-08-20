import pytest

from z64kit import packing

MIB = 1024 * 1024
CAPACITY = 100_433_408


def item(name, mib):
    return packing.Item(key=name, size=mib * MIB)


class TestGranularity:
    def test_rounds_a_size_up_to_whole_units(self):
        assert packing.units_for(4 * MIB) == 1
        assert packing.units_for(4 * MIB + 1) == 2

    def test_a_rom_with_a_patch_beside_it_costs_an_extra_unit(self):
        assert packing.units_for(32 * MIB + 74_656) == 9

    def test_capacity_floors_because_a_partial_unit_holds_nothing(self):
        assert packing.units_for_capacity(CAPACITY) == 23

    def test_the_effective_capacity_is_less_than_the_raw_capacity(self):
        effective = packing.units_for_capacity(CAPACITY) * packing.GRAIN

        assert effective == 92 * MIB
        assert effective < CAPACITY


class TestLowerBound:
    def test_an_empty_collection_needs_no_disks(self):
        assert packing.lower_bound([], CAPACITY) == 0

    def test_one_small_item_needs_one_disk(self):
        assert packing.lower_bound([item("a", 4)], CAPACITY) == 1

    def test_two_large_items_fit_on_one_disk(self):
        assert packing.lower_bound([item("a", 32), item("b", 32)], CAPACITY) == 1

    def test_three_large_items_cannot_share_a_disk(self):
        assert packing.lower_bound([item(str(i), 32) for i in range(3)], CAPACITY) == 2

    def test_refuses_a_capacity_too_small_to_hold_anything(self):
        with pytest.raises(packing.DoesNotFitError, match="holds nothing"):
            packing.lower_bound([item("a", 4)], 1024)


class TestPack:
    def test_no_bin_exceeds_the_capacity(self):
        items = [item(str(i), 16) for i in range(20)]

        bins = packing.pack(items, CAPACITY)

        assert all(sum(x.size for x in b) <= CAPACITY for b in bins)

    def test_every_item_is_placed_exactly_once(self):
        items = [item(str(i), 12) for i in range(17)]

        bins = packing.pack(items, CAPACITY)
        placed = [x.key for b in bins for x in b]

        assert sorted(placed) == sorted(x.key for x in items)

    def test_the_layout_is_stable_across_runs(self):
        items = [item(str(i), 8) for i in range(30)]

        first = packing.pack(items, CAPACITY)
        second = packing.pack(items, CAPACITY)

        assert [[x.key for x in b] for b in first] == [[x.key for x in b] for b in second]

    def test_the_layout_does_not_depend_on_input_order(self):
        items = [item(str(i), 8) for i in range(30)]

        forward = packing.pack(items, CAPACITY)
        reverse = packing.pack(list(reversed(items)), CAPACITY)

        assert [[x.key for x in b] for b in forward] == [[x.key for x in b] for b in reverse]

    def test_large_items_are_placed_before_small_ones(self):
        items = [item("small", 4), item("large", 32)]

        bins = packing.pack(items, CAPACITY)

        assert bins[0][0].key == "large"

    def test_refuses_an_item_that_cannot_fit_any_disk(self):
        with pytest.raises(packing.DoesNotFitError, match="huge"):
            packing.pack([item("huge", 96)], CAPACITY)

    def test_an_empty_collection_produces_no_disks(self):
        assert packing.pack([], CAPACITY) == []


class TestOptimality:
    def test_reaches_the_lower_bound_for_a_realistic_distribution(self):
        sizes = [4] * 13 + [8] * 62 + [12] * 87 + [16] * 88 + [32] * 42
        items = [item(f"g{i}", mib) for i, mib in enumerate(sizes)]

        bins = packing.pack(items, CAPACITY)

        assert len(bins) == packing.lower_bound(items, CAPACITY)

    def test_that_distribution_needs_forty_eight_disks(self):
        sizes = [4] * 13 + [8] * 62 + [12] * 87 + [16] * 88 + [32] * 42
        items = [item(f"g{i}", mib) for i, mib in enumerate(sizes)]

        assert packing.lower_bound(items, CAPACITY) == 48

    def test_reports_the_bound_alongside_the_layout(self):
        items = [item(str(i), 16) for i in range(10)]

        result = packing.plan(items, CAPACITY)

        assert result.disk_count == len(result.disks)
        assert result.lower_bound <= result.disk_count
        assert result.optimal is (result.disk_count == result.lower_bound)
