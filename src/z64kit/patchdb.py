"""The unit's patch database, read and rebuilt as the ZIP container it is.

`z64patch.dat` opens with `PK\x03\x04`. Inside, each patch is a pair: `name.aps`
carrying the payload and `name.hdr` carrying the 64 bytes of the untouched ROM
that the unit matches against to find it.

That pairing is what makes an in-place rebuild the safe way to deliver a merged
patch. Dropping a second patch beside the ROM would leave two candidates for one
game, and which of them the unit prefers has never been established on hardware.
Replacing the payload while the header stays byte-identical leaves exactly one
candidate, bound by exactly the key it was bound by before.

Every guard below refuses rather than guesses, because each failure it prevents
is silent on the writing machine and only shows up as a game that stopped being
found once the disk is in the drive.
"""

from __future__ import annotations

import io
import zipfile

from .aps import MAGIC

HEADER_EXTENSION = ".hdr"
PATCH_EXTENSION = ".aps"
HEADER_SIZE = 64


class NotADatabaseError(ValueError):
    """Raised when the bytes are not the ZIP container the unit ships."""


class UnknownMemberError(KeyError):
    """Raised when a replacement names a member the database does not carry."""


class LookupKeyError(ValueError):
    """Raised when a replacement would move the header the unit matches on."""


class NotAPatchError(ValueError):
    """Raised when a replacement payload is not an APS patch."""


def read(blob: bytes) -> dict[str, bytes]:
    """Every member, in the order the container stores them."""
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            return {info.filename: archive.read(info.filename) for info in archive.infolist()}
    except zipfile.BadZipFile as error:
        raise NotADatabaseError(
            f"the patch database is not a readable ZIP container: {error}"
        ) from error


def patch_members(members: dict[str, bytes]) -> dict[str, str]:
    """Each patch payload mapped to the header sidecar that binds it.

    A payload with no sidecar is left out. Its binding would have to come from the
    checksums stored inside the patch, and a rebuild has no reason to touch a
    member it cannot prove the unit locates the same way afterwards.
    """
    out = {}
    for name in members:
        if not name.lower().endswith(PATCH_EXTENSION):
            continue
        sidecar = name[: -len(PATCH_EXTENSION)] + HEADER_EXTENSION
        if sidecar in members and len(members[sidecar]) == HEADER_SIZE:
            out[name] = sidecar
    return out


def rebuild(blob: bytes, replacements: dict[str, bytes]) -> bytes:
    """A new container with the named payloads swapped and nothing else changed."""
    members = read(blob)

    for name, payload in replacements.items():
        if name not in members:
            raise UnknownMemberError(
                f"{name} is not in the patch database, so replacing it would add a member "
                "rather than swap one. Adding entries changes what the unit finds and is "
                "not what a rebuild is for."
            )
        if name.lower().endswith(HEADER_EXTENSION):
            raise LookupKeyError(
                f"{name} is the 64-byte header the unit matches a ROM against. Rewriting it "
                "would move the key that locates the patch, so the game it belongs to would "
                "stop being found."
            )
        if payload[: len(MAGIC)] != MAGIC:
            raise NotAPatchError(
                f"the replacement for {name} does not start with {MAGIC!r}, so it is not an "
                "APS patch and the unit would not be able to apply it."
            )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, original in members.items():
            archive.writestr(name, replacements.get(name, original))
    return buffer.getvalue()
