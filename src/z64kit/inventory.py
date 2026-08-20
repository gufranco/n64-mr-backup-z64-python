"""What hardware the user owns, and what follows from that.

The unit needs a cartridge in the slot to boot, and for two save chips it cannot
emulate it needs a cartridge carrying the right chip, because the save is written
to that cartridge rather than to the disk. Which titles work therefore depends on
what the person actually has on their shelf.

Nothing here is assumed. An unrecorded inventory owns nothing and every report
built from it speaks in conditional terms. Once the user answers, the same
functions turn those answers into a shopping list that names the titles each
purchase would unlock, so the recommendation carries its own reasoning.

Questions are only asked about hardware this collection needs. A collection with
no FlashRAM titles is never asked about a FlashRAM donor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .compat import STATUS_NEEDS_DONOR, STATUS_TOO_LARGE, Candidate, Rules, classify

BOOT_KEY = "boot"


class InventoryError(ValueError):
    """Raised when a stored inventory cannot be read."""


@dataclass(frozen=True)
class Inventory:
    owned: frozenset[str] = frozenset()
    recorded: bool = False

    def owns(self, key: str) -> bool:
        return key in self.owned

    @property
    def is_recorded(self) -> bool:
        return self.recorded


@dataclass(frozen=True)
class Question:
    key: str
    label: str
    prompt: str
    examples: tuple[str, ...]
    unlocks: int
    titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShoppingItem:
    key: str
    label: str
    reference: str
    outstanding: bool
    unlocks: int
    titles: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class ShoppingList:
    items: tuple[ShoppingItem, ...] = ()
    blocked: tuple[str, ...] = ()
    cartridge_only: tuple[str, ...] = ()
    will_not_boot: tuple[str, ...] = ()
    one_save_per_cartridge: bool = False
    boot_requirement: str = ""
    donor_source: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)


def _donor_demand(games: list[Candidate], rules: Rules) -> dict[str, list[str]]:
    demand: dict[str, list[str]] = {}
    for game in games:
        verdict = classify(game, rules)
        if verdict.status == STATUS_TOO_LARGE:
            continue
        needs_it = verdict.status == STATUS_NEEDS_DONOR or verdict.will_not_boot
        if verdict.donor and needs_it:
            demand.setdefault(verdict.donor, []).append(game.title)
    return demand


def questions(games: list[Candidate], rules: Rules) -> tuple[Question, ...]:
    out = [
        Question(
            key=BOOT_KEY,
            label="Boot cartridge",
            prompt=(
                "Do you have a cartridge with a 4 KB EEPROM save chip and a 6102 or "
                "7101 security chip? One must be in the slot for anything to boot."
            ),
            examples=tuple(rules.boot_cartridge["examples"]),
            unlocks=len(games),
        )
    ]
    for donor, titles in sorted(_donor_demand(games, rules).items()):
        out.append(
            Question(
                key=donor,
                label=rules.donor_label(donor),
                prompt=(
                    f"Do you have a cartridge carrying {rules.donor_label(donor)}? "
                    "Without one, these titles cannot save."
                ),
                examples=tuple(rules.donors.get(donor, {}).get("also_carrying_6102", ())),
                unlocks=len(titles),
                titles=tuple(sorted(titles)),
            )
        )
    return tuple(out)


def shopping_list(games: list[Candidate], held: Inventory, rules: Rules) -> ShoppingList:
    demand = _donor_demand(games, rules)
    verdicts = [classify(g, rules) for g in games]

    items = [
        ShoppingItem(
            key=BOOT_KEY,
            label="Boot cartridge",
            reference=rules.boot_cartridge["examples"][0],
            outstanding=not held.owns(BOOT_KEY),
            unlocks=len(games),
            note=rules.boot_cartridge["note"],
        )
    ]
    for donor, titles in sorted(demand.items()):
        items.append(
            ShoppingItem(
                key=donor,
                label=rules.donor_label(donor),
                reference=rules.donor_reference(donor),
                outstanding=not held.owns(donor),
                unlocks=len(titles),
                titles=tuple(sorted(titles)),
            )
        )

    blocked = tuple(
        sorted(
            v.title
            for v in verdicts
            if v.status == STATUS_NEEDS_DONOR and not held.owns(v.donor or "")
        )
    )
    cartridge_only = tuple(sorted(v.title for v in verdicts if v.status == STATUS_TOO_LARGE))
    no_boot = tuple(
        sorted(v.title for v in verdicts if v.will_not_boot and not held.owns(v.donor or ""))
    )

    warnings = []
    if not held.is_recorded:
        warnings.append(
            "No inventory has been recorded, so every requirement below is stated "
            "as a condition rather than as something outstanding."
        )

    return ShoppingList(
        items=tuple(items),
        blocked=blocked,
        cartridge_only=cartridge_only,
        will_not_boot=no_boot,
        one_save_per_cartridge=bool(rules.one_save_per_cartridge["rule"]),
        boot_requirement=rules.boot_cartridge["requirement"],
        donor_source=rules.donor_source,
        warnings=tuple(warnings),
    )


def save(held: Inventory, path: Path | str) -> None:
    payload = {"schema": 1, "owned": sorted(held.owned), "recorded": held.recorded}
    Path(path).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")


def load(path: Path | str) -> Inventory:
    target = Path(path)
    if not target.exists():
        return Inventory()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InventoryError(f"{target} is not readable JSON: {exc}") from exc
    return Inventory(
        owned=frozenset(raw.get("owned", ())),
        recorded=bool(raw.get("recorded", False)),
    )
