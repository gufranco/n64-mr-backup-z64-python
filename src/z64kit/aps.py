"""The APS patch format, as the Mr Backup Z64 stores and consumes it.

The layout here was not taken from documentation. It was pinned by parsing every
patch in a real `z64patch.dat` and requiring each one to consume its bytes to
exact EOF, then cross-checking the stored checksums against the 64-byte `.hdr`
that sits beside each patch in that archive. All eighteen agreed, which is what
establishes that the `.hdr` is the source ROM's header and the stored checksums
describe the ROM before patching rather than after.

That last point is what makes merging possible. A patch is bound to the ROM it
was built against, so a second change folded into the same patch leaves the
binding intact as long as the ROM on disk is never touched.

Offsets are little endian, checksums big endian, matching the observed files.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

MAGIC = b"APS10"
TYPE_N64 = 1
DESCRIPTION_OFFSET = 7
DESCRIPTION_LENGTH = 50
CART_ID_OFFSET = 0x3A
COUNTRY_OFFSET = 0x3C
CRC1_OFFSET = 0x3D
CRC2_OFFSET = 0x41
SIZE_OFFSET = 0x4A
RECORDS_OFFSET = 0x4E

ROM_CRC1_OFFSET = 0x10
ROM_CRC2_OFFSET = 0x14

MAX_RECORD = 0xFF
RECORD_HEADER = 5
RUN_THRESHOLD = 8


class FormatError(ValueError):
    """Raised when the bytes are not a patch this reader understands."""


class TargetMismatchError(ValueError):
    """Raised when a patch is applied to a ROM it was not built for."""


@dataclass(frozen=True)
class Patch:
    crc1: int
    crc2: int
    cart_id: bytes = b"  "
    country: bytes = b" "
    size: int = 0
    description: str = ""
    records: tuple[tuple[int, bytes], ...] = ()


def parse(raw: bytes) -> Patch:
    if raw[: len(MAGIC)] != MAGIC:
        raise FormatError(f"wrong magic, expected {MAGIC!r} and found {raw[:5]!r}")
    if len(raw) < RECORDS_OFFSET:
        raise FormatError(f"truncated header, {len(raw)} bytes is short of {RECORDS_OFFSET}")
    if raw[5] != TYPE_N64:
        raise FormatError(f"patch type {raw[5]} is not the N64 type {TYPE_N64}")

    crc1, crc2 = struct.unpack(">II", raw[CRC1_OFFSET : CRC1_OFFSET + 8])
    records: list[tuple[int, bytes]] = []
    at = RECORDS_OFFSET
    while at < len(raw):
        if at + RECORD_HEADER > len(raw):
            raise FormatError(f"truncated record header at {at:#x}")
        offset = struct.unpack("<I", raw[at : at + 4])[0]
        length = raw[at + 4]
        at += RECORD_HEADER
        if length == 0:
            if at + 2 > len(raw):
                raise FormatError(f"truncated run length record at {at:#x}")
            records.append((offset, bytes([raw[at + 1]]) * raw[at]))
            at += 2
            continue
        if at + length > len(raw):
            raise FormatError(f"truncated record payload at {at:#x}, wanted {length} bytes")
        records.append((offset, raw[at : at + length]))
        at += length

    return Patch(
        crc1=crc1,
        crc2=crc2,
        cart_id=raw[CART_ID_OFFSET:COUNTRY_OFFSET],
        country=raw[COUNTRY_OFFSET : COUNTRY_OFFSET + 1],
        size=struct.unpack("<I", raw[SIZE_OFFSET : SIZE_OFFSET + 4])[0],
        description=raw[DESCRIPTION_OFFSET : DESCRIPTION_OFFSET + DESCRIPTION_LENGTH]
        .decode("latin1")
        .strip(),
        records=tuple(records),
    )


HEADER_LENGTH = 0x40


def target_checksums(rom: bytes) -> tuple[int, int]:
    if len(rom) < HEADER_LENGTH:
        raise ValueError(f"a ROM header is {HEADER_LENGTH} bytes and this input is {len(rom)}")
    return struct.unpack(">II", rom[ROM_CRC1_OFFSET : ROM_CRC1_OFFSET + 8])


def apply(rom: bytes, patch: Patch, verify: bool = False) -> bytes:
    """Apply every record in order. Later records win, matching the observed files."""
    if verify:
        found1, found2 = target_checksums(rom)
        if found1 != patch.crc1:
            raise TargetMismatchError(
                f"CRC1 mismatch: the patch targets {patch.crc1:#010x} "
                f"and this ROM carries {found1:#010x}"
            )
        if found2 != patch.crc2:
            raise TargetMismatchError(
                f"CRC2 mismatch: the patch targets {patch.crc2:#010x} "
                f"and this ROM carries {found2:#010x}"
            )
    out = bytearray(rom)
    for offset, payload in patch.records:
        end = offset + len(payload)
        if end > len(out):
            out.extend(bytes(end - len(out)))
        out[offset:end] = payload
    return bytes(out)


def _runs(original: bytes, patched: bytes) -> list[tuple[int, bytes]]:
    """Collect maximal differing spans, then cut them to the record size limit."""
    limit = max(len(original), len(patched))
    spans: list[tuple[int, bytes]] = []
    at = 0
    while at < limit:
        left = original[at] if at < len(original) else None
        right = patched[at] if at < len(patched) else None
        if left == right:
            at += 1
            continue
        start = at
        while at < limit:
            a = original[at] if at < len(original) else None
            b = patched[at] if at < len(patched) else None
            if a == b:
                break
            at += 1
        block = patched[start:at]
        for cut in range(0, len(block), MAX_RECORD):
            spans.append((start + cut, block[cut : cut + MAX_RECORD]))
    return spans


def _encode(offset: int, payload: bytes) -> bytes:
    """Prefer a run when the payload is uniform and long enough to pay for itself."""
    head = struct.pack("<I", offset)
    if len(payload) >= RUN_THRESHOLD and payload.count(payload[:1]) == len(payload):
        return head + bytes([0, len(payload), payload[0]])
    return head + bytes([len(payload)]) + payload


def build(original: bytes, patched: bytes, description: str = "") -> bytes:
    """Express the difference as a patch bound to the original ROM.

    The stored checksums come from `original`, never from `patched`. The unit
    finds a patch by matching the loaded ROM's header, so a patch that advertised
    the post-patch checksums would never be found for the ROM it belongs to.
    """
    if len(description) > DESCRIPTION_LENGTH:
        raise ValueError(
            f"description is {len(description)} characters, "
            f"more than the {DESCRIPTION_LENGTH} the format holds"
        )
    crc1, crc2 = target_checksums(original)
    out = bytearray(MAGIC)
    out += bytes([TYPE_N64, 0])
    out += description.ljust(DESCRIPTION_LENGTH).encode("latin1")
    out += bytes([0])
    out += original[0x3C:0x3E]
    out += original[0x3E:0x3F]
    out += struct.pack(">II", crc1, crc2)
    out += bytes(5)
    out += struct.pack("<I", len(patched))
    for offset, payload in _runs(original, patched):
        out += _encode(offset, payload)
    return bytes(out)
