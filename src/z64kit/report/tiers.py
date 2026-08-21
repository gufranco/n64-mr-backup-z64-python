"""Quality tiers, which the collection states and this code never infers.

A game's quality is a judgement. Nothing here derives one, and nothing guesses
where a band ends, because a boundary invented by the tool would assert a ranking
the reader never made.

What a curated collection does carry is an order: the disks were filled best
first. A `tiers.json` beside the games names where each band closes, so disk 1
through 3 can read as one group and 4 through 8 as the next. Without that file
the document is exactly as it was.

    {"tiers": [
      {"name": "S", "label": "Masterpieces", "through_disk": 3},
      {"name": "A", "label": "Essential classics", "through_disk": 8}
    ]}

A malformed file is refused rather than skipped. Silently ignoring it would
produce a document with no tiers and no reason given, which reads as though the
collection had none.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

FILENAME = "tiers.json"
DISK_NUMBER = re.compile(r"(\d+)")


class TierFileError(ValueError):
    """The tiers file exists but cannot be used."""


@dataclass(frozen=True)
class Band:
    name: str
    label: str
    through_disk: int

    @property
    def heading(self) -> str:
        return f"{self.name}-tier: {self.label}" if self.label else f"{self.name}-tier"


def parse(payload: object) -> tuple[Band, ...]:
    if not isinstance(payload, dict):
        raise TierFileError(f"{FILENAME} must hold an object with a 'tiers' list")
    listed = payload.get("tiers")
    if not isinstance(listed, list):
        raise TierFileError(f"{FILENAME} must hold an object with a 'tiers' list")

    bands: list[Band] = []
    for entry in listed:
        if not isinstance(entry, dict):
            raise TierFileError(f"every tier in {FILENAME} must be an object")
        name = entry.get("name")
        through = entry.get("through_disk")
        if not isinstance(name, str) or not name:
            raise TierFileError(f"a tier in {FILENAME} has no name")
        if not isinstance(through, int):
            raise TierFileError(f"tier {name} in {FILENAME} has no through_disk")
        label = entry.get("label")
        bands.append(
            Band(
                name=name,
                label=label if isinstance(label, str) else "",
                through_disk=through,
            )
        )

    return tuple(sorted(bands, key=lambda b: b.through_disk))


def load(root: Path) -> tuple[Band, ...]:
    """The bands a collection declares, or nothing when it declares none."""
    candidate = Path(root) / FILENAME
    if not candidate.is_file():
        return ()
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TierFileError(f"{candidate} could not be read: {error}") from error
    return parse(payload)


def disk_number(disk: str) -> int | None:
    """The number in a disk name, so a band can be matched to it."""
    found = DISK_NUMBER.search(disk)
    return int(found.group(1)) if found else None


def band_for(number: int, bands: tuple[Band, ...]) -> Band | None:
    """The first band this disk still falls inside."""
    for band in bands:
        if number <= band.through_disk:
            return band
    return None
