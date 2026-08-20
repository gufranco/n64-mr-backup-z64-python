"""Fold a video change into the patch a game already needs, producing one patch.

The unit resolves a patch by matching the loaded ROM's first 64 bytes against a
stored header, and it applies one patch per ROM. Two consequences follow, and
together they force this design.

Editing the ROM is not an option even when the edit is correct, because the
header carries the checksum. Resealing after a video edit changes the header, and
the stored header no longer matches, so the save fix the game needs would stop
being found. The video change would arrive and the save fix would vanish.

Shipping a second patch file is not an option either, because there is one slot.

So the two changes become one patch. The existing patch is applied in memory, the
video change is applied on top of that result, the checksum is resealed once over
the final state, and the difference from the untouched original is expressed as a
single patch. The ROM on disk is never written, so the binding that finds the
patch stays exactly as the vendor built it.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import aps, vi
from .rom import checksum

DESCRIPTION = "merged save fix and video settings"


class UnsafeMergeError(RuntimeError):
    """Raised when the inputs cannot be combined without guessing."""


@dataclass(frozen=True)
class Merged:
    patch: bytes
    cic: str
    video_changes: tuple[tuple[int, int, int], ...] = ()
    existing_records: int = 0


def merge(rom: bytes, existing_patch: bytes, **video: bool) -> Merged:
    """Combine `existing_patch` and the requested video changes into one patch.

    Refuses rather than guesses. The existing patch must bind to this exact ROM,
    and it must leave a ROM whose checksum verifies, because a video change is
    applied on top of its output and an unverifiable intermediate means the
    result cannot be trusted either.
    """
    parsed = aps.parse(existing_patch)
    intermediate = aps.apply(rom, parsed, verify=True)

    valid, resolved = checksum.verify(intermediate)
    if not valid:
        raise UnsafeMergeError(
            "the existing patch leaves a ROM whose header checksum does not verify "
            "under any known boot chip, so a video change stacked on it cannot be "
            "trusted. Verify the patch against the ROM it was built for before merging."
        )

    if not vi.find_mode_tables(intermediate):
        raise UnsafeMergeError(
            "no video mode table could be proven present in the patched ROM, so "
            "there is nothing safe to edit. Merging a refusal would emit a patch "
            "that silently drops the video change."
        )

    result = vi.safe_patch(intermediate, **video)
    if result.reason == vi.NO_CHANGE_NEEDED:
        return Merged(
            patch=existing_patch,
            cic=resolved or result.cic,
            video_changes=(),
            existing_records=len(parsed.records),
        )
    if not result.applied:
        raise UnsafeMergeError(
            f"the video change was refused and produced nothing: {result.reason}. "
            "Merging a refusal would emit a patch that silently drops it."
        )

    return Merged(
        patch=aps.build(rom, result.data, description=DESCRIPTION),
        cic=resolved or result.cic,
        video_changes=tuple(result.changes),
        existing_records=len(parsed.records),
    )
