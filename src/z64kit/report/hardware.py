"""The printable hardware shopping list.

The catalogue says what each game needs as it goes. This answers the question
somebody asks before spending money: which cartridges do I have to buy, what does
each one unlock, and what stays impossible whatever I buy.

Nothing here knows what the reader owns unless they have said so. An unrecorded
inventory produces a document that lists what the collection demands and claims
nothing about what is missing, because a gap is only a gap relative to a shelf
this project cannot see.
"""

from __future__ import annotations

from ..compat import Rules
from ..inventory import Inventory, ShoppingList
from . import latex

TITLE = "Hardware you need"


def _summary(result: ShoppingList, generated: str) -> str:
    outstanding = [item for item in result.items if item.outstanding]
    return latex.key_values(
        [
            ("Cartridges still needed", str(len(outstanding))),
            ("Titles they unlock", str(sum(item.unlocks for item in outstanding))),
            ("Cannot load at all", str(len(result.cartridge_only))),
            ("Generated", generated),
        ]
    )


def build(
    result: ShoppingList,
    *,
    rules: Rules,
    held: Inventory,
    generated: str,
) -> str:
    """Render the shopping list as a LaTeX document."""
    body: list[str] = [latex.section("Summary"), _summary(result, generated)]

    if not held.is_recorded:
        body.append(
            latex.note(
                "No hardware inventory has been recorded, so this document lists what "
                "the collection demands rather than what is missing. Run "
                "`z64kit inventory --ask` to record which cartridges you own, and the "
                "outstanding list below will shrink to the real gaps."
            )
        )

    outstanding = [item for item in result.items if item.outstanding]
    if outstanding:
        body.append(latex.section("Cartridges to buy"))
        body.append(
            latex.longtable(
                ["Cartridge", "Unlocks", "For example"],
                [
                    [item.label, f"{item.unlocks} titles", item.reference or ""]
                    for item in outstanding
                ],
                widths=["55mm", "25mm", "70mm"],
            )
        )
        for item in outstanding:
            if not item.titles:
                continue
            body.append(latex.section(f"What a {item.label} unlocks"))
            body.append(
                latex.longtable(
                    ["Title"],
                    [[title] for title in sorted(item.titles)],
                    widths=["150mm"],
                )
            )

    owned = [item for item in result.items if not item.outstanding]
    if owned:
        body.append(latex.section("Already have"))
        body.append(
            latex.longtable(
                ["Cartridge", "Covers"],
                [[item.label, f"{item.unlocks} titles"] for item in owned],
                widths=["70mm", "80mm"],
            )
        )

    if result.boot_requirement:
        body.append(latex.section("Booting at all"))
        body.append(latex.note(result.boot_requirement))

    if result.one_save_per_cartridge:
        body.append(
            latex.note(
                "One cartridge holds one game save. Two titles that both need the same "
                "kind of donor can share a cartridge only by overwriting each other, so "
                "playing them in parallel needs a second copy."
            )
        )

    if result.cartridge_only:
        body.append(latex.section("Cannot be loaded at all"))
        body.append(
            latex.note(
                f"The unit holds {rules.memory_mib} MiB, so these titles cannot be loaded "
                "from a disk whatever cartridge is in the slot. They need the original."
            )
        )
        body.append(
            latex.longtable(
                ["Title"],
                [[title] for title in sorted(result.cartridge_only)],
                widths=["150mm"],
            )
        )

    if result.will_not_boot:
        body.append(latex.section("Will not start without a donor"))
        body.append(
            latex.longtable(
                ["Title"],
                [[title] for title in sorted(result.will_not_boot)],
                widths=["150mm"],
            )
        )

    for warning in result.warnings:
        body.append(latex.note(warning))

    return latex.document(title=TITLE, subtitle=f"Generated {generated}", body="\n".join(body))
