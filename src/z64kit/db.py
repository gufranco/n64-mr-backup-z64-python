"""The save-type and boot-chip database, fetched rather than bundled.

Which save chip a cartridge carries cannot be read from the ROM. It is a
property of the board, so it has to come from a catalogue built by people who
dumped the hardware. The catalogue this module reads is licensed GPL-3.0, and
this package is MIT, so it is downloaded on first use and cached rather than
shipped inside the wheel. That keeps the licence of the code unentangled and
means the distribution carries no third-party data at all.

Two indexes are built. An MD5 of the whole ROM gives an exact answer. A game-code
pattern with underscores as wildcards gives a family answer, used when the exact
dump is not catalogued, and the most specific pattern wins.
"""

from __future__ import annotations

import hashlib
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

SOURCE_URL = "https://raw.githubusercontent.com/MiSTer-devel/N64_ROM_Database/main/N64-database.txt"
SOURCE_LICENCE = "GPL-3.0"
SOURCE_NAME = "MiSTer N64 ROM Database"

CACHE_FILENAME = "N64-database.txt"
FETCH_TIMEOUT_SECONDS = 60

SAVE_TAGS = ("eeprom512", "eeprom2k", "sram32k", "sram96k", "flash128k")
ACCESSORY_TAGS = ("cpak", "rpak", "tpak", "rtc")

_MD5_LINE = re.compile(r"^([0-9a-fA-F]{32})\s+(\S+)(?:\s*#\s*(.*))?$")
_ID_LINE = re.compile(r"^ID:(\S+)\s+(\S+)(?:\s*#\s*(.*))?$")


class DatabaseMissingError(FileNotFoundError):
    """Raised when the catalogue has not been downloaded yet."""


@dataclass(frozen=True)
class Entry:
    save: str = "none"
    cic: str = ""
    name: str = ""
    accessories: tuple[str, ...] = ()
    region: str = ""


@dataclass
class Database:
    by_md5: dict[str, Entry] = field(default_factory=dict)
    id_patterns: dict[str, Entry] = field(default_factory=dict)

    def lookup_by_code(self, game_code: str) -> Entry | None:
        """Resolve from the game code alone, reading no ROM bytes.

        The exact-dump index needs an MD5 of the whole file, and the caller that
        wants a save type for every game in a collection has already read each one
        once. Charging a second full pass for a value the code pattern resolves is
        not worth the precision.
        """
        if len(game_code) < 4:
            return None
        best: tuple[int, Entry] | None = None
        for pattern, entry in self.id_patterns.items():
            if not _matches(pattern, game_code):
                continue
            weight = sum(1 for c in pattern if c != "_")
            if best is None or weight > best[0]:
                best = (weight, entry)
        return best[1] if best else None

    def lookup(self, rom: bytes, game_code: str) -> Entry | None:
        exact = self.by_md5.get(hashlib.md5(rom).hexdigest())
        if exact is not None:
            return exact
        return self.lookup_by_code(game_code)


def _matches(pattern: str, code: str) -> bool:
    padded = code.ljust(len(pattern), "_")
    return all(p == "_" or p == c for p, c in zip(pattern, padded, strict=False))


def _entry_from_tags(tags: str, name: str) -> Entry:
    parts = tags.split("|")
    save = next((t for t in parts if t in SAVE_TAGS), "none")
    cic = next((t[3:] for t in parts if t.startswith("cic")), "")
    region = next((t for t in parts if t in ("ntsc", "pal")), "")
    return Entry(
        save=save,
        cic=cic,
        name=name.strip(),
        accessories=tuple(t for t in parts if t in ACCESSORY_TAGS),
        region=region,
    )


def parse(text: str) -> Database:
    out = Database()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        found = _ID_LINE.match(line)
        if found:
            out.id_patterns[found.group(1)] = _entry_from_tags(found.group(2), found.group(3) or "")
            continue
        found = _MD5_LINE.match(line)
        if found:
            out.by_md5[found.group(1).lower()] = _entry_from_tags(
                found.group(2), found.group(3) or ""
            )
    return out


def load(path: Path | str) -> Database:
    return parse(Path(path).read_text(encoding="utf-8", errors="replace"))


def cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    root = Path(base) if base else Path.home() / ".cache"
    return root / "z64kit" / CACHE_FILENAME


def available() -> bool:
    return cache_path().exists()


def load_default() -> Database:
    target = cache_path()
    if not target.exists():
        raise DatabaseMissingError(
            f"the {SOURCE_NAME} is not cached yet. Run `z64kit db-update` to fetch it, "
            f"or pass a local copy. It is {SOURCE_LICENCE} licensed and is therefore "
            "downloaded rather than shipped with this package."
        )
    return load(target)


def update(url: str = SOURCE_URL) -> Path:
    """Download the catalogue and cache it. Network access happens only here."""
    target = cache_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "z64kit"})
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
        payload = response.read()
    target.write_bytes(payload)
    return target
