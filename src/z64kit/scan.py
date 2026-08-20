"""Walking a folder and working out what is actually in it.

Files are identified by content. A dump whose extension disagrees with its magic
word is reported rather than trusted, because that mismatch is silent on a
desktop and fatal on the hardware.

Two folder shapes are supported without a flag. A flat folder of ROMs is what a
new user has, and the layout is computed for them. A folder holding one
subfolder per disk is what someone who has already curated their collection has,
and that arrangement is preserved. Detecting which is present costs nothing and
serves both.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from .compat import load_rules
from .rom import checksum, header

DEFAULT_DISK_PREFIX = "Zip Disk"


@dataclass(frozen=True)
class Game:
    path: str
    filename: str
    disk: str | None
    size: int
    extension: str
    true_extension: str
    byte_order: str
    internal_name: str
    cart_id: str
    region: str
    region_code: str
    version: int
    crc1: str
    crc2: str
    game_code: str
    cic: str
    checksum_valid: bool
    sha256: str
    identity_key: bytes

    @property
    def extension_mismatch(self) -> bool:
        return self.extension.lower() != self.true_extension.lower()

    @property
    def stem(self) -> str:
        return self.filename.rsplit(".", 1)[0]


@dataclass(frozen=True)
class Companion:
    path: str
    filename: str
    disk: str | None
    stem: str
    extension: str
    size: int
    sha256: str


@dataclass(frozen=True)
class Skipped:
    path: str
    reason: str


@dataclass(frozen=True)
class Collection:
    root: str
    games: tuple[Game, ...] = ()
    companions: tuple[Companion, ...] = ()
    skipped: tuple[Skipped, ...] = ()
    disk_names: tuple[str, ...] = ()
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_curated(self) -> bool:
        return bool(self.disk_names)

    @property
    def total_bytes(self) -> int:
        return sum(g.size for g in self.games)

    def companions_for(self, game: Game) -> tuple[Companion, ...]:
        return tuple(c for c in self.companions if c.stem == game.stem and c.disk == game.disk)


def _read_game(path: Path, disk: str | None, verify_checksum: bool) -> Game | tuple[None, str]:
    data = path.read_bytes()
    info = header.parse(data)
    if info is None:
        return None, "no recognisable N64 header"
    valid, cic = checksum.verify(data) if verify_checksum else (False, None)
    return Game(
        path=str(path),
        filename=path.name,
        disk=disk,
        size=len(data),
        extension=path.suffix.lstrip(".").upper(),
        true_extension=info.true_extension.upper(),
        byte_order=info.byte_order,
        internal_name=info.internal_name,
        cart_id=info.cart_id,
        region=info.region,
        region_code=info.region_code,
        version=info.version,
        crc1=info.crc1,
        crc2=info.crc2,
        game_code=info.game_code,
        cic=cic or "unknown",
        checksum_valid=valid,
        sha256=hashlib.sha256(data).hexdigest(),
        identity_key=header.identity_key(data) or b"",
    )


def scan(
    root: Path | str,
    *,
    disk_prefix: str = DEFAULT_DISK_PREFIX,
    verify_checksum: bool = True,
) -> Collection:
    base = Path(root)
    if not base.is_dir():
        raise FileNotFoundError(f"{base} is not a directory")

    rules = load_rules()
    disks = sorted(
        p.name
        for p in base.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name.startswith(disk_prefix)
    )

    sources: list[tuple[Path, str | None]] = []
    if disks:
        for name in disks:
            for path in sorted((base / name).iterdir()):
                sources.append((path, name))
    else:
        for path in sorted(base.iterdir()):
            sources.append((path, None))

    games: list[Game] = []
    companions: list[Companion] = []
    skipped: list[Skipped] = []
    warnings: list[str] = []

    for path, disk in sources:
        if not path.is_file() or path.name.startswith("."):
            if path.is_file():
                skipped.append(Skipped(str(path), "hidden file"))
            continue

        extension = path.suffix.lstrip(".").upper()

        if extension in rules.rom_extensions:
            result = _read_game(path, disk, verify_checksum)
            if isinstance(result, tuple):
                skipped.append(Skipped(str(path), result[1]))
                continue
            games.append(result)
            if result.extension_mismatch:
                warnings.append(
                    f"{result.filename} is {result.byte_order} but named "
                    f".{result.extension.lower()}, it will be stored as "
                    f".{result.true_extension}"
                )
            if result.true_extension in rules.unsupported_rom_extensions:
                warnings.append(
                    f"{result.filename} is little endian, which the unit does not list, "
                    "convert it to big endian"
                )
            if not result.checksum_valid and verify_checksum:
                warnings.append(
                    f"{result.filename} carries a checksum matching no known boot chip, "
                    "so the dump may be damaged"
                )
        elif extension in rules.patch_extensions or extension in rules.aux_extensions:
            data = path.read_bytes()
            companions.append(
                Companion(
                    path=str(path),
                    filename=path.name,
                    disk=disk,
                    stem=path.stem,
                    extension=extension,
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
        else:
            skipped.append(
                Skipped(str(path), f"extension .{extension.lower()} is not one the unit reads")
            )

    return Collection(
        root=str(base),
        games=tuple(games),
        companions=tuple(companions),
        skipped=tuple(skipped),
        disk_names=tuple(disks),
        warnings=tuple(warnings),
    )
