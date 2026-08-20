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

from ..compat import Candidate, Rules, classify
from ..inventory import Inventory
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


def flags_for(verdict, game, *, has_companion: bool) -> str:
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
                ["Game", "On disk", "MiB", "CIC", "Save", "Status", "CRC1", "Flags"],
                [
                    [
                        r.title,
                        r.name83,
                        str(r.mib),
                        r.cic,
                        rules.save_label(r.save),
                        STATUS_LABEL.get(r.status, r.status),
                        r.crc1,
                        r.flags,
                    ]
                    for r in on_disk
                ],
                widths=["55mm", "20mm", "11mm", "12mm", "24mm", "20mm", "18mm", "12mm"],
                align=["l", "l", "r", "l", "l", "l", "l", "l"],
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


def rows_from(layout, names, saves, rules: Rules, patched: set[str]) -> list[Row]:
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
                )
            )
    return out
