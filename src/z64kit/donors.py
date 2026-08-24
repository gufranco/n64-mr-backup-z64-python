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

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from .db import Database, matches

WILDCARD = "_"
UNKNOWN = "?"


@dataclass(frozen=True)
class Donor:
    """A catalogued cartridge carrying the wanted save chip."""

    title: str
    code: str


BRACKETED = re.compile(r"\s*\[[^\]]*\]")
PARENTHESISED = re.compile(r"\s*\([^)]*\)")
SUBTITLE = re.compile(r":\s+")


def clean_title(name: str) -> str:
    """The catalogue's name rewritten the way the rest of the report writes one.

    The report takes every other title from the collection's own files, which are
    No-Intro named. The catalogue is not: it puts a subtitle after a colon, keeps
    the Japanese title in brackets, and spells Pokemon with an accent. Two schemes
    in one document read as mistakes, and half of them are.

    Region and revision suffixes go for the same reason. A shopping list names a
    cartridge, and which revision of it turns up is not something a buyer picks.
    """
    without_alternates = BRACKETED.sub("", name)
    without_qualifiers = PARENTHESISED.sub("", without_alternates)
    dashed = SUBTITLE.sub(" - ", without_qualifiers)
    folded = unicodedata.normalize("NFKD", dashed).encode("ascii", "ignore").decode("ascii")
    return folded.strip()


def _code(pattern: str) -> str:
    """The pattern as an identifier a reader can compare against a label.

    Trailing wildcards carry nothing and go. A wildcard anywhere else means that
    position genuinely varies, usually the media letter or the region, so it is
    shown as a question mark. Passing the underscore through would read as part
    of the code, which is the one thing the column must not say.
    """
    return pattern.rstrip(WILDCARD).replace(WILDCARD, UNKNOWN)


def catalogued(
    database: Database, save_tag: str, owned: Mapping[str, str] | None = None
) -> tuple[Donor, ...]:
    """Every catalogued cartridge carrying `save_tag`, one row per title.

    A title appears once even when the catalogue lists it per region, because a
    reader buying one cartridge does not need the same name three times. The
    shortest code wins, since that is the part the regional variants share.

    `owned` maps a game code to the name the reader's own file carries. The
    catalogue abbreviates, calling Kirby 64 - The Crystal Shards just Kirby 64,
    so a No-Intro named file the reader already has is the better source. The
    link is the game code under the catalogue's own wildcard rule, never a
    resemblance between two titles.
    """
    preferred = _preferred(database, owned or {})
    best: dict[str, str] = {}
    for pattern, entry in database.id_patterns.items():
        if entry.save != save_tag or not entry.name:
            continue
        code = _code(pattern)
        title = preferred.get(pattern) or clean_title(entry.name)
        current = best.get(title)
        if current is None or len(code) < len(current):
            best[title] = code
    return tuple(Donor(title=title, code=best[title]) for title in sorted(best))


def _preferred(database: Database, owned: Mapping[str, str]) -> dict[str, str]:
    """Each catalogue pattern mapped to a collection name whose code satisfies it."""
    out: dict[str, str] = {}
    for pattern in database.id_patterns:
        for code, title in owned.items():
            if matches(pattern, code):
                out[pattern] = clean_title(title)
                break
    return out
