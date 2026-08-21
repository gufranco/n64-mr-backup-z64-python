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

from ..compat import Candidate, Rules, classify, requirement_for
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

NEEDS_FILE = "+file"


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
        """What a patch would take out, named rather than abbreviated.

        A bare "AA" left the reader to work out whether it meant the setting was
        on or that it would be removed, and said nothing about the dedither filter
        going with it.
        """
        if not self.checksum_valid:
            return "refused, no boot chip"
        wanted = []
        if self.aa_patchable:
            wanted.append("anti-aliasing")
        if self.dither_patchable:
            wanted.append("dedither")
        if wanted:
            return "removes " + " and ".join(wanted)
        return "nothing to remove"


@dataclass(frozen=True)
class Row:
    disk: str
    title: str
    mib: int
    cic: str
    save: str
    status: str
    needs_file: bool = False
    requirement: str = ""
    video: Video | None = None


def status_label(status: str, *, needs_file: bool) -> str:
    """What the Status column prints.

    The old flag column carried six markers and only one of them said anything the
    rest of the row did not. P, B, ! and X were computed straight from the status
    beside them, and ? repeated the CIC column already reading "unknown". The
    companion save file is the one fact with nowhere else to live, so it rides
    here instead of paying for a column and a legend.
    """
    label = STATUS_LABEL.get(status, status)
    return f"{label} {NEEDS_FILE}" if needs_file else label


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
            ("Has no save data at all", str(counts.get("no-save-data", 0))),
            ("Cannot save without hardware", str(counts.get("needs-donor", 0))),
            ("Cannot load at all", str(counts.get("too-large", 0))),
            ("Needs a companion save file", str(sum(1 for r in rows if r.needs_file))),
            ("Generated", generated),
        ]
    )


def _video_sections(rows: list[Row]) -> list[str]:
    """The video picture: what blurs, what can be cleared, and what cannot.

    Counts only. What each individual game gives up sits in the Video column of
    its own disk listing, so repeating it here as a second table would say the
    same thing twice and add a page.

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
            "The blur on real hardware is mostly the dedither filter, not edge anti-aliasing. "
            "The two are set in different places, so a game can lose one and keep the other."
        )
    )
    body.append(
        latex.longtable(
            ["What", "Games"],
            [
                [what, str(count)]
                for what, count in (
                    ("Anti-aliasing can be removed", len(aa)),
                    ("Dedither filter can be removed", len(dither)),
                    ("Dedither filter already off", len(known) - len(dither) - len(blocked)),
                    ("Refused, no known boot chip", len(blocked)),
                    ("Could not be read", len(unreadable)),
                )
                if count
            ],
            widths=["100mm", "20mm"],
            align=["l", "r"],
        )
    )

    return body


def build(rows: list[Row], *, rules: Rules, held: Inventory, generated: str) -> str:
    body: list[str] = [latex.section("Summary"), _summary(rows, generated)]

    if not held.is_recorded:
        body.append(
            latex.note(
                "No hardware inventory has been recorded, so this document does not claim "
                "anything about which cartridges are available. A title marked as unable to "
                "save needs a donor cartridge; whether that is a gap depends on what the "
                "reader owns."
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
                ["Game", "CIC", "Save", "Status", "Video"],
                [
                    [
                        r.title,
                        r.cic,
                        rules.save_label(r.save),
                        status_label(r.status, needs_file=r.needs_file),
                        r.video.summary if r.video is not None else VIDEO_UNREAD,
                    ]
                    for r in on_disk
                ],
                widths=["68mm", "12mm", "22mm", "26mm", "42mm"],
                align=["l", "l", "l", "l", "l"],
            )
        )

    body.append(latex.section("How these values were obtained"))
    body.append(
        latex.note(
            "Every figure is read from the files themselves. The boot chip is measured by "
            "recomputing the header checksum against each known seed rather than looked up, "
            "and a patch is bound to a ROM by the first 64 bytes of its target, so one built "
            "for another revision is never applied. Memory limit: " + rules.memory_source
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
    saves: dict[str, str],
    rules: Rules,
    patched: set[str],
) -> list[Row]:
    """Build rows from a disk layout and a save type lookup."""
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
            out.append(
                Row(
                    disk=disk_name,
                    title=game.stem,
                    mib=game.size // (1024 * 1024),
                    cic=game.cic,
                    save=candidate.save,
                    status=verdict.status,
                    needs_file=game.filename in patched,
                    requirement=requirement_for(verdict, rules),
                    video=video_for(game),
                )
            )
    return out
