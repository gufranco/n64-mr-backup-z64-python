"""Writing files into a FAT16 volume, in memory.

The whole volume is built as a byte array and handed back once, so nothing here
touches the filesystem and the result can be hashed, diffed or verified without
ever being written to disk. That is what makes the images reproducible and what
lets the test suite exercise the writer with no real collection present.

Allocation is contiguous and in call order. There is no attempt to place a file
at a physically faster position: measurement showed the spread across a 32 MiB
read is about seven percent, while a non contiguous file pays a seek on every
fragment, so contiguity is worth more than placement. Packing files from the
start also leaves the free space in one run at the tail, which is where the unit
writes its save files.

`verify` reads every file back through the structures this writer produced,
rather than from the buffers it wrote. A writer bug that corrupts a cluster
chain is invisible to any check that trusts its own bookkeeping.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from . import image

ROOT = 0

ATTR_READ_ONLY = 0x01
ATTR_HIDDEN = 0x02
ATTR_SYSTEM = 0x04
ATTR_VOLUME_LABEL = 0x08
ATTR_DIRECTORY = 0x10
ATTR_ARCHIVE = 0x20
ATTR_LONG_NAME = 0x0F

ENTRY_SIZE = 32
FREE_ENTRY = 0x00
DELETED_ENTRY = 0xE5
END_OF_CHAIN = 0xFFFF

DOT = b".          "
DOTDOT = b"..         "


class OutOfSpaceError(Exception):
    """Raised when the volume cannot hold another file."""


class NameCollisionError(Exception):
    """Raised when an 8.3 name is already taken in the target directory."""


class DirectoryFullError(Exception):
    """Raised when a directory has no free entry left."""


@dataclass(frozen=True)
class Placed:
    name: str
    first_cluster: int
    last_cluster: int
    size: int
    start_lba: int
    media_percent: float


@dataclass(frozen=True)
class Entry:
    name: bytes
    attributes: int
    cluster: int
    size: int

    @property
    def is_label(self) -> bool:
        return bool(self.attributes & ATTR_VOLUME_LABEL)

    @property
    def is_dir(self) -> bool:
        return bool(self.attributes & ATTR_DIRECTORY)


def pad83(base: str, extension: str) -> bytes:
    return (base.upper().ljust(8)[:8] + extension.upper().ljust(3)[:3]).encode("ascii", "replace")


def display_name(stored: bytes) -> str:
    base = stored[:8].decode("ascii", "replace").rstrip()
    extension = stored[8:11].decode("ascii", "replace").rstrip()
    return f"{base}.{extension}" if extension else base


class Volume:
    def __init__(self) -> None:
        self._data = bytearray(image.blank_image())
        self._dir_buffers: dict[int, bytearray] = {}
        self._sources: dict[tuple[int, bytes], bytes] = {}

    def _cluster_lba(self, cluster: int) -> int:
        return image.data_lba() + (cluster - 2) * image.SECTORS_PER_CLUSTER

    def _fat_get(self, cluster: int) -> int:
        offset = image.fat_lba(0) * image.SECTOR + cluster * 2
        return int(struct.unpack_from("<H", self._data, offset)[0])

    def _fat_set(self, cluster: int, value: int) -> None:
        for copy in range(image.NUM_FATS):
            offset = image.fat_lba(copy) * image.SECTOR + cluster * 2
            struct.pack_into("<H", self._data, offset, value)

    def _fat_limit(self) -> int:
        return image.cluster_count() + 2

    def free_clusters(self) -> int:
        return sum(1 for c in range(2, image.cluster_count() + 2) if self._fat_get(c) == 0)

    def free_bytes(self) -> int:
        return self.free_clusters() * image.SECTORS_PER_CLUSTER * image.SECTOR

    def _allocate(self, count: int) -> list[int]:
        limit = image.cluster_count() + 2
        found: list[int] = []
        for cluster in range(2, limit):
            if self._fat_get(cluster) == 0:
                found.append(cluster)
                if len(found) == count:
                    return found
        raise OutOfSpaceError(f"needs {count} clusters, {self.free_clusters()} free")

    def _chain(self, first: int) -> list[int]:
        chain: list[int] = []
        cluster = first
        while 2 <= cluster < 0xFFF8 and len(chain) < image.cluster_count() + 2:
            chain.append(cluster)
            cluster = self._fat_get(cluster)
        return chain

    def _dir_buffer(self, cluster: int) -> bytearray:
        if cluster == ROOT:
            start = image.root_lba() * image.SECTOR
            return self._data[start : start + image.root_sectors() * image.SECTOR]
        if cluster not in self._dir_buffers:
            buffer = bytearray()
            for part in self._chain(cluster):
                start = self._cluster_lba(part) * image.SECTOR
                buffer += self._data[start : start + image.SECTORS_PER_CLUSTER * image.SECTOR]
            self._dir_buffers[cluster] = buffer
        return self._dir_buffers[cluster]

    def _store_dir(self, cluster: int, buffer: bytearray) -> None:
        if cluster == ROOT:
            start = image.root_lba() * image.SECTOR
            span = image.root_sectors() * image.SECTOR
            if len(buffer) > span:
                raise DirectoryFullError(f"root holds {image.ROOT_ENTRIES} entries")
            self._data[start : start + span] = buffer.ljust(span, b"\x00")
        else:
            self._dir_buffers[cluster] = buffer

    def list_dir(self, cluster: int = ROOT) -> list[Entry]:
        buffer = self._dir_buffer(cluster)
        entries = []
        for offset in range(0, len(buffer), ENTRY_SIZE):
            raw = buffer[offset : offset + ENTRY_SIZE]
            if not raw or raw[0] in (FREE_ENTRY, DELETED_ENTRY):
                continue
            if raw[11] == ATTR_LONG_NAME:
                continue
            entries.append(
                Entry(
                    name=bytes(raw[0:11]),
                    attributes=raw[11],
                    cluster=struct.unpack_from("<H", raw, 26)[0],
                    size=struct.unpack_from("<I", raw, 28)[0],
                )
            )
        return entries

    def _make_entry(self, name: bytes, attributes: int, cluster: int, size: int) -> bytearray:
        raw = bytearray(ENTRY_SIZE)
        raw[0:11] = name
        raw[11] = attributes
        struct.pack_into("<H", raw, 14, image.TZ_TIME)
        struct.pack_into("<H", raw, 16, image.TZ_DATE)
        struct.pack_into("<H", raw, 18, image.TZ_DATE)
        struct.pack_into("<H", raw, 22, image.TZ_TIME)
        struct.pack_into("<H", raw, 24, image.TZ_DATE)
        struct.pack_into("<H", raw, 26, cluster)
        struct.pack_into("<I", raw, 28, size)
        return raw

    def _add_entry(self, parent: int, raw: bytearray) -> None:
        buffer = self._dir_buffer(parent)
        for offset in range(0, len(buffer), ENTRY_SIZE):
            if buffer[offset] in (FREE_ENTRY, DELETED_ENTRY):
                buffer[offset : offset + ENTRY_SIZE] = raw
                self._store_dir(parent, buffer)
                return
        if parent == ROOT:
            raise DirectoryFullError(f"root holds {image.ROOT_ENTRIES} entries")
        extra = self._allocate(1)[0]
        self._fat_set(extra, END_OF_CHAIN)
        for existing in self._chain(parent):
            if self._fat_get(existing) == END_OF_CHAIN and existing != extra:
                self._fat_set(existing, extra)
                break
        appended_at = len(buffer)
        buffer += bytearray(image.SECTORS_PER_CLUSTER * image.SECTOR)
        buffer[appended_at : appended_at + ENTRY_SIZE] = raw
        self._store_dir(parent, buffer)

    def _taken(self, parent: int) -> set[bytes]:
        return {e.name for e in self.list_dir(parent)}

    def add_file(self, parent: int, base: str, extension: str, data: bytes) -> Placed:
        name = pad83(base, extension)
        if name in self._taken(parent):
            raise NameCollisionError(f"{display_name(name)} already exists")

        cluster_bytes = image.SECTORS_PER_CLUSTER * image.SECTOR
        needed = max(1, -(-len(data) // cluster_bytes))
        clusters = self._allocate(needed)

        for index, cluster in enumerate(clusters):
            start = self._cluster_lba(cluster) * image.SECTOR
            chunk = data[index * cluster_bytes : (index + 1) * cluster_bytes]
            self._data[start : start + cluster_bytes] = chunk.ljust(cluster_bytes, b"\x00")
            self._fat_set(
                cluster,
                END_OF_CHAIN if index == len(clusters) - 1 else clusters[index + 1],
            )

        self._add_entry(parent, self._make_entry(name, ATTR_ARCHIVE, clusters[0], len(data)))
        self._sources[(parent, name)] = data

        start_lba = self._cluster_lba(clusters[0])
        return Placed(
            name=display_name(name),
            first_cluster=clusters[0],
            last_cluster=clusters[-1],
            size=len(data),
            start_lba=start_lba,
            media_percent=100.0 * start_lba / image.TOTAL_SECTORS,
        )

    def make_dir(self, parent: int, base: str) -> int:
        name = pad83(base, "")
        if name in self._taken(parent):
            raise NameCollisionError(f"{display_name(name)} already exists")
        cluster = self._allocate(1)[0]
        self._fat_set(cluster, END_OF_CHAIN)

        buffer = bytearray(image.SECTORS_PER_CLUSTER * image.SECTOR)
        buffer[0:ENTRY_SIZE] = self._make_entry(DOT, ATTR_DIRECTORY, cluster, 0)
        buffer[ENTRY_SIZE : ENTRY_SIZE * 2] = self._make_entry(DOTDOT, ATTR_DIRECTORY, parent, 0)
        self._dir_buffers[cluster] = buffer

        self._add_entry(parent, self._make_entry(name, ATTR_DIRECTORY, cluster, 0))
        return cluster

    def read_file(self, base: str, extension: str, parent: int = ROOT) -> bytes:
        name = pad83(base, extension)
        for entry in self.list_dir(parent):
            if entry.name == name:
                cluster_bytes = image.SECTORS_PER_CLUSTER * image.SECTOR
                out = b""
                for cluster in self._chain(entry.cluster):
                    start = self._cluster_lba(cluster) * image.SECTOR
                    out += bytes(self._data[start : start + cluster_bytes])
                return out[: entry.size]
        raise FileNotFoundError(display_name(name))

    def sort_directories(self, key: dict[str, str] | None = None, cluster: int = ROOT) -> None:
        buffer = self._dir_buffer(cluster)
        pinned, movable = [], []
        for offset in range(0, len(buffer), ENTRY_SIZE):
            raw = buffer[offset : offset + ENTRY_SIZE]
            if not raw or raw[0] in (FREE_ENTRY, DELETED_ENTRY):
                continue
            name = bytes(raw[0:11])
            if raw[11] & ATTR_VOLUME_LABEL or name in (DOT, DOTDOT):
                pinned.append(raw)
            else:
                movable.append(raw)

        def sort_key(raw: bytearray) -> tuple[int, str, bytes]:
            stored = bytes(raw[0:11])
            shown = display_name(stored)
            external = (key or {}).get(shown)
            return (
                0 if raw[11] & ATTR_DIRECTORY else 1,
                (external or shown).upper(),
                stored,
            )

        movable.sort(key=sort_key)
        rebuilt = bytearray()
        for raw in pinned + movable:
            rebuilt += raw
        self._store_dir(cluster, rebuilt.ljust(len(buffer), b"\x00"))

        for entry in self.list_dir(cluster):
            if entry.is_dir and entry.name not in (DOT, DOTDOT):
                self.sort_directories(key, entry.cluster)

    def verify(self) -> list[str]:
        """Read every file back through the written structures, returning failures."""
        failures = []
        for (parent, name), original in self._sources.items():
            got = self.read_file(name[:8].decode().rstrip(), name[8:11].decode().rstrip(), parent)
            if hashlib.sha256(got).hexdigest() != hashlib.sha256(original).hexdigest():
                failures.append(display_name(name))
        return sorted(failures)

    def corrupt_for_test(self, lba: int) -> None:
        offset = lba * image.SECTOR
        self._data[offset] ^= 0xFF

    def to_bytes(self) -> bytes:
        out = bytearray(self._data)
        for cluster, buffer in self._dir_buffers.items():
            chain = self._chain(cluster)
            cluster_bytes = image.SECTORS_PER_CLUSTER * image.SECTOR
            for index, part in enumerate(chain):
                start = self._cluster_lba(part) * image.SECTOR
                chunk = buffer[index * cluster_bytes : (index + 1) * cluster_bytes]
                out[start : start + cluster_bytes] = bytes(chunk).ljust(cluster_bytes, b"\x00")
        return bytes(out)
