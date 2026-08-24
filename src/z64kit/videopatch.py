"""Deliver a video change as a patch, so the ROM on disk is never written.

Turning anti-aliasing off means editing the VI mode table, which sits inside the
region the ROM checksum covers, so the checksum has to be resealed. The checksum
lives at offset 0x10, inside the first 64 bytes, and those 64 bytes are exactly
what the unit compares against a stored header to find a game's patch. Editing
the ROM therefore delivers the video change and silently loses the patch the game
needs to boot.

A patch has no such cost. It records the checksums of the ROM it was built
against, the ROM is left alone, and the binding stays as the vendor built it.
Where a game already carries a patch the two fold into one, because the unit
applies one patch per ROM and a second file is not a way out.

One rule governs every branch: an outcome this code cannot prove safe carries no
patch. Emitting nothing costs a video change on that game. Emitting the wrong
thing costs the game.
"""

from __future__ import annotations

from dataclasses import dataclass

from n64_video_interface import vi

from . import aps, merge

VIDEO_ONLY = "video_only"
MERGED = "merged"
SKIPPED = "skipped"

DESCRIPTION = "video settings"


@dataclass(frozen=True)
class Outcome:
    """What to emit for one game, and why."""

    kind: str
    patch: bytes | None
    reason: str


def _skip(reason: str) -> Outcome:
    return Outcome(SKIPPED, None, reason)


def build_for(rom: bytes, existing: bytes | None, **video: bool) -> Outcome:
    """The patch to ship for one game, or a refusal that ships nothing.

    `existing` is the patch the game already needs, as bytes, or None when it
    needs none. A game whose existing patch cannot be read or folded keeps that
    patch untouched and goes without the video change, which is the only outcome
    of the three that costs nothing but sharpness.
    """
    if existing is None:
        result = vi.safe_patch(rom, **video)
        if not result.applied:
            return _skip(result.reason)
        return Outcome(
            VIDEO_ONLY,
            aps.build(rom, result.data, description=DESCRIPTION),
            f"{result.modes_changed} modes, boot chip {result.cic}, resealed",
        )

    try:
        folded = merge.merge(rom, existing, **video)
    except aps.FormatError as error:
        return _skip(f"the existing patch is not an APS payload, so it cannot be folded: {error}")
    except (aps.TargetMismatchError, merge.UnsafeMergeError, ValueError) as error:
        return _skip(str(error))

    if not folded.video_changes:
        return _skip("the video settings already match, so the existing patch is kept as it is")

    return Outcome(
        MERGED,
        folded.patch,
        f"folded into {folded.existing_records} existing records, boot chip {folded.cic}",
    )
