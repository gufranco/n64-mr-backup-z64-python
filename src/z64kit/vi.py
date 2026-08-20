"""Reading and changing the N64 Video Interface configuration inside a ROM.

The blur people dislike on real hardware is mostly not anti-aliasing. The VI has
a dedither filter, bit 16 of VI_CTRL, whose job is to reconstruct a 32-bit image
from a dithered 16-bit framebuffer, and it is that filter which softens the
picture. Edge anti-aliasing, bits 9:8, is a separate thing.

The two are coupled in hardware. The dedither filter only behaves correctly when
AA_MODE is REPLICATE or AA_ALWAYS, so libultra's `osViSetSpecialFeatures` forces
AA_MODE when the filter is switched on and restores it from the mode table when
switched off. That is why turning the filter off is the small, safe change and
clearing AA_MODE is the larger one that trades softness for shimmer.

Two places in a ROM decide this:

  the VI mode table, an array of OSViMode structs the game hands to the library,
  whose ctrl field holds the values above

  osViSetSpecialFeatures itself, which masks those bits at runtime according to
  what the game asks for

This module locates both by signature rather than by per-game offsets, so one
implementation covers any title built against the standard library. Every field
name and bit position below is from the published hardware documentation, and the
mode table signature was verified against retail ROMs before being relied on.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

CTRL_TYPE_MASK = 0x00003
CTRL_GAMMA_DITHER = 0x00004
CTRL_GAMMA = 0x00008
CTRL_DIVOT = 0x00010
CTRL_VBUS_CLOCK = 0x00020
CTRL_SERRATE = 0x00040
CTRL_TEST_MODE = 0x00080
CTRL_AA_MASK = 0x00300
CTRL_KILL_WE = 0x00800
CTRL_PIXEL_ADVANCE_MASK = 0x0F000
CTRL_DITHER_FILTER = 0x10000

AA_SHIFT = 8
AA_ALWAYS, AA_NEEDED, AA_RESAMPLE, AA_REPLICATE = 0, 1, 2, 3

AA_NAMES = {
    AA_ALWAYS: "AA_ALWAYS (anti-aliasing on)",
    AA_NEEDED: "AA_NEEDED (anti-aliasing on)",
    AA_RESAMPLE: "RESAMPLE (anti-aliasing off)",
    AA_REPLICATE: "REPLICATE (anti-aliasing off, no resample)",
}

PIXEL_TYPES = {0: "blank", 1: "reserved", 2: "16-bit", 3: "32-bit"}

VSYNC_BY_STANDARD = {525: "NTSC", 625: "PAL"}
PLAUSIBLE_WIDTHS = (256, 320, 384, 512, 576, 640)

ADDIU_ZERO = 0x24000000
ADDIU_OPCODE_MASK = 0xFC000000
ADDIU_OPCODE = 0x24000000

MASK_CONSTANTS = (
    ("gamma", 0xFFF7),
    ("gamma_dither", 0xFFFB),
    ("divot", 0xFFEF),
    ("antialias", 0xFCFF),
)
MASK_SEARCH_WINDOW = 256

MODE_ENTRY_STRIDE = 4


@dataclass(frozen=True)
class ViCtrl:
    raw: int

    @property
    def pixel_type(self) -> int:
        return self.raw & CTRL_TYPE_MASK

    @property
    def gamma_dither(self) -> bool:
        return bool(self.raw & CTRL_GAMMA_DITHER)

    @property
    def gamma(self) -> bool:
        return bool(self.raw & CTRL_GAMMA)

    @property
    def divot(self) -> bool:
        return bool(self.raw & CTRL_DIVOT)

    @property
    def serrate(self) -> bool:
        return bool(self.raw & CTRL_SERRATE)

    @property
    def aa_mode(self) -> int:
        return (self.raw & CTRL_AA_MASK) >> AA_SHIFT

    @property
    def antialiasing(self) -> bool:
        return self.aa_mode in (AA_ALWAYS, AA_NEEDED)

    @property
    def dither_filter(self) -> bool:
        return bool(self.raw & CTRL_DITHER_FILTER)

    @property
    def pixel_advance(self) -> int:
        return (self.raw & CTRL_PIXEL_ADVANCE_MASK) >> 12

    @property
    def aa_name(self) -> str:
        return AA_NAMES[self.aa_mode]

    @property
    def type_name(self) -> str:
        return PIXEL_TYPES[self.pixel_type]

    @property
    def blur_sources(self) -> tuple[str, ...]:
        out = []
        if self.dither_filter:
            out.append("dither filter")
        if self.divot:
            out.append("divot")
        if self.gamma_dither:
            out.append("gamma dither")
        return tuple(out)


def decode_ctrl(value: int) -> ViCtrl:
    return ViCtrl(raw=value & 0xFFFFFFFF)


def apply_changes(
    value: int,
    *,
    dither_filter: bool | None = None,
    divot: bool | None = None,
    gamma_dither: bool | None = None,
    gamma: bool | None = None,
    antialiasing: bool | None = None,
) -> int:
    """Set only the requested bits, leaving pixel type, serrate and timing alone."""
    out = value
    for flag, bit in (
        (dither_filter, CTRL_DITHER_FILTER),
        (divot, CTRL_DIVOT),
        (gamma_dither, CTRL_GAMMA_DITHER),
        (gamma, CTRL_GAMMA),
    ):
        if flag is True:
            out |= bit
        elif flag is False:
            out &= ~bit
    if antialiasing is False:
        out = (out & ~CTRL_AA_MASK) | (AA_RESAMPLE << AA_SHIFT)
    elif antialiasing is True:
        out = (out & ~CTRL_AA_MASK) | (AA_NEEDED << AA_SHIFT)
    return out & 0xFFFFFFFF


@dataclass(frozen=True)
class ModeEntry:
    ctrl_offset: int
    ctrl: int
    width: int
    vsync: int
    standard: str

    @property
    def decoded(self) -> ViCtrl:
        return decode_ctrl(self.ctrl)


def _plausible_ctrl(value: int) -> bool:
    if value >> 17:
        return False
    if value & CTRL_TYPE_MASK not in (2, 3):
        return False
    return not value & (CTRL_VBUS_CLOCK | CTRL_TEST_MODE | CTRL_KILL_WE)


VSYNC_OFFSET_FROM_CTRL = 12


def find_mode_tables(rom: bytes) -> tuple[ModeEntry, ...]:
    """Locate OSViMode entries by their ctrl, width and vSync fields together.

    A ctrl value alone is far too common to key on. Requiring a plausible width
    and a real video standard immediately after it is what makes the match safe.

    The search is anchored on vSync rather than on ctrl. vSync takes one of only
    two values in the whole address space, so scanning for it in C through
    bytes.find and then checking backwards is far cheaper than decoding every
    word in a 64 MiB ROM. The acceptance test is identical either way.
    """
    found: list[ModeEntry] = []
    for vsync, standard in VSYNC_BY_STANDARD.items():
        needle = struct.pack(">I", vsync)
        at = rom.find(needle)
        while at >= 0:
            ctrl_offset = at - VSYNC_OFFSET_FROM_CTRL
            if ctrl_offset >= 0 and ctrl_offset % 4 == 0 and ctrl_offset + 16 <= len(rom):
                ctrl = struct.unpack_from(">I", rom, ctrl_offset)[0]
                if _plausible_ctrl(ctrl):
                    width = struct.unpack_from(">I", rom, ctrl_offset + 4)[0]
                    if width in PLAUSIBLE_WIDTHS:
                        found.append(
                            ModeEntry(
                                ctrl_offset=ctrl_offset,
                                ctrl=ctrl,
                                width=width,
                                vsync=vsync,
                                standard=standard,
                            )
                        )
            at = rom.find(needle, at + 1)
    found.sort(key=lambda m: m.ctrl_offset)
    return tuple(found)


@dataclass(frozen=True)
class SpecialFeaturesSite:
    offset: int
    masks: dict[str, int]


def find_special_features(rom: bytes) -> tuple[SpecialFeaturesSite, ...]:
    """Locate osViSetSpecialFeatures by the four AND masks it applies in order.

    The routine clears GAMMA, GAMMA_DITHER, DIVOT and AA_MODE using immediate
    constants 0xFFF7, 0xFFFB, 0xFFEF and 0xFCFF. Those four appearing in order
    and close together is a strong signature for the library routine, and it is
    how the established tooling finds it too.
    """
    first_name, first_imm = MASK_CONSTANTS[0]
    sites: list[SpecialFeaturesSite] = []
    for offset in range(0, max(0, len(rom) - 4), 4):
        word = struct.unpack_from(">I", rom, offset)[0]
        if word & ADDIU_OPCODE_MASK != ADDIU_OPCODE or word & 0xFFFF != first_imm:
            continue
        masks = {first_name: offset}
        cursor = offset
        for name, imm in MASK_CONSTANTS[1:]:
            hit = None
            for probe in range(cursor + 4, min(len(rom) - 4, cursor + MASK_SEARCH_WINDOW), 4):
                candidate = struct.unpack_from(">I", rom, probe)[0]
                if candidate & ADDIU_OPCODE_MASK == ADDIU_OPCODE and candidate & 0xFFFF == imm:
                    hit = probe
                    break
            if hit is None:
                break
            masks[name] = hit
            cursor = hit
        if len(masks) == len(MASK_CONSTANTS):
            sites.append(SpecialFeaturesSite(offset=offset, masks=masks))
    return tuple(sites)


@dataclass(frozen=True)
class Report:
    mode_count: int
    ctrl_values: tuple[int, ...]
    antialiasing_on: int
    dither_filter_on: int
    divot_on: int
    gamma_dither_on: int
    standards: tuple[str, ...]
    special_features_sites: int

    @property
    def patchable(self) -> bool:
        return self.mode_count > 0

    @property
    def blurs(self) -> bool:
        return self.dither_filter_on > 0 or self.divot_on > 0


def audit(rom: bytes) -> Report:
    modes = find_mode_tables(rom)
    decoded = [m.decoded for m in modes]
    seen: list[int] = []
    for m in modes:
        if m.ctrl not in seen:
            seen.append(m.ctrl)
    standards: list[str] = []
    for m in modes:
        if m.standard not in standards:
            standards.append(m.standard)
    return Report(
        mode_count=len(modes),
        ctrl_values=tuple(seen),
        antialiasing_on=sum(1 for d in decoded if d.antialiasing),
        dither_filter_on=sum(1 for d in decoded if d.dither_filter),
        divot_on=sum(1 for d in decoded if d.divot),
        gamma_dither_on=sum(1 for d in decoded if d.gamma_dither),
        standards=tuple(standards),
        special_features_sites=len(find_special_features(rom)),
    )


def patch(
    rom: bytes,
    *,
    dither_filter: bool | None = None,
    divot: bool | None = None,
    gamma_dither: bool | None = None,
    gamma: bool | None = None,
    antialiasing: bool | None = None,
) -> tuple[bytes, int]:
    """Rewrite the ctrl field of every mode entry, touching nothing else."""
    out = bytearray(rom)
    changed = 0
    for entry in find_mode_tables(rom):
        new = apply_changes(
            entry.ctrl,
            dither_filter=dither_filter,
            divot=divot,
            gamma_dither=gamma_dither,
            gamma=gamma,
            antialiasing=antialiasing,
        )
        if new != entry.ctrl:
            struct.pack_into(">I", out, entry.ctrl_offset, new)
            changed += 1
    return bytes(out), changed


CHECKSUM_START = 0x1000
CHECKSUM_END = CHECKSUM_START + 0x100000
CRC1_OFFSET = 0x10
CRC2_OFFSET = 0x14

DEFAULT_RESEAL_CIC = "6102"


def reseal(rom: bytes, cic: str | None = None) -> bytes:
    """Recompute and write the header checksum.

    Almost every video mode table sits inside the region the checksum covers, so
    editing one invalidates it. A retail cartridge with a bad checksum is
    rejected by the lockout chip, which means an unsealed patch produces a ROM
    that will not boot on real hardware even though it looks fine in an emulator
    that skips the check. Resealing is therefore not optional.
    """
    from .rom import checksum

    if len(rom) < CHECKSUM_END:
        raise ValueError(
            f"data is too short to checksum, need {CHECKSUM_END} bytes, got {len(rom)}"
        )
    chosen = cic or checksum.verify(rom)[1] or DEFAULT_RESEAL_CIC
    pair = checksum.compute(rom, chosen)
    out = bytearray(rom)
    struct.pack_into(">I", out, CRC1_OFFSET, pair[0])
    struct.pack_into(">I", out, CRC2_OFFSET, pair[1])
    return bytes(out)


@dataclass(frozen=True)
class PatchResult:
    applied: bool
    reason: str
    data: bytes = b""
    modes_changed: int = 0
    changes: tuple[tuple[int, int, int], ...] = ()
    cic: str | None = None


NO_CHANGE_NEEDED = "every mode already has the requested settings"


def safe_patch(
    rom: bytes,
    *,
    antialiasing: bool | None = None,
    divot: bool | None = None,
    gamma_dither: bool | None = None,
    gamma: bool | None = None,
) -> PatchResult:
    """Edit the video mode table, then prove the result before returning it.

    The dither filter is deliberately absent from the arguments. It is never
    present in a mode table, in any of the retail ROMs surveyed, because the game
    switches it on at runtime through osViSetSpecialFeatures. Offering a switch
    that silently does nothing would be worse than not offering one, so removing
    the filter is left to a separate code-editing path that does not exist yet.

    Every guard below refuses rather than guesses:

      the ROM must carry a mode table this code can prove is one
      its existing checksum must validate, otherwise the boot chip is unknown
      and the result could not be resealed correctly
      at least one bit must actually change, so a no-op is reported as such
      the recomputed checksum must validate before the data is handed back
    """
    from .rom import checksum

    requested = {
        "antialiasing": antialiasing,
        "divot": divot,
        "gamma_dither": gamma_dither,
        "gamma": gamma,
    }
    if all(v is None for v in requested.values()):
        return PatchResult(False, "nothing requested")

    entries = find_mode_tables(rom)
    if not entries:
        return PatchResult(False, "no video mode table could be proven present")

    valid, cic = checksum.verify(rom)
    if not valid:
        return PatchResult(
            False,
            "the existing checksum does not validate, so the boot chip is unknown "
            "and the result could not be resealed correctly",
        )

    changes: list[tuple[int, int, int]] = []
    out = bytearray(rom)
    for entry in entries:
        new = apply_changes(
            entry.ctrl,
            divot=divot,
            gamma_dither=gamma_dither,
            gamma=gamma,
            antialiasing=antialiasing,
        )
        if new != entry.ctrl:
            struct.pack_into(">I", out, entry.ctrl_offset, new)
            changes.append((entry.ctrl_offset, entry.ctrl, new))

    if not changes:
        return PatchResult(False, NO_CHANGE_NEEDED)

    sealed = reseal(bytes(out), cic)

    revalidated, after_cic = checksum.verify(sealed)
    if not revalidated or after_cic != cic:
        return PatchResult(
            False, "the recomputed checksum failed to validate, refusing to return the data"
        )

    for offset, _, expected in changes:
        if struct.unpack_from(">I", sealed, offset)[0] != expected:
            return PatchResult(False, f"the edit at 0x{offset:06X} did not take, refusing")

    return PatchResult(
        applied=True,
        reason=f"{len(changes)} of {len(entries)} mode entries changed",
        data=sealed,
        modes_changed=len(changes),
        changes=tuple(changes),
        cic=cic,
    )


IPS_MAX_OFFSET = 0xFFFFFF


def make_ips(
    changes: list[tuple[int, int, int]] | tuple[tuple[int, int, int], ...],
    checksum_words: bytes | None = None,
) -> bytes:
    """Express the same edits as an IPS patch, leaving the ROM file untouched.

    Useful when the ROM must stay byte-identical on disk and the change is
    applied by some other tool. Note that the unit itself cannot consume this as
    a runtime patch alongside a save fix, because it matches one external patch
    per ROM by filename, so the two would compete for the same slot.

    When `checksum_words` is given, the two header checksum words are included as
    a record, since editing a mode table almost always invalidates them.
    """
    out = bytearray(b"PATCH")
    records = [(offset, struct.pack(">I", new)) for offset, _, new in changes]
    if checksum_words is not None:
        records.append((CRC1_OFFSET, bytes(checksum_words[CRC1_OFFSET : CRC1_OFFSET + 8])))
    for offset, payload in records:
        if offset > IPS_MAX_OFFSET:
            raise ValueError(
                f"offset 0x{offset:X} is beyond what IPS can address, 0x{IPS_MAX_OFFSET:X}"
            )
        out += offset.to_bytes(3, "big")
        out += len(payload).to_bytes(2, "big")
        out += payload
    return bytes(out + b"EOF")
