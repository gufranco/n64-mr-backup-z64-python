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


FOLDER_KINDS = ("patch", "save")
FOLDER_OWN_FILES = ("README.md", ".gitignore")
FOLDER_NAME = "patches"


@dataclass(frozen=True)
class FolderReport:
    present: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    wrong: dict[str, str] = field(default_factory=dict)
    misnamed: dict[str, str] = field(default_factory=dict)
    unknown: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing and not self.wrong


def folder_entries(manifest: Manifest) -> tuple[ArtifactEntry, ...]:
    """The files that belong in the supplied-artifact folder, in a stable order."""
    chosen = [e for e in manifest.entries() if e.kind in FOLDER_KINDS]
    return tuple(sorted(chosen, key=lambda e: e.filename))


def other_entries(manifest: Manifest) -> tuple[ArtifactEntry, ...]:
    chosen = [e for e in manifest.entries() if e.kind not in FOLDER_KINDS]
    return tuple(sorted(chosen, key=lambda e: e.filename))


def inspect_folder(folder: Path | str, manifest: Manifest) -> FolderReport:
    """Compare a folder against the manifest, deciding on SHA-256 alone.

    A missing folder is reported as everything missing rather than raised, because
    the answer a caller wants is the same either way: none of it is here yet.
    """
    root = Path(folder)
    wanted = {e.filename: e for e in folder_entries(manifest)}
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
        entry = wanted.get(path.name)
        if entry is None:
            unknown.append(path.name)
            continue
        result = verify(data, entry)
        if result.ok:
            present.append(path.name)
        else:
            wrong[path.name] = result.reason

    for name in wanted:
        if name not in present and name not in wrong:
            missing.append(name)

    return FolderReport(
        present=tuple(sorted(present)),
        missing=tuple(sorted(missing)),
        wrong=wrong,
        misnamed=misnamed,
        unknown=tuple(sorted(unknown)),
    )


def _folder_row(entry: ArtifactEntry) -> str:
    target = ""
    if entry.target_crc1 and entry.target_crc2:
        target = f"`{entry.target_crc1}` / `{entry.target_crc2}`"
    return (
        f"| `{entry.filename}` | {entry.game or ''} | {entry.description or ''} "
        f"| {entry.size:,} | {target} |"
    )


def render_folder_readme(manifest: Manifest) -> str:
    """Write the folder's documentation from the manifest, so the two cannot diverge.

    Nothing here says where to obtain a file. The point of the document is to let
    somebody confirm that what they already have is the right thing, and to name
    exactly what is wrong when it is not.
    """
    wanted = folder_entries(manifest)
    others = other_entries(manifest)

    lines = [
        "# Supplied artifacts",
        "",
        "Files this project needs, cannot distribute, and cannot regenerate. Put them",
        "in this folder. Everything here is ignored by git except this document and the",
        "ignore rules beside it, so a payload dropped in cannot be committed by accident.",
        "",
        "This file is generated from the manifest the code checks against. Do not edit it",
        "by hand: run `z64kit artifacts --write-readme` after the manifest changes.",
        "",
        "## How a file is accepted",
        "",
        "**SHA-256 alone decides.** Size is a cheap pre-filter and CRC32 is there so a",
        "file can be cross-referenced against a public database. Neither one accepts or",
        "rejects anything.",
        "",
        "A file whose digest does not match is reported with the reason, not just a",
        "failure. Wrong size, right size with altered content, and a recognised file",
        "under the wrong name are three different problems with three different fixes.",
        "",
        "```",
        "z64kit artifacts            # what is here, what is missing, what is wrong",
        "```",
        "",
        "## Expected files",
        "",
        f"{len(wanted)} files. The checksum pair is the ROM each patch is bound to, which",
        "is how a patch built for another revision is refused rather than applied.",
        "",
        "| File | Game | Purpose | Bytes | Target CRC1 / CRC2 |",
        "|:-----|:-----|:--------|------:|:-------------------|",
    ]
    lines += [_folder_row(entry) for entry in wanted]
    lines += [
        "",
        "### Digests",
        "",
        "```",
    ]
    for entry in wanted:
        lines.append(f"{entry.sha256}  {entry.filename}")
    lines += [
        "```",
        "",
        "### CRC32, for looking a file up elsewhere",
        "",
        "| File | CRC32 |",
        "|:-----|:------|",
    ]
    lines += [f"| `{e.filename}` | `{e.crc32}` |" for e in wanted]

    companions = [e for e in wanted if e.companions]
    if companions:
        lines += [
            "",
            "## Files that travel in pairs",
            "",
            "Some patches need a save file present as well, and the unit expects both to",
            "carry the ROM's name once they reach a disk. The tool renames them together,",
            "so here they keep the names below.",
            "",
            "| Patch | Also needs |",
            "|:------|:-----------|",
        ]
        lines += [
            f"| `{e.filename}` | {', '.join(f'`{c}`' for c in e.companions)} |" for e in companions
        ]

    lines += [
        "",
        "## Checking a file yourself",
        "",
        "macOS and any system with Perl:",
        "",
        "```bash",
        "shasum -a 256 *.aps *.ram *.eep",
        "```",
        "",
        "Linux:",
        "",
        "```bash",
        "sha256sum *.aps *.ram *.eep",
        "```",
        "",
        "Windows PowerShell:",
        "",
        "```powershell",
        "Get-FileHash -Algorithm SHA256 *.aps, *.ram, *.eep",
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
        "Game images never belong here either. This folder is for the small files that",
        "make a game run on the unit, not for the games.",
        "",
        "## Provenance",
        "",
        "| File | Recorded source |",
        "|:-----|:----------------|",
    ]
    lines += [f"| `{e.filename}` | {e.provenance} |" for e in wanted]
    lines += [
        "",
        "A recorded source says where the digest came from. It is not a claim that the",
        "file is correct, safe, or what it says it is. Every one of these was verified",
        "against the ROM it targets before being trusted, and so should any replacement.",
        "",
    ]
    return "\n".join(lines)
