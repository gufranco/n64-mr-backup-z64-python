"""The part of an image a writer actually has to copy, and the identity a disk gets.

A Zip 100 image is 96 MiB whether or not the games fill it, and everything past the
last used cluster is zero. Writing that tail costs minutes on a drive managing about
765 kB/s, so a writer copies the prefix and stops.

The prefix is not a guess. The FAT records which clusters are in use, so the highest
used one gives the exact last meaningful sector. Reading the BPB rather than assuming
it keeps the answer right for an image this package did not build.

The other job here is the volume serial. Images carry none by design, so that two
images holding the same files are the same bytes. Real mode DOS uses the serial to
notice that the media changed, and the unit runs real mode DOS, so two disks sharing
a serial can have it serve a cached FAT from the previous disk after a swap, which
reads as corruption. The serial therefore belongs to a disk rather than to a file,
and is stamped on the way to one.

`prepare` takes the serial rather than inventing it, so a caller can pin it and the
result stays a pure function of its inputs.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .image import PART_TYPE_FAT16_CHS, SECTOR, TOTAL_SECTORS

MBR_SIGNATURE_OFFSET = 510
MBR_SIGNATURE = b"\x55\xaa"
PARTITION_ENTRY = 446
PARTITION_TYPE_OFFSET = PARTITION_ENTRY + 4
PARTITION_LBA_OFFSET = PARTITION_ENTRY + 8

BPB_BYTES_PER_SECTOR = 11
BPB_SECTORS_PER_CLUSTER = 13
BPB_RESERVED = 14
BPB_NUM_FATS = 16
BPB_ROOT_ENTRIES = 17
BPB_SECTORS_PER_FAT = 22
BPB_SERIAL = 39

FIRST_DATA_CLUSTER = 2
SERIAL_MASK = 0xFFFFFFFF


class ImageRejectedError(ValueError):
    """The file is not a Zip 100 image this tool is willing to write to a disk."""


@dataclass(frozen=True)
class Payload:
    """The bytes to write, and what a caller wants to report about them."""

    body: bytes
    sectors: int
    highest_cluster: int
    data_start_lba: int
    partition_lba: int
    serial: int

    @property
    def size(self) -> int:
        return self.sectors * SECTOR


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise ImageRejectedError(message)


def highest_used_cluster(table: bytes, entries: int) -> int:
    """The last cluster the FAT marks as used, or 1 when nothing is allocated.

    One rather than zero because clusters are numbered from two, so 1 reads as
    "nothing allocated" without needing a separate flag. The scan does not stop at
    the first free entry, since a deleted file leaves a gap ahead of live data.
    """
    highest = 1
    for cluster in range(FIRST_DATA_CLUSTER, entries):
        if struct.unpack_from("<H", table, cluster * 2)[0] != 0:
            highest = cluster
    return highest


def prepare(image: bytes, serial: int) -> Payload:
    """Validate an image, find its used extent, and stamp a serial on the copy.

    The serial goes onto the returned body only. The image itself is never touched.
    """
    _expect(
        len(image) == TOTAL_SECTORS * SECTOR,
        f"image is {len(image)} bytes, expected {TOTAL_SECTORS * SECTOR}",
    )
    _expect(
        image[MBR_SIGNATURE_OFFSET : MBR_SIGNATURE_OFFSET + 2] == MBR_SIGNATURE,
        "image has no MBR signature",
    )

    partition_type = image[PARTITION_TYPE_OFFSET]
    _expect(
        partition_type == PART_TYPE_FAT16_CHS,
        f"partition type is 0x{partition_type:02X}, expected "
        f"0x{PART_TYPE_FAT16_CHS:02X}, the one real mode DOS reads",
    )

    partition_lba = struct.unpack_from("<I", image, PARTITION_LBA_OFFSET)[0]
    boot = image[partition_lba * SECTOR : (partition_lba + 1) * SECTOR]
    _expect(len(boot) == SECTOR, f"partition starts at sector {partition_lba}, past the image")

    bytes_per_sector = struct.unpack_from("<H", boot, BPB_BYTES_PER_SECTOR)[0]
    sectors_per_cluster = boot[BPB_SECTORS_PER_CLUSTER]
    reserved = struct.unpack_from("<H", boot, BPB_RESERVED)[0]
    num_fats = boot[BPB_NUM_FATS]
    root_entries = struct.unpack_from("<H", boot, BPB_ROOT_ENTRIES)[0]
    sectors_per_fat = struct.unpack_from("<H", boot, BPB_SECTORS_PER_FAT)[0]

    _expect(bytes_per_sector == SECTOR, f"boot record says {bytes_per_sector} bytes per sector")
    _expect(sectors_per_cluster > 0, "boot record says zero sectors per cluster")
    _expect(num_fats > 0, "boot record says zero FATs")
    _expect(sectors_per_fat > 0, "boot record says zero sectors per FAT")

    root_sectors = root_entries * 32 // bytes_per_sector
    data_start_lba = partition_lba + reserved + num_fats * sectors_per_fat + root_sectors

    fat_start = (partition_lba + reserved) * SECTOR
    table = image[fat_start : fat_start + sectors_per_fat * SECTOR]
    highest = highest_used_cluster(table, len(table) // 2)

    if highest < FIRST_DATA_CLUSTER:
        sectors = data_start_lba
    else:
        sectors = data_start_lba + (highest - 1) * sectors_per_cluster

    _expect(
        sectors <= TOTAL_SECTORS,
        f"the FAT claims {sectors} sectors, more than the {TOTAL_SECTORS} the image holds",
    )

    stamped = serial & SERIAL_MASK
    body = bytearray(image[: sectors * SECTOR])
    struct.pack_into("<I", body, partition_lba * SECTOR + BPB_SERIAL, stamped)

    return Payload(
        body=bytes(body),
        sectors=sectors,
        highest_cluster=highest,
        data_start_lba=data_start_lba,
        partition_lba=partition_lba,
        serial=stamped,
    )
