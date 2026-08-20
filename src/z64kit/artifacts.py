"""Identification of user supplied artifacts.

This project never distributes ROMs, patch payloads, firmware or save data. It
distributes their identity, so a user can confirm the file they already hold is
the right one and the tool can refuse to act on the wrong one.

SHA-256 is the only value that decides acceptance. Size and CRC32 exist to make
a near miss cheap to detect and to cross reference against public databases.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = 1
DEFAULT_MANIFEST_PATH = Path(__file__).parent / "data" / "artifacts.manifest.json"

APS_MAGIC = b"APS10"
APS_TARGET_CRC1 = 0x3D
APS_TARGET_CRC2 = 0x41
APS_MIN_LENGTH = 0x45

FORBIDDEN_KEYS = ("payload", "data", "bytes", "content")


class ManifestError(ValueError):
    """Raised when a manifest is malformed or carries content it must not."""


@dataclass(frozen=True)
class ArtifactEntry:
    name: str
    kind: str
    filename: str
    size: int
    sha256: str
    crc32: str
    provenance: str
    target_crc1: str | None = None
    target_crc2: str | None = None
    game: str | None = None
    description: str | None = None
    companions: tuple[str, ...] = ()
    region: str | None = None
    game_code: str | None = None
    checksum_after: str | None = None
    in_patch_database: bool = False


@dataclass(frozen=True)
class Manifest:
    by_sha256: dict[str, ArtifactEntry] = field(default_factory=dict)
    by_size: dict[int, tuple[ArtifactEntry, ...]] = field(default_factory=dict)

    def entries(self) -> tuple[ArtifactEntry, ...]:
        return tuple(self.by_sha256.values())


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    reason: str = ""


def _entry_from_dict(item: dict) -> ArtifactEntry:
    for key in FORBIDDEN_KEYS:
        if key in item:
            raise ManifestError(
                f"entry {item.get('name', '?')!r} carries a {key!r} field. "
                "Manifests hold identity only and must never hold payload bytes."
            )
    try:
        return ArtifactEntry(
            name=item["name"],
            kind=item["kind"],
            filename=item["filename"],
            size=int(item["size"]),
            sha256=item["sha256"].lower(),
            crc32=item["crc32"].lower(),
            provenance=item["provenance"],
            target_crc1=item.get("target_crc1"),
            target_crc2=item.get("target_crc2"),
            game=item.get("game"),
            description=item.get("description"),
            companions=tuple(item.get("companions", ())),
            region=item.get("region"),
            game_code=item.get("game_code"),
            checksum_after=item.get("checksum_after"),
            in_patch_database=bool(item.get("in_patch_database", False)),
        )
    except KeyError as exc:
        raise ManifestError(f"entry is missing required field {exc.args[0]!r}") from exc


def load_manifest(path: Path | str) -> Manifest:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = raw.get("schema")
    if schema != SCHEMA_VERSION:
        raise ManifestError(
            f"manifest schema {schema!r} is not supported, this build understands {SCHEMA_VERSION}"
        )
    by_sha: dict[str, ArtifactEntry] = {}
    by_size: dict[int, list[ArtifactEntry]] = {}
    for item in raw.get("entries", []):
        entry = _entry_from_dict(item)
        by_sha[entry.sha256] = entry
        by_size.setdefault(entry.size, []).append(entry)
    return Manifest(by_sha256=by_sha, by_size={k: tuple(v) for k, v in by_size.items()})


def load_default_manifest() -> Manifest:
    return load_manifest(DEFAULT_MANIFEST_PATH)


def identify(data: bytes, manifest: Manifest) -> ArtifactEntry | None:
    return manifest.by_sha256.get(hashlib.sha256(data).hexdigest())


def verify(data: bytes, entry: ArtifactEntry) -> VerifyResult:
    if len(data) != entry.size:
        return VerifyResult(
            False,
            f"size is {len(data)} bytes, {entry.name} is {entry.size} bytes",
        )
    digest = hashlib.sha256(data).hexdigest()
    if digest != entry.sha256:
        return VerifyResult(
            False,
            f"sha256 is {digest}, {entry.name} is {entry.sha256}",
        )
    return VerifyResult(True)


def diagnose(data: bytes, manifest: Manifest) -> str:
    known = identify(data, manifest)
    if known is not None:
        return f"recognised as {known.name}, {known.description or known.kind}"

    digest = hashlib.sha256(data).hexdigest()
    lines = [
        f"not recognised: {len(data)} bytes, sha256 {digest}",
    ]
    same_size = manifest.by_size.get(len(data), ())
    if same_size:
        names = ", ".join(e.name for e in same_size)
        lines.append(f"the size matches {names}, so this may be a modified or truncated copy")
    else:
        lines.append("no known artifact has this size")
    lines.append("search the sha256 above to find what this file actually is")
    return "\n".join(lines)


def _aps_target_checksums(data: bytes) -> tuple[str | None, str | None]:
    if len(data) < APS_MIN_LENGTH or data[:5] != APS_MAGIC:
        return None, None
    crc1 = struct.unpack_from(">I", data, APS_TARGET_CRC1)[0]
    crc2 = struct.unpack_from(">I", data, APS_TARGET_CRC2)[0]
    return f"{crc1:08X}", f"{crc2:08X}"


def build_entry(
    *,
    name: str,
    kind: str,
    filename: str,
    data: bytes,
    provenance: str,
    game: str | None = None,
    description: str | None = None,
    companions: tuple[str, ...] = (),
) -> ArtifactEntry:
    crc1, crc2 = _aps_target_checksums(data)
    return ArtifactEntry(
        name=name,
        kind=kind,
        filename=filename,
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        crc32=f"{zlib.crc32(data):08x}",
        provenance=provenance,
        target_crc1=crc1,
        target_crc2=crc2,
        game=game,
        description=description,
        companions=companions,
    )


def entry_to_dict(entry: ArtifactEntry) -> dict:
    out = {
        "name": entry.name,
        "kind": entry.kind,
        "filename": entry.filename,
        "size": entry.size,
        "sha256": entry.sha256,
        "crc32": entry.crc32,
        "provenance": entry.provenance,
    }
    if entry.target_crc1:
        out["target_crc1"] = entry.target_crc1
        out["target_crc2"] = entry.target_crc2
    if entry.game:
        out["game"] = entry.game
    if entry.description:
        out["description"] = entry.description
    if entry.companions:
        out["companions"] = list(entry.companions)
    if entry.region:
        out["region"] = entry.region
    if entry.game_code:
        out["game_code"] = entry.game_code
    if entry.checksum_after:
        out["checksum_after"] = entry.checksum_after
    if entry.in_patch_database:
        out["in_patch_database"] = True
    return out


def write_manifest(entries: list[ArtifactEntry], path: Path | str, note: str) -> None:
    payload = {
        "schema": SCHEMA_VERSION,
        "note": note,
        "entries": [entry_to_dict(e) for e in sorted(entries, key=lambda e: e.name)],
    }
    Path(path).write_text(
        json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )


FOLDER_KINDS = ("patch", "crack", "save", "header", "patch-db")
PATCH_DATABASE = "z64patch.dat"
FOLDER_OWN_FILES = ("README.md", ".gitignore")
FOLDER_NAME = "patches"


@dataclass(frozen=True)
class FolderReport:
    present: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    wrong: dict[str, str] = field(default_factory=dict)
    misnamed: dict[str, str] = field(default_factory=dict)
    unknown: tuple[str, ...] = ()
    needed: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing and not self.wrong

    @property
    def needed_present(self) -> tuple[str, ...]:
        """Verified files this collection actually asked for.

        `present` counts everything that verified, including files kept for games
        the reader does not own. Only this narrower count belongs in a ratio
        against `needed`.
        """
        wanted = set(self.needed)
        return tuple(name for name in self.present if name in wanted)


def folder_entries(manifest: Manifest) -> tuple[ArtifactEntry, ...]:
    """The files that must actually be supplied, in a stable order.

    A patch the unit already finds inside `z64patch.dat` is deliberately absent
    here. Asking for it separately would mean obtaining seventy-five files to get
    what one file already contains, and the unit reads that one file itself.
    """
    chosen = [e for e in manifest.entries() if e.kind in FOLDER_KINDS and not e.in_patch_database]
    return tuple(sorted(chosen, key=lambda e: e.filename))


def database_contents(manifest: Manifest) -> tuple[ArtifactEntry, ...]:
    """What `z64patch.dat` already covers, listed so a reader can confirm it."""
    chosen = [e for e in manifest.entries() if e.in_patch_database]
    return tuple(sorted(chosen, key=lambda e: e.filename))


def other_entries(manifest: Manifest) -> tuple[ArtifactEntry, ...]:
    chosen = [e for e in manifest.entries() if e.kind not in FOLDER_KINDS]
    return tuple(sorted(chosen, key=lambda e: e.filename))


def required_for(manifest: Manifest, checksums: set[tuple[str, str]]) -> set[str]:
    """The files a collection actually needs, given the checksums it holds.

    The manifest describes every patch known for the platform, and most of them
    are for games the reader does not own. Reporting all of those as missing buries
    the handful that matter, so a caller that knows the collection passes its
    checksum pairs and gets back only the relevant filenames, companions included.
    """
    pairs = {(a.upper(), b.upper()) for a, b in checksums}
    out: set[str] = set()
    for entry in manifest.entries():
        if not (entry.target_crc1 and entry.target_crc2):
            continue
        if (entry.target_crc1.upper(), entry.target_crc2.upper()) not in pairs:
            continue
        # a patch the database already carries needs no separate copy, but a save
        # that ships beside it is a real file the disk still has to hold
        if not entry.in_patch_database:
            out.add(entry.filename)
        out.update(name for name in entry.companions if not _in_database(manifest, name))
    out.add(PATCH_DATABASE)
    return out


def _in_database(manifest: Manifest, filename: str) -> bool:
    for entry in manifest.entries():
        if entry.filename == filename:
            return entry.in_patch_database
    return False


def inspect_folder(
    folder: Path | str, manifest: Manifest, required: set[str] | None = None
) -> FolderReport:
    """Compare a folder against the manifest, deciding on SHA-256 alone.

    A missing folder is reported as everything missing rather than raised, because
    the answer a caller wants is the same either way: none of it is here yet.

    `required` narrows what counts as missing. A file present but wrong is always
    reported, whether or not this collection needs it, because a wrong file is a
    problem regardless of who wants it.
    """
    root = Path(folder)
    wanted = {e.filename: e for e in folder_entries(manifest)}
    # a file the database already carries is still a file this project knows. Finding
    # one loose in the folder is harmless, so it is verified rather than called unknown
    known = {e.filename: e for e in manifest.entries()}
    needed = set(wanted) if required is None else set(required) & set(wanted)
    present: list[str] = []
    missing: list[str] = []
    wrong: dict[str, str] = {}
    misnamed: dict[str, str] = {}
    unknown: list[str] = []

    on_disk = sorted(p for p in root.iterdir() if p.is_file()) if root.is_dir() else []

    for path in on_disk:
        if path.name in FOLDER_OWN_FILES:
            continue
        data = path.read_bytes()
        recognised = identify(data, manifest)
        if recognised is not None and recognised.filename != path.name:
            misnamed[path.name] = recognised.filename
            continue
        entry = wanted.get(path.name) or known.get(path.name)
        if entry is None:
            unknown.append(path.name)
            continue
        result = verify(data, entry)
        if result.ok:
            present.append(path.name)
        else:
            wrong[path.name] = result.reason

    for name in needed:
        if name not in present and name not in wrong:
            missing.append(name)

    return FolderReport(
        present=tuple(sorted(present)),
        missing=tuple(sorted(missing)),
        wrong=wrong,
        misnamed=misnamed,
        unknown=tuple(sorted(unknown)),
        needed=tuple(sorted(needed)),
    )


def owning_patch(manifest: Manifest, filename: str) -> ArtifactEntry | None:
    """The patch that lists `filename` as a companion, if any.

    A save file carries no game name of its own in the manifest, because it is
    meaningless apart from the patch it ships with. Resolving the owner is what
    lets a row say which game it belongs to instead of leaving the column blank.
    """
    for entry in manifest.entries():
        if filename in entry.companions:
            return entry
    return None


def _folder_row(entry: ArtifactEntry, manifest: Manifest) -> str:
    if entry.target_crc1 and entry.target_crc2:
        target = f"`{entry.target_crc1}` / `{entry.target_crc2}`"
    else:
        target = "not bound to a checksum"

    game = entry.game or ""
    purpose = entry.description or entry.kind
    if not game:
        owner = owning_patch(manifest, entry.filename)
        if owner is not None:
            game = owner.game or ""
            purpose = f"Save data used by `{owner.filename}`"

    return f"| `{entry.filename}` | {game} | {purpose} | {entry.size:,} | {target} |"


def render_folder_readme(manifest: Manifest) -> str:
    """Write the folder's documentation from the manifest, so the two cannot diverge.

    Nothing here says where to obtain a file. The point of the document is to let
    somebody confirm that what they already have is the right thing, and to name
    exactly what is wrong when it is not.

    Rows are grouped by what a file does rather than listed flat, because the
    reader's question is almost never "what is the digest of this byte count", it
    is "do I need this at all".
    """
    wanted = folder_entries(manifest)
    others = other_entries(manifest)
    by_kind = {kind: [e for e in wanted if e.kind == kind] for kind in FOLDER_KINDS}
    games = len({e.game_code for e in wanted if e.game_code})

    lines = [
        "# Supplied artifacts",
        "",
        "Files this project needs, cannot distribute, and cannot regenerate. Put them in",
        "this folder. Everything here is ignored by git except this document and the ignore",
        "rules beside it, so a payload dropped in cannot be committed by accident.",
        "",
        "This file is generated from the manifest the code checks against. Do not edit it by",
        "hand: run `z64kit artifacts --write-readme` after the manifest changes.",
        "",
        "## You almost certainly do not need all of these",
        "",
        f"Beyond the patch database, only {len(wanted) - 1} files are ever needed, covering",
        f"{games} games. Which of those matter depends entirely on which games you own, so",
        "ask the tool rather than reading the whole table:",
        "",
        "```",
        "z64kit artifacts --source YOUR-GAME-FOLDER",
        "```",
        "",
        "That reports only the files the games in that folder actually need, and says which",
        "are missing, which are present but wrong, and which are correct under the wrong",
        "name. Without `--source` every file below is treated as required.",
        "",
        "## Scope",
        "",
        "| | |",
        "|:--|:--|",
        "| Region | USA releases only |",
        f"| Games needing a separate file | {games} |",
        f"| Files expected here | {len(wanted)} |",
        f"| Patches the database already covers | {len(database_contents(manifest))} |",
        "| Filenames | lowercase throughout |",
        "| Decides acceptance | SHA-256, and nothing else |",
        "",
        "Size is a cheap pre-filter and CRC32 is there so a file can be cross-referenced",
        "against a public database. Neither one accepts or rejects anything.",
        "",
        "## What the checksum column means",
        "",
        "Every patch was applied to the ROM it targets, and the header checksum of the",
        "result was then recomputed.",
        "",
        "| Value | Meaning |",
        "|:------|:--------|",
        "| `valid-6102` | The patched ROM verifies under boot chip 6102 |",
        "| `no boot chip` | The patched ROM verifies under no boot chip this tool knows |",
        "| `not checked` | The ROM it targets was not available to test against |",
        "",
        "A `no boot chip` result is a measurement, not a verdict. The unit emulates the",
        "boot chip rather than holding a real one, so whether it enforces that check is",
        "untested on hardware here. Treat those patches as unverified rather than broken.",
        "",
        "Even a patch that verifies is only proven to start. A protection check that lets",
        "the game boot and then degrades play later cannot be detected by any test in this",
        "project, and that failure mode was real on this platform.",
        "",
    ]

    database = next((e for e in wanted if e.kind == "patch-db"), None)
    if database is not None:
        covered = database_contents(manifest)
        lines += [
            "## Start with one file",
            "",
            f"`{database.filename}` is the unit's own patch database, and it already covers",
            f"{len(covered)} of the patches known for this platform. The unit reads it",
            "directly and finds the right patch inside it, so you supply one file instead of",
            "dozens.",
            "",
            "| | |",
            "|:--|:--|",
            f"| File | `{database.filename}` |",
            f"| Bytes | {database.size:,} |",
            f"| SHA-256 | `{database.sha256}` |",
            "",
            "**It has to be on every disk, in the root, beside the games.** The tool copies it",
            "there for you whenever it is in this folder, and says so when it is not. Without",
            "it a game that needs a patch loads unpatched, which usually means it cannot save",
            "and sometimes means it will not boot at all.",
            "",
            "It costs about 0.6 MB of a 100 MB disk and takes nothing away from the games: a",
            "disk holds 23 of them at 4 MB granularity and still has roughly 3 MB spare.",
            "",
        ]

    sections = [
        (
            "patch-db",
            "The patch database",
            "One file the unit reads itself. It belongs in the root of every disk.",
        ),
        (
            "patch",
            "Save and boot fixes",
            "Without one of these the game either cannot write a save or will not start.",
        ),
        (
            "crack",
            "Copy protection removal",
            "These games check for a real cartridge and refuse to run from a disk.",
        ),
        ("save", "Save data", "Shipped alongside a patch, and meaningless without it."),
        (
            "header",
            "Target ROM headers",
            "64 bytes identifying the ROM a patch belongs to. Only a non-APS patch needs "
            "one: an APS carries its own binding at a fixed offset.",
        ),
    ]

    for kind, title, blurb in sections:
        rows = by_kind.get(kind) or []
        if not rows:
            continue
        lines += [f"## {title}", "", f"{blurb}", "", f"{len(rows)} files.", ""]
        if kind == "patch-db":
            lines += ["| File | Bytes |", "|:-----|------:|"]
            lines += [f"| `{e.filename}` | {e.size:,} |" for e in rows]
        elif kind == "header":
            lines += ["| File | Belongs to |", "|:-----|:-----------|"]
            owners = {}
            for entry in wanted:
                for companion in entry.companions:
                    owners[companion] = entry.filename
            lines += [f"| `{e.filename}` | `{owners.get(e.filename, 'its patch')}` |" for e in rows]
        else:
            lines += [
                "| File | Game | Bytes | Target CRC1 / CRC2 | Checksum after |",
                "|:-----|:-----|------:|:-------------------|:---------------|",
            ]
            for entry in rows:
                game = entry.game or ""
                if not game:
                    owner = owning_patch(manifest, entry.filename)
                    game = (owner.game or "") if owner else ""
                if entry.target_crc1 and entry.target_crc2:
                    target = f"`{entry.target_crc1}` / `{entry.target_crc2}`"
                else:
                    target = "matched by its own digest"
                after = {
                    None: "",
                    "not-checked": "not checked",
                    "could-not-apply": "would not apply",
                    "matches-no-boot-chip": "no boot chip",
                }.get(entry.checksum_after, entry.checksum_after or "")
                lines.append(
                    f"| `{entry.filename}` | {game} | {entry.size:,} | {target} | {after} |"
                )
        lines.append("")

    covered = database_contents(manifest)
    if covered:
        lines += [
            "## Already inside the patch database",
            "",
            f"You do not need separate copies of these {len(covered)} files. They are listed",
            f"so you can confirm that `{PATCH_DATABASE}` covers the game you care about, and",
            "so a copy found loose somewhere can be identified. Supplying the database is",
            "enough.",
            "",
            "| File | Game | Checksum after |",
            "|:-----|:-----|:---------------|",
        ]
        for entry in covered:
            game = entry.game or ""
            if not game:
                owner = owning_patch(manifest, entry.filename)
                game = (owner.game or "") if owner else ""
            after = {
                None: "",
                "not-checked": "not checked",
                "matches-no-boot-chip": "no boot chip",
            }.get(entry.checksum_after, entry.checksum_after or "")
            lines.append(f"| `{entry.filename}` | {game} | {after} |")
        lines.append("")

    lines += ["## Digests", "", "```"]
    lines += [f"{e.sha256}  {e.filename}" for e in wanted]
    lines += [
        "```",
        "",
        "### CRC32, for looking a file up elsewhere",
        "",
        "```",
    ]
    lines += [f"{e.crc32}  {e.filename}" for e in wanted]
    lines += [
        "```",
        "",
        "## Checking a file yourself",
        "",
        "macOS, and any system with Perl:",
        "",
        "```bash",
        "shasum -a 256 *",
        "```",
        "",
        "Linux:",
        "",
        "```bash",
        "sha256sum *",
        "```",
        "",
        "Windows PowerShell:",
        "",
        "```powershell",
        "Get-FileHash -Algorithm SHA256 *",
        "```",
        "",
        "Compare the result against the digest list above. A digest that appears in the",
        "list under a different filename means the file is right and the name is wrong,",
        "which is the one failure that needs no new file to fix.",
        "",
        "## What does not belong here",
        "",
    ]
    if others:
        lines += [
            "These are named in the manifest so the tool can recognise them, and they are",
            "not part of building a disk. Keep them wherever you keep unit firmware.",
            "",
            "| File | Purpose |",
            "|:-----|:--------|",
        ]
        lines += [f"| `{e.filename}` | {e.description or e.kind} |" for e in others]
        lines.append("")
    lines += [
        "Game images never belong here either. This folder is for the small files that make",
        "a game run on the unit, not for the games.",
        "",
        "## Provenance",
        "",
        "| File | Recorded source |",
        "|:-----|:----------------|",
    ]
    lines += [f"| `{e.filename}` | {e.provenance} |" for e in wanted]
    lines += [
        "",
        "A recorded source says where the digest came from. It is not a claim that the file",
        "is correct, safe, or what it says it is. Every one of these was verified against",
        "the ROM it targets before being trusted, and so should any replacement.",
        "",
    ]
    return "\n".join(lines)
