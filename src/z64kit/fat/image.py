"""The blank FAT16 volume a Zip 100 needs, built byte by byte.

Three details decide whether the unit can read the result at all.

The partition type must be 0x06. Real mode DOS, which is what the unit runs,
does not understand 0x0E, the LBA variant, so a volume formatted by a modern
operating system may be invisible to the hardware even though it mounts fine on
a desktop.

The geometry must be the native Zip 100 one, 96 cylinders of 64 heads of 32
sectors, which multiplies out to exactly the media size.

Everything here is deterministic. The volume serial is zero and every timestamp
is the fixed TorrentZip constant, so two builds of the same content produce
identical bytes. A serial is written per physical disk at flashing time instead,
because real mode DOS uses it to notice a media change.

An image carries no identity at all: no volume label, in the boot record or as a
directory entry, and a volume serial of zero. Two images holding the same files
are therefore the same bytes, not merely reproducible from the same input, and the
first root slot is free for a file rather than spent on a name.

Identity belongs to the physical disk instead, and is stamped when one is written.
Real mode DOS uses the serial to notice that the media changed, so two disks
sharing one can make it serve a cached FAT from the previous disk after a swap,
which reads as corruption. That is a property of a disk in a drive, not of a file
on a workstation, so nothing here can or should decide it.

Note that an empty label is not the same as no label: it writes an entry whose
name is eleven spaces, which is a label that happens to look blank. Nothing here
writes that entry at all.
"""

from __future__ import annotations

import struct

SECTOR = 512
TOTAL_SECTORS = 196_608
HEADS = 64
SECTORS_PER_TRACK = 32
CYLINDERS = TOTAL_SECTORS // (HEADS * SECTORS_PER_TRACK)

PART_START_LBA = 32
PART_TYPE_FAT16_CHS = 0x06

BYTES_PER_SECTOR = 512
SECTORS_PER_CLUSTER = 4
RESERVED_SECTORS = 1
NUM_FATS = 2
ROOT_ENTRIES = 512
SECTORS_PER_FAT = 192
MEDIA_DESCRIPTOR = 0xF8
OEM_NAME = b"MSDOS5.0"
DRIVE_NUMBER = 0x80

TZ_DATE = ((1996 - 1980) << 9) | (12 << 5) | 24
TZ_TIME = (23 << 11) | (32 << 5) | 0

ATTR_VOLUME_LABEL = 0x08


def partition_sectors() -> int:
    return TOTAL_SECTORS - PART_START_LBA


def root_sectors() -> int:
    return ROOT_ENTRIES * 32 // BYTES_PER_SECTOR


def fat_lba(index: int) -> int:
    return PART_START_LBA + RESERVED_SECTORS + index * SECTORS_PER_FAT


def root_lba() -> int:
    return PART_START_LBA + RESERVED_SECTORS + NUM_FATS * SECTORS_PER_FAT


def data_lba() -> int:
    return root_lba() + root_sectors()


def metadata_extent_sectors() -> int:
    """Sectors that carry meaning on an empty volume, so the rest need no writing."""
    return data_lba()


def cluster_count() -> int:
    data_sectors = (
        partition_sectors() - RESERVED_SECTORS - NUM_FATS * SECTORS_PER_FAT - root_sectors()
    )
    return data_sectors // SECTORS_PER_CLUSTER


def usable_capacity() -> int:
    return cluster_count() * SECTORS_PER_CLUSTER * BYTES_PER_SECTOR


def lba_to_chs(lba: int) -> tuple[int, int, int]:
    cylinder, remainder = divmod(lba, HEADS * SECTORS_PER_TRACK)
    head, sector = divmod(remainder, SECTORS_PER_TRACK)
    sector += 1
    if cylinder > 1023:
        cylinder, head, sector = 1023, HEADS - 1, SECTORS_PER_TRACK
    return head, (sector & 0x3F) | ((cylinder >> 2) & 0xC0), cylinder & 0xFF


def _message_stub(text: str, code_offset: int) -> bytes:
    """A tiny real mode stub that prints a message and waits, as period tools wrote."""
    prologue = bytes([0xFA, 0x31, 0xC0, 0x8E, 0xD8, 0x8E, 0xC0, 0x8E, 0xD0, 0xBC, 0x00, 0x7C, 0xFB])
    message_address = 0x7C00 + code_offset + len(prologue) + 3 + 14
    body = struct.pack("<BH", 0xBE, message_address) + bytes(
        [
            0xAC,
            0x08,
            0xC0,
            0x74,
            0x09,
            0xB4,
            0x0E,
            0xBB,
            0x07,
            0x00,
            0xCD,
            0x10,
            0xEB,
            0xF2,
            0x31,
            0xC0,
            0xCD,
            0x16,
            0xCD,
            0x19,
        ]
    )
    return prologue + body + text.encode("ascii") + b"\x00"


STUB_TEXT = "Non-system disk\r\nPress any key\r\n"


def master_boot_record() -> bytes:
    sector = bytearray(SECTOR)
    stub = _message_stub(STUB_TEXT, 0)
    sector[0 : len(stub)] = stub

    start_head, start_sector, start_cylinder = lba_to_chs(PART_START_LBA)
    end_head, end_sector, end_cylinder = lba_to_chs(TOTAL_SECTORS - 1)
    sector[446:462] = struct.pack(
        "<BBBBBBBBII",
        0x00,
        start_head,
        start_sector,
        start_cylinder,
        PART_TYPE_FAT16_CHS,
        end_head,
        end_sector,
        end_cylinder,
        PART_START_LBA,
        partition_sectors(),
    )
    sector[510:512] = b"\x55\xaa"
    return bytes(sector)


NO_LABEL = b" " * 11
NO_SERIAL = 0


def boot_sector() -> bytes:
    sector = bytearray(SECTOR)
    sector[0:3] = bytes([0xEB, 0x3C, 0x90])
    sector[3:11] = OEM_NAME
    struct.pack_into("<H", sector, 11, BYTES_PER_SECTOR)
    sector[13] = SECTORS_PER_CLUSTER
    struct.pack_into("<H", sector, 14, RESERVED_SECTORS)
    sector[16] = NUM_FATS
    struct.pack_into("<H", sector, 17, ROOT_ENTRIES)
    struct.pack_into("<H", sector, 19, 0)
    sector[21] = MEDIA_DESCRIPTOR
    struct.pack_into("<H", sector, 22, SECTORS_PER_FAT)
    struct.pack_into("<H", sector, 24, SECTORS_PER_TRACK)
    struct.pack_into("<H", sector, 26, HEADS)
    struct.pack_into("<I", sector, 28, PART_START_LBA)
    struct.pack_into("<I", sector, 32, partition_sectors())
    sector[36] = DRIVE_NUMBER
    sector[38] = 0x29
    struct.pack_into("<I", sector, 39, NO_SERIAL)
    sector[43:54] = NO_LABEL
    sector[54:62] = b"FAT16   "
    stub = _message_stub(STUB_TEXT, 0x3E)
    sector[0x3E : 0x3E + len(stub)] = stub
    sector[510:512] = b"\x55\xaa"
    return bytes(sector)


def empty_fat() -> bytes:
    table = bytearray(SECTORS_PER_FAT * SECTOR)
    table[0:4] = bytes([MEDIA_DESCRIPTOR, 0xFF, 0xFF, 0xFF])
    return bytes(table)


def empty_root() -> bytes:
    """An empty root directory. No label entry, so slot zero is free for a file."""
    return bytes(root_sectors() * SECTOR)


def blank_image() -> bytes:
    parts = [
        master_boot_record(),
        bytes(SECTOR * (PART_START_LBA - 1)),
        boot_sector(),
        empty_fat(),
        empty_fat(),
        empty_root(),
    ]
    built = b"".join(parts)
    return built + bytes(TOTAL_SECTORS * SECTOR - len(built))
