"""The list of exactly which ROM belongs on which disk, keyed by content.

A collection is identified by filenames, and a filename is a label somebody
typed. Swap the bytes of `Banjo-Kazooie (USA) (Rev 1).z64` for the base revision
and every stage downstream still reads it as Rev 1: the scan verifies the dump's
own internal checksum and passes, the build writes it and passes, and the only
symptom is that the patch bound to Rev 1 silently fails to attach, because it
binds on a checksum pair that no longer matches.

A roster closes that. It records, per game, the digest of the bytes that were
actually used, the name they came from, and the 8.3 name written to the disk, so
a later build against a different pile of ROMs can be checked rather than
trusted.

Two strengths of claim live here and they must not be confused. When a patch
binds a game, the required revision is not an opinion: the patch carries the
target's checksum pair and will not apply to anything else, so `pinned_by` names
the patch and the entry is a hard requirement. Without a patch, the entry records
what the curated collection held and nothing more. Reporting the second as though
it were the first would be inventing a requirement no evidence supports.

SHA-256 decides. The checksum pair is the index, because it is what a patch binds
on and what a header carries, but it covers only 1 MiB starting at 0x1000, so two
dumps differing anywhere past that share it. Using it to decide equality would
accept a ROM that differs across the other 31 MiB of a large title.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

SCHEMA = 1


@dataclass(frozen=True)
class Entry:
    """One game, as content rather than as a filename."""

    disk: str
    source_name: str
    image_name: str
    sha256: str
    crc1: str
    crc2: str
    size: int
    game_code: str = ""
    title: str = ""
    pinned_by: tuple[str, ...] = ()

    @property
    def binding(self) -> str:
        return f"{self.crc1} {self.crc2}"

    @property
    def required(self) -> bool:
        """Whether a patch pins this exact revision, rather than curation choosing it."""
        return bool(self.pinned_by)


@dataclass(frozen=True)
class Roster:
    generated: str
    entries: tuple[Entry, ...] = ()
    schema: int = SCHEMA

    @property
    def by_sha256(self) -> dict[str, Entry]:
        return {one.sha256: one for one in self.entries}

    @property
    def by_binding(self) -> dict[str, Entry]:
        return {one.binding: one for one in self.entries}

    @property
    def pinned(self) -> tuple[Entry, ...]:
        return tuple(one for one in self.entries if one.required)


@dataclass(frozen=True)
class Finding:
    """One way a collection fails to match the roster."""

    kind: str
    entry: Entry
    detail: str = ""

    @property
    def blocking(self) -> bool:
        """Whether this finding means a build would produce the wrong disk.

        A missing game leaves a gap. A substituted one is worse, because the disk
        is written and looks complete. Both block; a name difference alone does
        not, since the roster keys on content and the build renames anyway.
        """
        return self.kind in {"missing", "wrong-revision", "wrong-bytes"}


@dataclass(frozen=True)
class Report:
    findings: tuple[Finding, ...] = ()
    matched: int = 0
    extra: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not any(one.blocking for one in self.findings)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path | str) -> Roster:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Roster(
        generated=str(raw.get("generated", "")),
        schema=int(raw.get("schema", SCHEMA)),
        entries=tuple(
            Entry(
                disk=str(one["disk"]),
                source_name=str(one["source_name"]),
                image_name=str(one["image_name"]),
                sha256=str(one["sha256"]),
                crc1=str(one["crc1"]),
                crc2=str(one["crc2"]),
                size=int(one["size"]),
                game_code=str(one.get("game_code", "")),
                title=str(one.get("title", "")),
                pinned_by=tuple(one.get("pinned_by", ())),
            )
            for one in raw.get("entries", ())
        ),
    )


def dumps(roster: Roster) -> str:
    """Serialise stably, so an unchanged collection rewrites an identical file."""
    body = {
        "schema": roster.schema,
        "generated": roster.generated,
        "entries": [
            {**asdict(one), "pinned_by": list(one.pinned_by)}
            for one in sorted(roster.entries, key=lambda e: (e.disk, e.source_name))
        ],
    }
    return json.dumps(body, indent=1, ensure_ascii=False) + "\n"


def check(roster: Roster, present: dict[str, bytes]) -> Report:
    """Compare a collection against the roster, keyed by content.

    `present` maps a filename to its bytes. Names are used only to report where a
    problem was found, never to decide whether it is the right game.
    """
    by_sha = {digest(blob): name for name, blob in present.items()}
    findings: list[Finding] = []
    matched = 0
    claimed: set[str] = set()

    for one in sorted(roster.entries, key=lambda e: (e.disk, e.source_name)):
        found = by_sha.get(one.sha256)
        if found is not None:
            matched += 1
            claimed.add(found)
            if found != one.source_name:
                findings.append(
                    Finding("renamed", one, f"present as {found}, roster says {one.source_name}")
                )
            continue

        impostor = next(
            (name for name, blob in present.items() if Path(name).name == one.source_name), None
        )
        if impostor is None:
            findings.append(Finding("missing", one, f"no file matches {one.sha256[:16]}"))
            continue

        claimed.add(impostor)
        kind = "wrong-revision" if one.required else "wrong-bytes"
        why = f"pinned by {', '.join(one.pinned_by)}" if one.required else "not pinned by any patch"
        findings.append(
            Finding(
                kind,
                one,
                f"{impostor} carries {digest(present[impostor])[:16]}, "
                f"roster expects {one.sha256[:16]}, {why}",
            )
        )

    return Report(
        findings=tuple(findings),
        matched=matched,
        extra=tuple(sorted(set(present) - claimed)),
    )


@dataclass(frozen=True)
class Placement:
    """One roster entry, and the file in the search area that satisfies it."""

    entry: Entry
    source: str


@dataclass(frozen=True)
class Resolution:
    """What a pile of ROMs, in any naming scheme, yields against the roster."""

    placements: tuple[Placement, ...] = ()
    missing: tuple[Entry, ...] = ()
    unused: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def missing_pinned(self) -> tuple[Entry, ...]:
        """The absences that break a patch, rather than merely leaving a gap."""
        return tuple(one for one in self.missing if one.required)


def resolve(known: Roster, found: dict[str, str]) -> Resolution:
    """Match the roster against candidates, keyed by digest.

    `found` maps a SHA-256 to the path that carries it. Names never take part in
    the decision, so a collection renamed by any convention, or dumped in one flat
    folder, resolves exactly as a curated tree does. A digest carried by several
    files is not an error: the roster names the game, the duplicates are the same
    bytes, and the first path in sorted order is taken so a rerun picks the same
    one.
    """
    placements, missing = [], []
    for one in sorted(known.entries, key=lambda e: (e.disk, e.source_name)):
        source = found.get(one.sha256)
        if source is None:
            missing.append(one)
        else:
            placements.append(Placement(one, source))

    taken = {p.source for p in placements}
    return Resolution(
        placements=tuple(placements),
        missing=tuple(missing),
        unused=tuple(sorted(set(found.values()) - taken)),
    )
