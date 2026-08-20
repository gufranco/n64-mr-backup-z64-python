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
