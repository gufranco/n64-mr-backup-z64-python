"""Assigning games to disks.

Every N64 ROM is a whole multiple of 4 MiB, and the smallest one is 4 MiB. That
single fact decides the whole problem. A Zip 100 FAT16 volume holds 100,433,408
usable bytes, which is 95.78 MiB, but only 23 whole 4 MiB items fit in it, so the
effective capacity is 92 MiB. Three 32 MiB ROMs would need 100,663,296 bytes,
exactly the raw disk, leaving nothing for the MBR, the FATs or the directory, so
two large ROMs per disk is a hard ceiling rather than a tuning choice.

Because both the items and the capacity quantise to the same grain, the counting
bound over whole units is tight rather than optimistic, and first fit decreasing
reaches it for realistic collections. `plan` returns the bound alongside the
layout so a caller can assert optimality instead of trusting it.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

GRAIN = 4 * 1024 * 1024


class DoesNotFitError(ValueError):
    """Raised when a single item is larger than an entire disk."""


@dataclass(frozen=True)
class Item:
    key: str
    size: int


@dataclass(frozen=True)
class Plan:
    disks: tuple[tuple[Item, ...], ...]
    lower_bound: int

    @property
    def disk_count(self) -> int:
        return len(self.disks)

    @property
    def optimal(self) -> bool:
        return self.disk_count == self.lower_bound


def units_for(size_bytes: int) -> int:
    """Whole 4 MiB units an item consumes, rounded up."""
    return ceil(size_bytes / GRAIN)


def units_for_capacity(capacity_bytes: int) -> int:
    """Whole 4 MiB units a disk can hold, rounded down."""
    return capacity_bytes // GRAIN


def lower_bound(items: list[Item], capacity_bytes: int) -> int:
    per_disk = units_for_capacity(capacity_bytes)
    if per_disk <= 0:
        raise DoesNotFitError("a disk of this capacity holds nothing")
    total = sum(units_for(i.size) for i in items)
    return ceil(total / per_disk)


def pack(items: list[Item], capacity_bytes: int) -> list[list[Item]]:
    per_disk = units_for_capacity(capacity_bytes)
    ordered = sorted(items, key=lambda i: (-i.size, i.key))

    disks: list[list[Item]] = []
    used: list[int] = []
    for entry in ordered:
        need = units_for(entry.size)
        if need > per_disk:
            raise DoesNotFitError(f"{entry.key} needs {need} units but a disk holds {per_disk}")
        for index, taken in enumerate(used):
            if taken + need <= per_disk:
                disks[index].append(entry)
                used[index] = taken + need
                break
        else:
            disks.append([entry])
            used.append(need)
    return disks


def plan(items: list[Item], capacity_bytes: int) -> Plan:
    disks = pack(items, capacity_bytes)
    return Plan(
        disks=tuple(tuple(d) for d in disks),
        lower_bound=lower_bound(items, capacity_bytes),
    )
