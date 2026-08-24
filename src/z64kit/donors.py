"""Which cartridges carry a given save chip, for a reader about to buy one.

The shopping list answers what is needed and names one example. This answers the
question that follows it: what else would do. A save chip is a property of the
board, so the only way to know is a catalogue built by people who dumped the
hardware, which is what the save-type database is.

The code is carried alongside the title because it is printed on the label. Two
cartridges can share a name and not a board, and the code is what tells them
apart on a shelf or in a listing.

The catalogue holds prototypes, kiosk units and romhacks next to retail releases
and marks none of them as such. So this returns what the catalogue holds, and
the document that prints it says so rather than calling the list purchasable.
"""

from __future__ import annotations

from dataclasses import dataclass

from .db import Database

WILDCARD = "_"
UNKNOWN = "?"


@dataclass(frozen=True)
class Donor:
    """A catalogued cartridge carrying the wanted save chip."""

    title: str
    code: str


def _code(pattern: str) -> str:
    """The pattern as an identifier a reader can compare against a label.

    Trailing wildcards carry nothing and go. A wildcard anywhere else means that
    position genuinely varies, usually the media letter or the region, so it is
    shown as a question mark. Passing the underscore through would read as part
    of the code, which is the one thing the column must not say.
    """
    return pattern.rstrip(WILDCARD).replace(WILDCARD, UNKNOWN)


def catalogued(database: Database, save_tag: str) -> tuple[Donor, ...]:
    """Every catalogued cartridge carrying `save_tag`, one row per title.

    A title appears once even when the catalogue lists it per region, because a
    reader buying one cartridge does not need the same name three times. The
    shortest code wins, since that is the part the regional variants share.
    """
    best: dict[str, str] = {}
    for pattern, entry in database.id_patterns.items():
        if entry.save != save_tag or not entry.name:
            continue
        code = _code(pattern)
        current = best.get(entry.name)
        if current is None or len(code) < len(current):
            best[entry.name] = code
    return tuple(Donor(title=name, code=best[name]) for name in sorted(best))
