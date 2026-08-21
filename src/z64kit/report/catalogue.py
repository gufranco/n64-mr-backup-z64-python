"""The disk catalogue: what is on every disk, and what each title needs.

A summary first, then the per disk listing. The status column is the point of the
document: it says whether a title saves unaided, saves because a patch sits
beside it on the disk, or cannot save without hardware the reader may not own.

Nothing here asserts anything about the reader. Until an inventory is recorded,
the document says so plainly rather than assuming a shelf it cannot see.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from pathlib import Path

from ..compat import Candidate, Rules, Verdict, classify, requirement_for
from ..inventory import Inventory
from ..scan import Game
from . import latex

STATUS_LABEL = {
    "native": "saves",
    "patched": "patched",
    "bios-crack": "BIOS fix",
    "needs-donor": "no save",
    "no-save-data": "no save data",
    "too-large": "will not load",
}

FLAG_LEGEND = (
    ("P", "a patch file sits beside it on the disk"),
    ("B", "the BIOS carries a crack for it"),
    ("!", "boots and plays but cannot save without a donor cartridge"),
    ("X", "larger than the unit's memory, so it cannot load at all"),
    ("+", "needs a companion save file to be present"),
    ("?", "the dump's checksum matches no known boot chip"),
)


VIDEO_UNREAD = "not read"


@dataclass(frozen=True)
class Video:
    """What a ROM's video configuration looks like, and what can be changed in it.

    `modes` is zero when no mode table could be proven present, which is what makes
    anti-aliasing unpatchable. `dither_requests` counts the places the ROM switches
    the dedither filter on at runtime; zero means it has no way to switch it on, so
    the filter is already off rather than unpatchable.
    """

    modes: int = 0
    antialiasing_on: int = 0
    divot_on: int = 0
    gamma_dither_on: int = 0
    dither_requests: int = 0
    checksum_valid: bool = True

    @property
    def aa_patchable(self) -> bool:
        return self.modes > 0 and self.antialiasing_on > 0 and self.checksum_valid

    @property
    def dither_patchable(self) -> bool:
        return self.dither_requests > 0 and self.checksum_valid

    @property
    def summary(self) -> str:
        if not self.checksum_valid:
            return "no boot chip"
        wanted = []
        if self.aa_patchable:
            wanted.append("AA")
        if self.dither_patchable:
            wanted.append("dedither")
        if wanted:
            return ", ".join(wanted)
        if self.modes == 0 and self.dither_requests == 0:
            return "unreachable"
        return "clean"


@dataclass(frozen=True)
class Row:
    disk: str
    title: str
    name83: str
    mib: int
    cic: str
    save: str
    status: str
    flags: str
    crc1: str
    requirement: str = ""
    video: Video | None = None


def flags_for(verdict: Verdict, game: Game, *, has_companion: bool) -> str:
    out = ""
    if verdict.status == "patched":
        out += "P"
    if verdict.status == "bios-crack":
        out += "B"
    if verdict.status == "needs-donor":
        out += "!"
    if verdict.status == "too-large":
        out += "X"
    if has_companion:
        out += "+"
    if not game.checksum_valid:
        out += "?"
    return out


def _summary(rows: list[Row], generated: str) -> str:
    counts = collections.Counter(r.status for r in rows)
    disks = sorted({r.disk for r in rows})
    total_mib = sum(r.mib for r in rows)
    helped = counts.get("patched", 0) + counts.get("bios-crack", 0)
    return latex.key_values(
        [
            ("Disks", str(len(disks))),
            ("Games", str(len(rows))),
            ("Total size", f"{total_mib / 1024:.2f} GiB"),
            ("Saves unaided", str(counts.get("native", 0))),
            ("Saves via a patch", str(helped)),
            ("Cannot save without hardware", str(counts.get("needs-donor", 0))),
            ("Cannot load at all", str(counts.get("too-large", 0))),
            ("Generated", generated),
        ]
    )


def _video_sections(rows: list[Row]) -> list[str]:
    """The video picture: what blurs, what can be cleared, and what cannot.

    Two settings, reported separately because they live in different places and
    fail for different reasons. Anti-aliasing is in the mode table, so a ROM with
    no provable table cannot have it changed. The dedither filter is switched on at
    runtime, so a ROM that never switches it on has it off already, which is a
    different thing from being unpatchable and is not reported as a gap.
    """
    known = [r for r in rows if r.video is not None]
    if not known:
        return []

    aa = [r for r in known if r.video is not None and r.video.aa_patchable]
    dither = [r for r in known if r.video is not None and r.video.dither_patchable]
    unreadable = [r for r in rows if r.video is None]
    blocked = [r for r in known if r.video is not None and not r.video.checksum_valid]

    body = [latex.section("Video")]
    body.append(
        latex.note(
            "The blur on real hardware is mostly the dedither filter, bit 16 of VI_CTRL, "
            "not edge anti-aliasing. The filter never appears in a video mode table: a game "
            "switches it on at runtime, so clearing it edits that routine instead. Anti-"
            "aliasing does live in the table, which is why a ROM with no provable table can "
            "have the filter cleared and not the anti-aliasing."
        )
    )
    body.append(
        latex.longtable(
            ["What", "Games"],
            [
                ["Anti-aliasing on, can be cleared", str(len(aa))],
                ["Dedither filter reachable, can be cleared", str(len(dither))],
                [
                    "Dedither filter already unreachable",
                    str(len(known) - len(dither) - len(blocked)),
                ],
                ["Checksum invalid, nothing can be resealed", str(len(blocked))],
                ["Could not be read", str(len(unreadable))],
            ],
            widths=["100mm", "20mm"],
            align=["l", "r"],
        )
    )

    changeable = sorted({r.title: r for r in aa + dither}.values(), key=lambda r: r.title)
    if changeable:
        body.append(latex.section("Games with a video patch available"))
        body.append(
            latex.longtable(
                ["Game", "Modes", "AA on", "Divot", "Gamma dither", "Can clear"],
                [
                    [
                        r.title,
                        str(r.video.modes),
                        str(r.video.antialiasing_on),
                        str(r.video.divot_on),
                        str(r.video.gamma_dither_on),
                        r.video.summary,
                    ]
                    for r in changeable
                    if r.video is not None
                ],
                widths=["58mm", "14mm", "13mm", "13mm", "22mm", "38mm"],
                align=["l", "r", "r", "r", "r", "l"],
            )
        )

    if blocked:
        body.append(latex.section("Video patches refused"))
        body.append(
            latex.longtable(
                ["Game", "Why"],
                [
                    [
                        r.title,
                        "the dump's checksum matches no known boot chip, so a patched "
                        "copy could not be resealed and would not boot",
                    ]
                    for r in sorted(blocked, key=lambda x: x.title)
                ],
                widths=["55mm", "105mm"],
            )
        )

    return body


def build(rows: list[Row], *, rules: Rules, held: Inventory, generated: str) -> str:
    body: list[str] = [latex.section("Summary"), _summary(rows, generated)]

    body.append(latex.section("Flags"))
    body.append(
        latex.longtable(
            ["Flag", "Meaning"],
            [[flag, meaning] for flag, meaning in FLAG_LEGEND],
            widths=["12mm", "150mm"],
        )
    )

    if not held.is_recorded:
        body.append(
            latex.note(
                "No hardware inventory has been recorded, so this document does not claim "
                "anything about which cartridges are available. A title marked as unable to "
                "save needs a donor cartridge; whether that is a gap depends on what the "
                "reader owns."
            )
        )

    counts = collections.Counter(r.status for r in rows)
    body.append(latex.section("Save capability"))
    body.append(
        latex.longtable(
            ["Status", "Games"],
            [[STATUS_LABEL.get(s, s), str(n)] for s, n in counts.most_common()],
            widths=["60mm", "20mm"],
            align=["l", "r"],
        )
    )

    body.append(latex.section("Boot chip"))
    body.append(
        latex.longtable(
            ["CIC", "Games", "What to set in Game Setup"],
            [
                [cic, str(n), rules.boot_chip_action(cic) or "no change needed"]
                for cic, n in collections.Counter(r.cic for r in rows).most_common()
            ],
            widths=["18mm", "16mm", "120mm"],
            align=["l", "r", "l"],
        )
    )

    affected = [r for r in rows if r.requirement]
    if affected:
        body.append(latex.section("What each affected game needs"))
        body.append(
            latex.longtable(
                ["Game", "What it needs"],
                [[r.title, r.requirement] for r in sorted(affected, key=lambda x: x.title)],
                widths=["55mm", "105mm"],
            )
        )

    body.extend(_video_sections(rows))

    body.append(latex.section("Disk contents"))
    for disk in sorted({r.disk for r in rows}):
        on_disk = [r for r in rows if r.disk == disk]
        used = sum(r.mib for r in on_disk)
        body.append(
            f"\\textbf{{{latex.escape(disk)}}} \\hfill "
            f"{{\\footnotesize {len(on_disk)} games, {used} MiB}}\\\\[2pt]\n"
        )
        body.append(
            latex.longtable(
                ["Game", "On disk", "MiB", "CIC", "Save", "Status", "Video", "CRC1", "Flags"],
                [
                    [
                        r.title,
                        r.name83,
                        str(r.mib),
                        r.cic,
                        rules.save_label(r.save),
                        STATUS_LABEL.get(r.status, r.status),
                        r.video.summary if r.video is not None else VIDEO_UNREAD,
                        r.crc1,
                        r.flags,
                    ]
                    for r in on_disk
                ],
                widths=[
                    "38mm",
                    "22mm",
                    "8mm",
                    "11mm",
                    "18mm",
                    "15mm",
                    "24mm",
                    "15mm",
                    "8mm",
                ],
                align=["l", "l", "r", "l", "l", "l", "l", "l", "l"],
            )
        )

    body.append(latex.section("How these values were obtained"))
    body.append(
        latex.note(
            "Every figure is read from the files themselves. The boot chip is recovered by "
            "recomputing the header checksum against each known seed, so it is measured "
            "rather than looked up. A patch is bound to a ROM by the first 64 bytes of its "
            "target, which include both checksums, so a patch built for a different revision "
            "is never applied. Source for the memory limit: " + rules.memory_source
        )
    )

    return latex.document(
        title="Nintendo 64 Disk Catalogue",
        subtitle=f"Mr. Backup Z64, Iomega Zip 100. Generated {generated}.",
        body="\n".join(body),
    )


def video_for(game: Game) -> Video | None:
    """Read a ROM and describe its video configuration.

    This is the one figure in the document that cannot come from the header, so it
    costs a full read per game. A ROM that cannot be read is reported as unknown
    rather than as clean, because claiming a game needs no video patch when the
    question was never asked is the one wrong answer here.
    """
    from ..vi import audit, find_dither_requests

    try:
        rom = Path(game.path).read_bytes()
    except OSError:
        return None
    report = audit(rom)
    return Video(
        modes=report.mode_count,
        antialiasing_on=report.antialiasing_on,
        divot_on=report.divot_on,
        gamma_dither_on=report.gamma_dither_on,
        dither_requests=len(find_dither_requests(rom)),
        checksum_valid=game.checksum_valid,
    )


def rows_from(
    layout: list[tuple[str, list[Game]]],
    names: dict[str, str],
    saves: dict[str, str],
    rules: Rules,
    patched: set[str],
) -> list[Row]:
    """Build rows from a disk layout, an 8.3 name assignment and a save type lookup."""
    out: list[Row] = []
    for disk_name, games in layout:
        for game in games:
            candidate = Candidate(
                key=game.filename,
                title=game.stem,
                save=saves.get(game.filename, "none"),
                cic=game.cic,
                size=game.size,
                has_patch=game.filename in patched,
            )
            verdict = classify(candidate, rules)
            base = names.get(game.filename, "")
            out.append(
                Row(
                    disk=disk_name,
                    title=game.stem,
                    name83=f"{base}.{game.true_extension}" if base else "",
                    mib=game.size // (1024 * 1024),
                    cic=game.cic,
                    save=candidate.save,
                    status=verdict.status,
                    flags=flags_for(verdict, game, has_companion=game.filename in patched),
                    crc1=game.crc1,
                    requirement=requirement_for(verdict, rules),
                    video=video_for(game),
                )
            )
    return out
