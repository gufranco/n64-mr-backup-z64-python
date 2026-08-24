"""What the unit can and cannot do with a given title.

Three limits matter, and they rank in this order.

A ROM larger than the unit's 256 Mbit of memory cannot be loaded at all. No
patch, BIOS or setting changes that, so it outranks every other consideration.

A save chip the unit does not emulate, 16 Kbit EEPROM or FlashRAM, means the
save is written to the chip of the cartridge physically in the slot instead. A
save fix patch can sometimes redirect it onto a chip that is emulated; where no
such patch exists, only a donor cartridge carrying the right chip will do.

A lockout chip other than the common one still runs, but the per game Boot Chip
setting has to be changed, and for the partially emulated chip two other options
must be turned off.

Every rule here is loaded from data carrying its own source, so a claim can be
traced back rather than taken on trust.
"""

from __future__ import annotations

import collections
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_RULES_PATH = Path(__file__).parent / "data" / "compat.json"

DEFAULT_BOOT_CHIPS = frozenset({"6102", "7101"})

STATUS_NO_SAVE_DATA = "no-save-data"
STATUS_NATIVE = "native"
STATUS_PATCHED = "patched"
STATUS_BIOS_CRACK = "bios-crack"
STATUS_NEEDS_DONOR = "needs-donor"
STATUS_TOO_LARGE = "too-large"


@dataclass(frozen=True)
class Candidate:
    key: str
    title: str
    save: str = "none"
    cic: str = "6102"
    size: int = 0
    has_patch: bool = False
    has_bios_crack: bool = False


@dataclass(frozen=True)
class Verdict:
    key: str
    title: str
    status: str
    blocked: bool
    donor: str | None = None
    boot_chip_action: str = ""
    will_not_boot: bool = False
    note: str = ""


@dataclass(frozen=True)
class Summary:
    counts: dict[str, int] = field(default_factory=dict)
    donors_needed: tuple[str, ...] = ()
    non_default_boot_chip: int = 0
    oversized: tuple[str, ...] = ()
    will_not_boot: tuple[str, ...] = ()


def _normalise(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def _matches(title: str, keys: Iterable[str]) -> bool:
    haystack = _normalise(title)
    return any(_normalise(k) in haystack for k in keys if k)


class Rules:
    def __init__(self, raw: dict[str, Any]) -> None:
        self._raw = raw
        unit = raw["unit"]
        self.memory_mib: int = unit["memory_mib"]
        self.memory_bytes: int = unit["memory_mib"] * 1024 * 1024
        self.memory_source: str = unit["memory_source"]
        self.rom_extensions: frozenset[str] = frozenset(unit["rom_extensions"])
        self.patch_extensions: frozenset[str] = frozenset(unit["patch_extensions"])
        self.aux_extensions: frozenset[str] = frozenset(unit["aux_extensions"])
        self.unsupported_rom_extensions: frozenset[str] = frozenset(
            unit["unsupported_rom_extensions"]
        )
        self.save_hardware: dict[str, Any] = raw["save_hardware"]
        self.boot_chips: dict[str, Any] = raw["boot_chips"]
        self.boot_cartridge: dict[str, Any] = raw["boot_cartridge"]
        self.donors: dict[str, dict[str, object]] = raw["donor_cartridges"]
        self.donor_source: str = raw["donor_source"]
        self.one_save_per_cartridge: dict[str, Any] = raw["one_save_per_cartridge"]
        self._no_boot = raw["will_not_boot_without_donor"]
        self.oversized: tuple[dict[str, Any], ...] = tuple(raw["oversized_titles"])

    def is_emulated(self, save: str) -> bool:
        return bool(self.save_hardware.get(save, {}).get("emulated", True))

    def donor_for(self, save: str) -> str | None:
        return str(self.save_hardware.get(save, {}).get("donor") or "") or None

    def save_label(self, save: str) -> str:
        return str(self.save_hardware.get(save, {}).get("label", save))

    def boot_chip_action(self, cic: str) -> str:
        if cic in DEFAULT_BOOT_CHIPS:
            return ""
        entry = self.boot_chips.get(cic)
        if entry is None:
            return f"Boot chip {cic} is not in the known set, test this title first"
        return str(entry["note"])

    def will_not_boot(self, title: str) -> bool:
        return any(_matches(title, [e["title"]]) for e in self._no_boot)

    def donor_label(self, donor: str) -> str:
        return str(self.donors.get(donor, {}).get("label", donor))

    def donor_reference(self, donor: str) -> str:
        return str(self.donors.get(donor, {}).get("reference", ""))


def load_rules(path: Path | str = DEFAULT_RULES_PATH) -> Rules:
    return Rules(json.loads(Path(path).read_text(encoding="utf-8")))


def classify(candidate: Candidate, rules: Rules) -> Verdict:
    action = rules.boot_chip_action(candidate.cic)

    if candidate.size > rules.memory_bytes:
        return Verdict(
            key=candidate.key,
            title=candidate.title,
            status=STATUS_TOO_LARGE,
            blocked=True,
            boot_chip_action=action,
            note=(
                f"{candidate.size / 1024 / 1024:.0f} MiB exceeds the "
                f"{rules.memory_mib} MiB the unit holds, so it cannot load from disk"
            ),
        )

    no_boot = rules.will_not_boot(candidate.title)

    if candidate.save == "none":
        status, blocked, donor = STATUS_NO_SAVE_DATA, False, None
    elif rules.is_emulated(candidate.save):
        status, blocked, donor = STATUS_NATIVE, False, None
    elif candidate.has_patch:
        status, blocked, donor = STATUS_PATCHED, False, None
    elif candidate.has_bios_crack:
        status, blocked, donor = STATUS_BIOS_CRACK, False, None
    else:
        status = STATUS_NEEDS_DONOR
        blocked = True
        donor = rules.donor_for(candidate.save)

    return Verdict(
        key=candidate.key,
        title=candidate.title,
        status=status,
        blocked=blocked or no_boot,
        donor=donor or (rules.donor_for(candidate.save) if no_boot else None),
        boot_chip_action=action,
        will_not_boot=no_boot,
        note="" if not no_boot else "will not boot at all without the matching cartridge",
    )


def summarise(candidates: list[Candidate], rules: Rules) -> Summary:
    verdicts = [classify(c, rules) for c in candidates]
    counts = collections.Counter(v.status for v in verdicts)
    donors: list[str] = []
    for verdict in verdicts:
        if verdict.donor and verdict.donor not in donors:
            donors.append(verdict.donor)
    return Summary(
        counts=dict(counts),
        donors_needed=tuple(donors),
        non_default_boot_chip=sum(1 for v in verdicts if v.boot_chip_action),
        oversized=tuple(v.title for v in verdicts if v.status == STATUS_TOO_LARGE),
        will_not_boot=tuple(v.title for v in verdicts if v.will_not_boot),
    )


def donor_save_tag(rules: Rules, donor: str) -> str:
    """The save-chip tag this donor carries, in the catalogue's vocabulary.

    The label a reader sees and the tag a catalogue keys on are different words
    for one chip, so the mapping is data beside the donor rather than a lookup
    table in code that would drift from it.
    """
    entry = rules.donors.get(donor, {})
    tag = entry.get("save_tag", "")
    return str(tag) if isinstance(tag, str) else ""


def donor_also_carrying(rules: Rules, donor: str, chip: str) -> tuple[str, ...]:
    """Cartridges that carry this save chip and the wanted boot chip at once."""
    entry = rules.donors.get(donor, {})
    shared = entry.get(f"also_carrying_{chip}", ())
    return tuple(str(one) for one in shared) if isinstance(shared, list) else ()


def _join_sentences(parts: list[str]) -> str:
    """Join clauses into sentences, each capitalised, with no doubled full stop."""
    cleaned = [p.strip().rstrip(".").strip() for p in parts if p and p.strip()]
    if not cleaned:
        return ""
    return ". ".join(p[0].upper() + p[1:] if p else p for p in cleaned) + "."


def requirement_for(verdict: Verdict, rules: Rules) -> str:
    """One line saying what this game still needs, in words a buyer can act on.

    A flag in a table says something is wrong. Only a sentence says which
    cartridge to buy or put in the slot, which is what the reader of a printed
    catalogue actually has to decide.
    """
    parts: list[str] = []
    if verdict.status == STATUS_TOO_LARGE:
        parts.append("too large for the unit to load at all")
        if verdict.note:
            parts.append(verdict.note)
        return _join_sentences(parts)

    if verdict.will_not_boot:
        parts.append("will not boot without a donor cartridge")

    chip = ""
    if verdict.boot_chip_action:
        found = [w for w in verdict.boot_chip_action.replace(",", " ").split() if w.isdigit()]
        chip = found[0] if found else ""

    if verdict.donor:
        label = rules.donor_label(verdict.donor)
        reference = rules.donor_reference(verdict.donor)
        shared = donor_also_carrying(rules, verdict.donor, chip) if chip else ()
        sentence = f"needs a {label}"
        if shared:
            sentence += (
                f", and {shared[0]} carries both that and the {chip} boot chip, "
                "so one cartridge covers both"
            )
        elif reference:
            sentence += f", for example {reference}"
        parts.append(sentence)
        parts.append("the save is written to whichever cartridge is inserted")

    if verdict.boot_chip_action and not (
        verdict.donor and chip and donor_also_carrying(rules, verdict.donor, chip)
    ):
        parts.append(verdict.boot_chip_action)

    return _join_sentences(parts)
