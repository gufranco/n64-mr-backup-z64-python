import struct
from pathlib import Path

import pytest

MAGIC = {
    "z64": b"\x80\x37\x12\x40",
    "v64": b"\x37\x80\x40\x12",
    "n64": b"\x40\x12\x37\x80",
}


def byteswap(data: bytes, order: str) -> bytes:
    if order == "v64":
        return bytes(b for pair in zip(data[1::2], data[0::2], strict=True) for b in pair)
    if order == "n64":
        return b"".join(data[i : i + 4][::-1] for i in range(0, len(data), 4))
    return data


def make_rom(
    *,
    title: str = "SYNTHETIC TEST ROM",
    cart: str = "ZZ",
    region: str = "E",
    version: int = 0,
    crc1: int = 0x11223344,
    crc2: int = 0x55667788,
    size: int = 4 * 1024 * 1024,
    order: str = "z64",
    fill: bytes | None = None,
) -> bytes:
    head = bytearray(0x40)
    head[0:4] = MAGIC["z64"]
    struct.pack_into(">I", head, 0x04, 0x0000000F)
    struct.pack_into(">I", head, 0x10, crc1)
    struct.pack_into(">I", head, 0x14, crc2)
    head[0x20:0x34] = title.ljust(20).encode("ascii")[:20]
    head[0x3B] = ord("N")
    head[0x3C:0x3E] = cart.encode("ascii")[:2]
    head[0x3E] = ord(region)
    head[0x3F] = version
    tail = fill if fill is not None else bytes(size - 0x40)
    body = bytes(head) + tail[: size - 0x40].ljust(size - 0x40, b"\x00")
    return byteswap(body, order)


def entropy(length: int) -> bytes:
    """Deterministic high entropy filler, so checksum carry paths are exercised."""
    out = bytearray(length)
    state = 0x12345678
    for i in range(length):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        out[i] = (state >> 16) & 0xFF
    return bytes(out)


@pytest.fixture
def rom_factory():
    return make_rom


@pytest.fixture
def rom():
    return make_rom()


NTSC_LAN1_CTRL = 0x0000324E


def mode_entry(ctrl=NTSC_LAN1_CTRL, width=320, vsync=525, hsync=3093):
    """A VI mode struct as libultra lays it out: type, then nine comRegs words.

    Lives here rather than beside a vi test, because the video code moved to its
    own package and the tests left behind still need a ROM that carries a table
    the scanner will accept.
    """
    return struct.pack(
        ">IIIIIIIIII",
        0x00000001,
        ctrl,
        width,
        0x03E52239,
        vsync,
        hsync,
        0x0C150C15,
        0x006C02EC,
        0x00000200,
        0x00000000,
    )


def repo_root() -> Path:
    """The checkout this file belongs to, found rather than counted to.

    A test that walks up a fixed number of directories moves when the file
    moves, and the way it fails is silent: a path that no longer resolves makes
    a skip guard fire, so the suite goes green with the test never having run.
    That is what happened when these moved out of tests/ and beside the code.
    """
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("no pyproject.toml above this file, so the checkout root is unknown")
