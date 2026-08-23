"""The z64kit command line.

Each command prints a human summary, and most can emit JSON instead.

    scan       what is in this folder, and what is wrong with any of it
    plan       which games land on which disk, and whether that is optimal
    organise   write one folder per disk, renamed, without building images
    build      write the disk images, verifying every file on the way out
    inventory  which cartridges you have, and what the gaps cost
    report     the printable catalogue
    doctor     what is installed, what is missing, and what each gap costs

`organise` and `build` are two ways to take the same layout. The folders are
useful for copying to a disk by hand, for checking the naming before committing
to an image, and for a drive the tool cannot write to directly. The images are
byte reproducible and carry the FAT structures the unit needs.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import secrets
import struct
import sys
from pathlib import Path

from . import (
    aps,
    artifacts,
    burn,
    compat,
    db,
    inventory,
    merge,
    naming,
    packing,
    prompts,
    scan,
    vi,
    wizard,
)
from .fat import image, payload, writer
from .report import catalogue, hardware, latex, render, tiers
from .rom import header


def _today() -> str:
    return datetime.datetime.now(tz=datetime.UTC).date().isoformat()


def _layout(found: scan.Collection) -> list[tuple[str, list[scan.Game]]]:
    if found.is_curated:
        return [(disk, [g for g in found.games if g.disk == disk]) for disk in found.disk_names]
    items = [packing.Item(key=g.filename, size=g.size) for g in found.games]
    if not items:
        return []
    plan = packing.plan(items, image.usable_capacity())
    by_name = {g.filename: g for g in found.games}
    return [
        (f"Disk {number:02d}", [by_name[item.key] for item in disk])
        for number, disk in enumerate(plan.disks, start=1)
    ]


def _names(found: scan.Collection) -> dict[str, str]:
    assigned, _, _ = naming.assign([(g.filename, g.filename) for g in found.games])
    return assigned


def _candidates(
    found: scan.Collection, saves: dict[str, str] | None = None
) -> list[compat.Candidate]:
    """The classifier's view of a collection.

    The save type has to be passed in. It is a property of the cartridge board
    rather than of the ROM, so it comes from the fetched catalogue, and defaulting
    it to none would report every game as needing no donor cartridge at all.
    """
    lookup = saves or {}
    return [
        compat.Candidate(
            key=g.filename,
            title=g.stem,
            save=lookup.get(g.filename, "none"),
            cic=g.cic,
            size=g.size,
            has_patch=bool(found.companions_for(g)),
        )
        for g in found.games
    ]


class PatchFolderMissingError(FileNotFoundError):
    """Raised when a named patch folder is absent, rather than yielding no patches."""


DATABASE_BASE, DATABASE_EXT = artifacts.PATCH_DATABASE.upper().split(".")


def _no_database_note() -> str:
    return (
        f"note: {artifacts.PATCH_DATABASE} was not found, so nothing will carry the patch "
        "database. Games that rely on it will load unpatched."
    )


def _patch_database(folder: str | None) -> bytes | None:
    """The unit's patch database, to be copied to the root of every disk.

    The unit reads this file itself and finds the right patch inside it, so placing
    it verbatim sidesteps the question of how it matches entirely. One file per disk
    replaces the seventy-five it contains.
    """
    if not folder:
        return None
    candidate = Path(folder) / artifacts.PATCH_DATABASE
    return candidate.read_bytes() if candidate.is_file() else None


def _patch_library(folder: str | None) -> dict[bytes, list[tuple[str, str, bytes]]]:
    """Index a patch folder by the 64 byte header of the ROM each patch targets.

    A patch carries either a `.hdr` sidecar holding those bytes, or, for APS
    payloads, the target checksums at a fixed offset. Either way the binding is
    exact, so a patch built for another revision is never applied.
    """
    if not folder:
        return {}
    root = Path(folder)
    if not root.is_dir():
        raise PatchFolderMissingError(
            f"the patch folder {folder} does not exist. A missing folder is not the "
            "same as an empty one: continuing would build disks silently missing "
            "every patch, so this stops instead."
        )

    payloads: dict[str, tuple[str, bytes]] = {}
    headers: dict[str, bytes] = {}
    extras: dict[str, list[tuple[str, bytes]]] = {}
    rules = compat.load_rules()

    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        extension = path.suffix.lstrip(".").upper()
        if extension == "HDR":
            headers[path.stem.lower()] = path.read_bytes()
        elif extension in rules.patch_extensions:
            payloads[path.stem.lower()] = (extension, path.read_bytes())
        elif extension in rules.aux_extensions:
            extras.setdefault(path.stem.lower(), []).append((extension, path.read_bytes()))

    index: dict[bytes, list[tuple[str, str, bytes]]] = {}
    for stem, (extension, blob) in payloads.items():
        key = _binding_key(headers.get(stem), blob)
        if key is None:
            continue
        entries = [(stem, extension, blob)]
        entries += [(stem, ext, data) for ext, data in extras.get(stem, ())]
        index[key] = entries
    return index


def _crc_key(crc1: int, crc2: int) -> bytes:
    """The weaker binding an APS carries: the target checksum pair alone."""
    return b"crc:" + struct.pack(">II", crc1, crc2)


def _binding_key(sidecar: bytes | None, blob: bytes) -> bytes | None:
    """What this patch binds to, preferring a header sidecar over stored checksums.

    A `.hdr` gives the full 64 bytes and is normalised to big endian first, so a
    byteswapped sidecar still matches the ROM it describes. An APS carries only the
    target checksum pair, which is enough to bind it exactly and is the binding the
    format itself uses. Requiring a sidecar for those discarded every one of them.
    """
    if sidecar is not None:
        normalised = header.identity_key(sidecar)
        if normalised is not None:
            return normalised
    if blob[: len(aps.MAGIC)] == aps.MAGIC:
        try:
            parsed = aps.parse(blob)
        except aps.FormatError:
            return None
        return _crc_key(parsed.crc1, parsed.crc2)
    return None


def _patches_for(
    library: dict[bytes, list[tuple[str, str, bytes]]], game: scan.Game
) -> list[tuple[str, str, bytes]]:
    """Look a game up by full header first, then by the checksum pair alone.

    Both keys come from the already parsed header, so this touches no files.
    """
    found = library.get(game.identity_key)
    if found is not None:
        return found
    try:
        pair = _crc_key(int(game.crc1, 16), int(game.crc2, 16))
    except ValueError:
        return []
    return library.get(pair, [])


def _scan_or_exit(root: str) -> scan.Collection:
    try:
        return scan.scan(root)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc


def cmd_scan(args: argparse.Namespace) -> int:
    found = _scan_or_exit(args.source)
    if args.json:
        print(
            json.dumps(
                {
                    "root": found.root,
                    "curated": found.is_curated,
                    "games": [
                        {
                            "filename": g.filename,
                            "disk": g.disk,
                            "size": g.size,
                            "internal_name": g.internal_name,
                            "game_code": g.game_code,
                            "region": g.region,
                            "cic": g.cic,
                            "crc1": g.crc1,
                            "crc2": g.crc2,
                            "checksum_valid": g.checksum_valid,
                            "sha256": g.sha256,
                        }
                        for g in found.games
                    ],
                    "skipped": [{"path": s.path, "reason": s.reason} for s in found.skipped],
                    "warnings": list(found.warnings),
                },
                indent=1,
            )
        )
        return 0

    shape = "curated into disks" if found.is_curated else "a flat folder"
    print(f"{len(found.games)} games in {shape}, {found.total_bytes / 2**30:.2f} GiB")
    for game in found.games:
        mark = "" if game.checksum_valid else "  unverified dump"
        print(f"  {game.filename[:56]:56}  {game.size // 2**20:3d} MiB  {game.cic}{mark}")
    if found.skipped:
        print(f"\n{len(found.skipped)} skipped:")
        for entry in found.skipped:
            print(f"  {Path(entry.path).name}: {entry.reason}")
    for warning in found.warnings:
        print(f"\nnote: {warning}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    found = _scan_or_exit(args.source)
    layout = _layout(found)
    names = _names(found)

    if args.json:
        print(
            json.dumps(
                {
                    "disks": [
                        {
                            "name": name,
                            "games": [
                                {"file": g.filename, "name83": names.get(g.filename, "")}
                                for g in games
                            ],
                        }
                        for name, games in layout
                    ]
                },
                indent=1,
            )
        )
        return 0

    if not found.is_curated and found.games:
        items = [packing.Item(key=g.filename, size=g.size) for g in found.games]
        bound = packing.lower_bound(items, image.usable_capacity())
        verdict = "optimal" if len(layout) == bound else f"above the bound of {bound}"
        print(f"{len(layout)} disks, {verdict}")
    else:
        print(f"{len(layout)} disks, taken from the existing folders")

    for name, games in layout:
        used = sum(g.size for g in games) // 2**20
        print(f"\n{name}: {len(games)} games, {used} MiB")
        for game in sorted(games, key=lambda g: -g.size):
            base = names.get(game.filename, "")
            print(
                f"  {game.stem[:46]:46}  {base:8}.{game.true_extension}"
                f"  {game.size // 2**20:3d} MiB"
            )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    found = _scan_or_exit(args.source)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    names = _names(found)
    layout = _layout(found)
    patches = _patch_library(getattr(args, "patches", None))
    database = _patch_database(getattr(args, "patches", None))
    if database is None:
        print(_no_database_note())

    disks = []
    for name, games in layout:
        volume = writer.Volume()
        placed = []
        for game in sorted(games, key=lambda g: (-g.size, g.filename)):
            base = names[game.filename]
            data = Path(game.path).read_bytes()
            spot = volume.add_file(writer.ROOT, base, game.true_extension, data)
            placed.append({"source": game.filename, "name": spot.name, "lba": spot.start_lba})
            for companion in found.companions_for(game):
                volume.add_file(
                    writer.ROOT,
                    base,
                    companion.extension,
                    Path(companion.path).read_bytes(),
                )
            for stem, extension, blob in _patches_for(patches, game):
                spot = volume.add_file(writer.ROOT, base, extension, blob)
                placed.append({"source": f"{stem}.{extension.lower()}", "name": spot.name})
        if database is not None:
            volume.add_file(writer.ROOT, DATABASE_BASE, DATABASE_EXT, database)
        volume.sort_directories()

        failures = volume.verify()
        if failures:
            print(f"verification failed on {name}: {', '.join(failures)}", file=sys.stderr)
            return 1

        blob = volume.to_bytes()
        target = out_dir / f"{name.replace(' ', '_')}.img"
        target.write_bytes(blob)
        digest = hashlib.sha256(blob).hexdigest()
        disks.append({"name": name, "image": target.name, "sha256": digest, "files": placed})
        print(f"{target.name}  {len(placed)} files  verified  {digest[:16]}")

    (out_dir / "manifest.json").write_text(
        json.dumps({"schema": 1, "generated": _today(), "disks": disks}, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"\n{len(disks)} images written to {out_dir}, manifest.json alongside them")
    return 0


def cmd_organise(args: argparse.Namespace) -> int:
    found = _scan_or_exit(args.source)
    out_dir = Path(args.output)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.force:
        print(
            f"{out_dir} already has content. Pass --force to write over it.",
            file=sys.stderr,
        )
        return 2
    out_dir.mkdir(parents=True, exist_ok=True)

    names = _names(found)
    patches = _patch_library(getattr(args, "patches", None))
    database = _patch_database(getattr(args, "patches", None))
    if database is None:
        print(_no_database_note())
    disks = []
    for name, games in _layout(found):
        folder = out_dir / name
        folder.mkdir(exist_ok=True)
        written = []
        if database is not None:
            (folder / artifacts.PATCH_DATABASE).write_bytes(database)
            written.append({"source": artifacts.PATCH_DATABASE, "name": artifacts.PATCH_DATABASE})
        for game in sorted(games, key=lambda g: (-g.size, g.filename)):
            base = names[game.filename]
            target = folder / f"{base}.{game.true_extension}"
            target.write_bytes(Path(game.path).read_bytes())
            written.append({"source": game.filename, "name": target.name})
            for companion in found.companions_for(game):
                mate = folder / f"{base}.{companion.extension}"
                mate.write_bytes(Path(companion.path).read_bytes())
                written.append({"source": companion.filename, "name": mate.name})
            for stem, extension, blob in _patches_for(patches, game):
                mate = folder / f"{base}.{extension}"
                mate.write_bytes(blob)
                written.append({"source": f"{stem}.{extension.lower()}", "name": mate.name})
        disks.append({"name": name, "files": written})
        print(f"{name}  {len(written)} files")

    (out_dir / "manifest.json").write_text(
        json.dumps({"schema": 1, "generated": _today(), "disks": disks}, indent=1) + "\n",
        encoding="utf-8",
    )
    total = sum(len(d["files"]) for d in disks)
    print(f"\n{len(disks)} folders, {total} files written to {out_dir}")
    return 0


class ConsoleIO:
    """The real terminal. Every prompt goes through this so the flow stays testable."""

    def say(self, text: str = "") -> None:
        print(text)

    def ask(self, prompt: str) -> str:
        return input(prompt)


def _ask_inventory(
    questions: tuple[inventory.Question, ...],
    held: inventory.Inventory,
    path: Path,
) -> inventory.Inventory:
    """Tick off the cartridges owned, then record the answers.

    Reading a list of things you might own and then re-running the command with
    the right flags is a programmer's workflow. This asks instead.
    """
    console = ConsoleIO()
    if not questions:
        console.say("Nothing in this collection needs a donor cartridge.")
        return held

    console.say()
    console.say("Some games cannot save on the unit alone. They write to whichever")
    console.say("cartridge is in the slot, so the cartridge has to carry the right chip.")

    labels = []
    for question in questions:
        example = f" (for example {question.examples[0]})" if question.examples else ""
        labels.append(f"{question.label}{example} - unlocks {question.unlocks} games")

    already = {i for i, q in enumerate(questions) if held.owns(q.key)}
    picked = prompts.toggle_list(
        console, "Tick the cartridges you already own:", labels, selected=already
    )

    chosen = inventory.Inventory(owned=frozenset(questions[i].key for i in picked), recorded=True)
    inventory.save(chosen, path)
    console.say()
    console.say(f"Recorded in {path}. Re-run this command to change the answers.")
    return chosen


def cmd_inventory(args: argparse.Namespace) -> int:
    found = _scan_or_exit(args.source)
    rules = compat.load_rules()
    path = Path(args.file)
    held = inventory.load(path)
    games = _candidates(found, _save_types(found))

    if args.own:
        held = inventory.Inventory(owned=frozenset(args.own), recorded=True)
        inventory.save(held, path)
        print(f"recorded {', '.join(sorted(held.owned))} in {path}")
    elif args.ask:
        held = _ask_inventory(inventory.questions(games, rules), held, path)

    for question in inventory.questions(games, rules):
        mark = "yes" if held.owns(question.key) else "not recorded"
        print(f"\n{question.label} [{question.key}]: {mark}")
        print(f"  {question.prompt}")
        if question.examples:
            print(f"  for example: {', '.join(question.examples[:3])}")
        if question.titles:
            print(f"  affects {question.unlocks} titles")

    result = inventory.shopping_list(games, held, rules)
    outstanding = [i for i in result.items if i.outstanding]
    if outstanding:
        print("\nOutstanding:")
        for item in outstanding:
            reference = f", for example {item.reference}" if item.reference else ""
            print(f"  {item.label}: unlocks {item.unlocks} titles{reference}")
    else:
        print("\nNothing outstanding for the titles in this collection.")

    if result.cartridge_only:
        print(f"\nToo large to load at all: {len(result.cartridge_only)} titles")
    if result.one_save_per_cartridge:
        print("\nOne cartridge holds one game save, so parallel saves need more copies.")
    for warning in result.warnings:
        print(f"\nnote: {warning}")
    return 0


def _save_types(found: scan.Collection) -> dict[str, str]:
    """Which save chip each game carries, from the fetched catalogue.

    The chip is a property of the board and cannot be read from the ROM, so it has
    to come from a catalogue. Without one every game would be reported as saving
    nothing, which is worse than saying so plainly: the printed pages would claim
    no game needs a donor cartridge.
    """
    try:
        catalogue = db.load_default()
    except db.DatabaseMissingError:
        print(
            "note: no save type catalogue is cached, so the save column and the donor "
            "advice are left blank. Run `z64kit db-update` to fetch it."
        )
        return {}

    out: dict[str, str] = {}
    for game in found.games:
        entry = catalogue.lookup_by_code(game.game_code)
        if entry is not None:
            out[game.filename] = entry.save
    return out


def cmd_report(args: argparse.Namespace) -> int:
    found = _scan_or_exit(args.source)
    rules = compat.load_rules()
    out_dir = Path(args.output)
    held = inventory.load(Path(args.inventory)) if args.inventory else inventory.Inventory()

    layout = _layout(found)
    saves = _save_types(found)
    patches = _patch_library(getattr(args, "patches", None))
    patched = {
        g.filename for g in found.games if found.companions_for(g) or _patches_for(patches, g)
    }
    rows = catalogue.rows_from(layout, saves, rules, patched)

    generated = _today()
    bands = tiers.load(Path(args.source))
    document = catalogue.build(rows, rules=rules, held=held, generated=generated, bands=bands)
    result = render.write(document, out_dir / "catalogue", compile_pdf=not args.no_pdf)
    print(result.message)

    # A second document, because the question it answers is asked at a different
    # moment. The catalogue is read with the disks in hand; this one is read
    # before spending money on cartridges.
    shopping = inventory.shopping_list(_candidates(found, saves), held, rules)
    gear = hardware.build(shopping, rules=rules, held=held, generated=generated)
    written = render.write(gear, out_dir / "hardware", compile_pdf=not args.no_pdf)
    print(written.message)
    return 0


def _vi_requests(args: argparse.Namespace) -> dict[str, bool]:
    out = {}
    if args.no_aa:
        out["antialiasing"] = False
    if args.no_divot:
        out["divot"] = False
    if args.no_gamma_dither:
        out["gamma_dither"] = False
    if args.no_gamma:
        out["gamma"] = False
    if args.no_dither:
        out["dither_filter"] = False
    return out


def cmd_vi(args: argparse.Namespace) -> int:
    """Report the video configuration, and optionally edit it under guard."""
    requests = _vi_requests(args)
    if requests:
        return _cmd_vi_patch(args, requests)
    found = _scan_or_exit(args.source)
    rows = []
    for game in found.games:
        report = vi.audit(Path(game.path).read_bytes())
        rows.append((game, report))

    if args.json:
        print(
            json.dumps(
                {
                    "roms": [
                        {
                            "file": g.filename,
                            "modes": r.mode_count,
                            "antialiasing_on": r.antialiasing_on,
                            "dither_filter_on": r.dither_filter_on,
                            "divot_on": r.divot_on,
                            "gamma_dither_on": r.gamma_dither_on,
                            "special_features_sites": r.special_features_sites,
                            "standards": list(r.standards),
                            "ctrl_values": [f"{c:08X}" for c in r.ctrl_values],
                        }
                        for g, r in rows
                    ]
                },
                indent=1,
            )
        )
        return 0

    with_table = [(g, r) for g, r in rows if r.mode_count]
    print(f"{'GAME':46} {'MODES':>6} {'AA-ON':>6} {'DIVOT':>6} {'SITES':>6} STD")
    for game, report in rows:
        if not report.mode_count:
            print(
                f"{game.stem[:46]:46} {'-':>6} {'-':>6} {'-':>6} "
                f"{report.special_features_sites:>6} no video mode table found"
            )
            continue
        print(
            f"{game.stem[:46]:46} {report.mode_count:>6} {report.antialiasing_on:>6} "
            f"{report.divot_on:>6} {report.special_features_sites:>6} "
            f"{','.join(report.standards)}"
        )

    print(f"\n{len(with_table)} of {len(rows)} ROMs carry a recognisable video mode table.")
    if with_table:
        aa = sum(1 for _, r in with_table if r.antialiasing_on)
        dv = sum(1 for _, r in with_table if r.divot_on)
        df = sum(1 for _, r in with_table if r.dither_filter_on)
        print(f"{aa} have anti-aliasing enabled in at least one mode.")
        print(f"{dv} have the divot filter enabled in at least one mode.")
        print(f"{df} have the dither filter enabled in the table itself.")
    sites = sum(1 for _, r in rows if r.special_features_sites)
    print(f"{sites} carry the osViSetSpecialFeatures routine.")
    print("\nThe dither filter is the main source of blur, and it is normally absent")
    print("from the mode table because the game switches it on at runtime through")
    print("osViSetSpecialFeatures. Clearing it therefore means patching that routine,")
    print("not the table. Anti-aliasing and the divot filter do live in the table.")
    return 0


def _cmd_vi_patch(args: argparse.Namespace, requests: dict[str, bool]) -> int:
    if args.apply and not args.output:
        print("--apply needs --output, so the source is never written over", file=sys.stderr)
        return 2

    found = _scan_or_exit(args.source)
    out_dir = Path(args.output) if args.output else None
    wanted = ", ".join(sorted(requests))
    mode = "APPLYING" if args.apply else "DRY RUN, nothing will be written"
    print(f"{mode}. Requested: {wanted} off.\n")

    applied = refused = skipped = 0
    for game in found.games:
        data = Path(game.path).read_bytes()
        result = vi.safe_patch(data, **requests)
        if not result.applied:
            if "already" in result.reason:
                skipped += 1
                print(f"  {game.stem[:52]:52} skipped, {result.reason}")
            else:
                refused += 1
                print(f"  {game.stem[:52]:52} refused, {result.reason}")
            continue
        applied += 1
        detail = f"{result.modes_changed} modes, boot chip {result.cic}, checksum resealed"
        print(f"  {game.stem[:52]:52} {detail}")
        if args.apply and out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / game.filename).write_bytes(result.data)

    print(f"\n{applied} would change, {skipped} already correct, {refused} refused.")
    if not args.apply:
        print("Nothing was written. Add --apply with --output to write patched copies.")
    else:
        print(f"Patched copies written to {out_dir}. The originals were not touched.")
    if not args.no_dither:
        print("\nThe dedither filter is the main source of blur and is not covered by the")
        print("switches above, because it never appears in a mode table. Add --no-dither")
        print("to clear it as well.")
    return 0


def _collection_checksums(source: str | None) -> set[tuple[str, str]] | None:
    """The checksum pair of every game found, or None when no collection was named."""
    if not source:
        return None
    found = scan.scan(source)
    return {(g.crc1, g.crc2) for g in found.games}


def _report_artifact_folder(
    folder: Path, manifest: artifacts.Manifest, source: str | None = None
) -> None:
    """Print the folder's state. Shared with `artifacts` so the two cannot disagree."""
    checksums = _collection_checksums(source)
    required = None if checksums is None else artifacts.required_for(manifest, checksums)
    report = artifacts.inspect_folder(folder, manifest, required=required)
    wanted = artifacts.folder_entries(manifest)
    if required is not None:
        wanted = tuple(e for e in wanted if e.filename in required)
    by_name = {e.filename: e for e in wanted}

    print(f"\nsupplied files    {folder}")
    if source:
        print(f"                  {len(wanted)} needed by the games in {source}")
    print(f"                  {len(report.needed_present)} of {len(report.needed)} verified")
    spare = len(report.present) - len(report.needed_present)
    if spare:
        print(f"                  {spare} more verified, for games not in this collection")

    if report.missing:
        print(f"\n  missing ({len(report.missing)}). Put these in {folder}:")
        for name in report.missing:
            entry = by_name[name]
            label = entry.game or entry.description or entry.kind
            print(f"    {name:16} {entry.size:>9,} bytes  {label}")
            print(f"    {'':16} {entry.sha256}")

    if report.wrong:
        print(f"\n  present but not what the manifest expects ({len(report.wrong)}):")
        for name, reason in sorted(report.wrong.items()):
            print(f"    {name:16} {reason}")
            print(f"    {'':16} expected {by_name[name].sha256}")

    if report.misnamed:
        print(f"\n  right file, wrong name ({len(report.misnamed)}). Rename these:")
        for found, should_be in sorted(report.misnamed.items()):
            print(f"    {found:16} rename to {should_be}")

    if report.unknown:
        print(f"\n  not in the manifest ({len(report.unknown)}), ignored:")
        for name in report.unknown:
            print(f"    {name}")

    if report.complete:
        print("\n  everything the manifest names is present and verified.")
    else:
        print("\n  `z64kit artifacts` gates on this and exits non-zero. Digests for every")
        print(f"  expected file are in {folder / 'README.md'}.")


def cmd_doctor(args: argparse.Namespace) -> int:
    manifest = artifacts.load_default_manifest()
    rules = compat.load_rules()
    engine = render.find_engine()

    print(f"artifact manifest   {len(manifest.by_sha256)} entries")
    print(f"compatibility rules memory limit {rules.memory_mib} MiB")
    print(f"TeX engine          {engine or 'none found'}")
    if engine is None:
        print("                    install tectonic for PDF output, a single binary")
    probe = latex.document(title="Probe", subtitle="", body="ok")
    print(f"latex builder       {len(probe)} byte document renders")
    print(f"volume capacity     {image.usable_capacity()} bytes usable")
    print(
        f"granularity         {packing.units_for_capacity(image.usable_capacity())} games per disk"
    )

    _report_artifact_folder(
        Path(args.folder or artifacts.FOLDER_NAME), manifest, getattr(args, "source", None)
    )
    return 0


def cmd_artifacts(args: argparse.Namespace) -> int:
    """Report what the supplied-artifact folder holds, or rewrite its documentation."""
    manifest = artifacts.load_default_manifest()
    folder = Path(args.folder or artifacts.FOLDER_NAME)

    if args.write_readme:
        target = folder / "README.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(artifacts.render_folder_readme(manifest), encoding="utf-8")
        print(f"wrote {target}")
        return 0

    checksums = _collection_checksums(getattr(args, "source", None))
    required = None if checksums is None else artifacts.required_for(manifest, checksums)
    report = artifacts.inspect_folder(folder, manifest, required=required)
    wanted = artifacts.folder_entries(manifest)
    if required is not None:
        wanted = tuple(e for e in wanted if e.filename in required)

    if args.json:
        print(
            json.dumps(
                {
                    "folder": str(folder),
                    "expected": len(wanted),
                    "complete": report.complete,
                    "present": list(report.present),
                    "missing": list(report.missing),
                    "wrong": report.wrong,
                    "misnamed": report.misnamed,
                    "unknown": list(report.unknown),
                },
                indent=2,
            )
        )
        return 0 if report.complete else 1

    print(f"folder   {folder}")
    print(f"expected {len(report.needed)} files, {len(report.needed_present)} verified")
    spare = len(report.present) - len(report.needed_present)
    if spare:
        print(f"         {spare} more verified, for games not in this collection")

    if report.missing:
        print(f"\nmissing ({len(report.missing)})")
        for name in report.missing:
            entry = next(e for e in wanted if e.filename == name)
            print(f"  {name:16} {entry.size:>8} bytes  {entry.game or entry.description or ''}")

    if report.wrong:
        print(f"\nwrong ({len(report.wrong)})")
        for name, reason in sorted(report.wrong.items()):
            print(f"  {name:16} {reason}")

    if report.misnamed:
        print(f"\nrecognised under the wrong name ({len(report.misnamed)})")
        for found, should_be in sorted(report.misnamed.items()):
            print(f"  {found:16} rename to {should_be}")

    if report.unknown:
        print(f"\nnot in the manifest ({len(report.unknown)})")
        for name in report.unknown:
            print(f"  {name}")

    if report.complete:
        print("\neverything the manifest names is present and verified.")
        return 0
    print(f"\nsee {folder / 'README.md'} for the digest of every expected file.")
    return 1


def cmd_payload(args: argparse.Namespace) -> int:
    """Write the used prefix of an image, stamped with a serial for one disk.

    Exists for `write-zip.sh`, which needs the byte count before it starts and would
    otherwise spend minutes pushing zeroes at a drive managing about 765 kB/s.
    """
    source = Path(args.image)
    try:
        raw = source.read_bytes()
    except OSError as error:
        print(f"could not read {source}: {error}")
        return 1

    serial = args.serial if args.serial is not None else secrets.randbits(32)
    try:
        made = payload.prepare(raw, serial=serial)
    except payload.ImageRejectedError as error:
        print(f"{source} is not a Zip 100 image this can write: {error}")
        return 1

    try:
        Path(args.output).write_bytes(made.body)
    except OSError as error:
        print(f"could not write {args.output}: {error}")
        return 1

    print(f"SECTORS={made.sectors}")
    print(f"BYTES={made.size}")
    print(f"SERIAL={made.serial:08X}")
    print(f"HIGHEST_CLUSTER={made.highest_cluster}")
    print(f"DATA_START_LBA={made.data_start_lba}")
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    """Write one image to a physical disk, watching the drive as it goes."""
    source = Path(args.image)
    if not source.is_file():
        print(f"no such image: {source}")
        return 1

    try:
        device = burn.read_device(args.device)
    except burn.DeviceError as error:
        print(str(error))
        return 1

    refused = burn.refusals(device, image.TOTAL_SECTORS * image.SECTOR)
    if refused:
        print(f"REFUSING TO WRITE to {args.device}:")
        for reason in refused:
            print(f"  {reason}")
        return 1

    serial = args.serial if args.serial is not None else secrets.randbits(32)
    try:
        made = payload.prepare(source.read_bytes(), serial=serial)
    except (OSError, payload.ImageRejectedError) as error:
        print(f"{source} cannot be written: {error}")
        return 1

    body = made.body
    total = made.size
    if getattr(args, "full", False):
        whole = bytearray(source.read_bytes())
        whole[: len(body)] = body
        body = bytes(whole)
        total = len(body)

    if made.highest_cluster < payload.FIRST_DATA_CLUSTER and not args.empty:
        print(f"{source} holds no files, so writing it would leave a blank disk.")
        print("Pass --empty if that is what you want.")
        return 1

    print(f"target      {device.block}  {device.media}")
    print(f"image       {source}")
    print(f"payload     {made.sectors} sectors, {made.size} bytes")
    print(f"serial      {made.serial:08X} (fresh for this disk)")

    if not args.yes:
        answer = input(f"Write to {device.block} and destroy its contents? type YES: ")
        if answer.strip() != "YES":
            print("aborted")
            return 1

    scratch = Path(args.output or "") if args.output else None
    holder = scratch or Path(f"{source}.payload")
    try:
        holder.write_bytes(body)
        written = burn.write_image(holder, device, total_bytes=total, say=print)
    except burn.WriteFailedError as error:
        print("")
        print(f"STOPPED: {error}")
        print("  The disk was ejected. A drive that clicks can damage the next disk")
        print("  it is given, and a disk that caused it can damage the next drive.")
        return 1
    finally:
        holder.unlink(missing_ok=True)

    print(f"verify      OK, {written.chunks} chunks matched")
    print(f"elapsed     {written.seconds}s")
    if written.ejected:
        print(f"ejected     {device.block}, safe to remove")
    return 0


def cmd_db_update(_args: argparse.Namespace) -> int:
    """Fetch the save-type catalogue. This is the only command that uses the network."""
    try:
        written = db.update()
    except OSError as error:
        print(f"could not download the {db.SOURCE_NAME}: {error}")
        print(f"fetch {db.SOURCE_URL} by hand and place it at {db.cache_path()}")
        return 1
    catalogue = db.load(written)
    print(f"cached {written}")
    print(
        f"{len(catalogue.by_md5)} exact dumps and {len(catalogue.id_patterns)} game-code patterns"
    )
    print(f"source {db.SOURCE_NAME}, {db.SOURCE_LICENCE}, fetched rather than bundled")
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    """Fold the requested video change into a patch the game already needs."""
    requests = _vi_requests(args)
    if not requests:
        print(
            "nothing requested. Pass at least one of --no-aa, --no-divot, "
            "--no-gamma-dither, --no-gamma"
        )
        return 2
    if args.apply and not args.output:
        print("refusing to write without --output, which names the merged patch")
        return 2

    rom = Path(args.rom).read_bytes()
    existing = Path(args.patch).read_bytes()
    try:
        result = merge.merge(rom, existing, **requests)
    except (aps.FormatError, aps.TargetMismatchError, merge.UnsafeMergeError) as error:
        print(f"refused: {error}")
        return 1

    if not result.video_changes:
        print("no video change was needed, so the existing patch already is the answer")
        return 0

    print(f"boot chip           {result.cic}")
    print(f"existing records    {result.existing_records}")
    print(f"video words changed {len(result.video_changes)}")
    for offset, before, after in result.video_changes[:8]:
        print(f"  0x{offset:06X}  {before:#010x} -> {after:#010x}")
    if len(result.video_changes) > 8:
        print(f"  and {len(result.video_changes) - 8} more")
    print(
        f"merged patch        {len(result.patch)} bytes, "
        f"bound to the untouched ROM {aps.parse(result.patch).crc1:#010x}"
    )

    if not args.apply:
        print("\ndry run. Pass --apply with --output to write the merged patch.")
        return 0

    Path(args.output).write_bytes(result.patch)
    print(f"\nwrote {args.output}")
    return 0


def _run_step(action: str, source: Path, output: Path, patches: str | None) -> int:
    """Perform one step of the guided flow with the same commands the CLI exposes.

    The flow asks the questions and this answers them, which keeps the dependency
    pointing one way: the command line knows about the wizard, and the wizard knows
    only that something will take an action and return a status.
    """
    args = argparse.Namespace(
        source=str(source),
        output=str(output),
        force=False,
        patches=patches,
        json=False,
        no_pdf=False,
        inventory=str(Path(output) / "cartridges.json"),
        file=str(Path(output) / "cartridges.json"),
        own=[],
        show=False,
        ask=True,
    )
    if action == wizard.ACTION_WRITE:
        return cmd_write(
            argparse.Namespace(
                image=str(source),
                device=patches or "",
                yes=False,
                empty=False,
                output=None,
                serial=None,
            )
        )
    if action == wizard.ACTION_FOLDERS:
        return cmd_organise(args)
    if action == wizard.ACTION_IMAGES:
        return cmd_build(args)
    if action == wizard.ACTION_REPORT:
        return cmd_report(args)
    return cmd_inventory(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="z64kit", description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="report what is in a folder")
    scan_parser.add_argument("source")
    scan_parser.add_argument("--json", action="store_true")
    scan_parser.set_defaults(func=cmd_scan)

    plan_parser = subparsers.add_parser("plan", help="show which games land on which disk")
    plan_parser.add_argument("source")
    plan_parser.add_argument("--json", action="store_true")
    plan_parser.set_defaults(func=cmd_plan)

    org = subparsers.add_parser(
        "organise", help="write one folder per disk, with 8.3 names, no images"
    )
    org.add_argument("source")
    org.add_argument("output")
    org.add_argument("--force", action="store_true", help="write over existing content")
    org.add_argument(
        "--patches", default=None, help="folder of patch files to match against the ROMs"
    )
    org.set_defaults(func=cmd_organise)

    build_cmd = subparsers.add_parser("build", help="write the disk images")
    build_cmd.add_argument("source")
    build_cmd.add_argument("output")
    build_cmd.add_argument(
        "--patches", default=None, help="folder of patch files to match against the ROMs"
    )
    build_cmd.set_defaults(func=cmd_build)

    inv = subparsers.add_parser("inventory", help="record which cartridges you have")
    inv.add_argument("source")
    inv.add_argument("--file", default="z64kit-inventory.json")
    inv.add_argument("--own", action="append", default=[])
    inv.add_argument("--show", action="store_true")
    inv.add_argument(
        "--ask", action="store_true", help="tick off what you own instead of passing --own"
    )
    inv.set_defaults(func=cmd_inventory)

    rep = subparsers.add_parser("report", help="write the printable catalogue")
    rep.add_argument("source")
    rep.add_argument("output")
    rep.add_argument("--inventory", default=None)
    rep.add_argument("--no-pdf", action="store_true")
    rep.add_argument(
        "--patches", default=None, help="folder of patch files, so patched games are marked"
    )
    rep.set_defaults(func=cmd_report)

    vic = subparsers.add_parser("vi", help="report the video configuration in each ROM, read only")
    vic.add_argument("source")
    vic.add_argument("--json", action="store_true")
    vic.add_argument("--no-aa", action="store_true", help="disable anti-aliasing")
    vic.add_argument("--no-divot", action="store_true", help="disable the divot filter")
    vic.add_argument("--no-gamma-dither", action="store_true", help="disable gamma dithering")
    vic.add_argument(
        "--no-dither",
        action="store_true",
        help="disable the dedither filter, the main source of blur",
    )
    vic.add_argument("--no-gamma", action="store_true", help="disable gamma correction")
    vic.add_argument("--output", default=None, help="folder for patched copies")
    vic.add_argument("--apply", action="store_true", help="actually write, otherwise dry run")
    vic.set_defaults(func=cmd_vi)

    mg = subparsers.add_parser(
        "merge", help="fold a video change into a patch the game already needs"
    )
    mg.add_argument("rom")
    mg.add_argument("patch")
    mg.add_argument("--no-aa", action="store_true", help="disable anti-aliasing")
    mg.add_argument("--no-divot", action="store_true", help="disable the divot filter")
    mg.add_argument("--no-gamma-dither", action="store_true", help="disable gamma dithering")
    mg.add_argument(
        "--no-dither",
        action="store_true",
        help="disable the dedither filter, the main source of blur",
    )
    mg.add_argument("--no-gamma", action="store_true", help="disable gamma correction")
    mg.add_argument("--output", default=None, help="path for the merged patch")
    mg.add_argument("--apply", action="store_true", help="actually write, otherwise dry run")
    mg.set_defaults(func=cmd_merge)

    art = subparsers.add_parser(
        "artifacts", help="check the supplied-artifact folder against the manifest"
    )
    art.add_argument(
        "--folder", default=None, help=f"where the files live, default {artifacts.FOLDER_NAME}/"
    )
    art.add_argument("--json", action="store_true")
    art.add_argument(
        "--source",
        default=None,
        help="only require the files the games in this folder actually need",
    )
    art.add_argument(
        "--write-readme", action="store_true", help="regenerate the folder's documentation"
    )
    art.set_defaults(func=cmd_artifacts)

    wr = subparsers.add_parser("write", help="write one image to a Zip disk, verifying as it goes")
    wr.add_argument("image")
    wr.add_argument("device", help="the device node, for example disk8")
    wr.add_argument("-y", "--yes", action="store_true", help="skip the confirmation")
    wr.add_argument("--empty", action="store_true", help="allow an image holding no files")
    wr.add_argument(
        "--full",
        action="store_true",
        help="write the whole image rather than only the part holding data",
    )
    wr.add_argument("--output", default=None, help="where to stage the payload")
    wr.add_argument(
        "--serial",
        type=lambda given: int(given, 16),
        default=None,
        help="hex volume serial, default a fresh random one per disk",
    )
    wr.set_defaults(func=cmd_write)

    pay = subparsers.add_parser(
        "payload", help="write the used prefix of an image, stamped for one disk"
    )
    pay.add_argument("image")
    pay.add_argument("output")
    pay.add_argument(
        "--serial",
        type=lambda given: int(given, 16),
        default=None,
        help="hex volume serial, default a fresh random one per disk",
    )
    pay.set_defaults(func=cmd_payload)

    dbu = subparsers.add_parser(
        "db-update", help="download the save-type catalogue, the only networked command"
    )
    dbu.set_defaults(func=cmd_db_update)

    doc = subparsers.add_parser("doctor", help="report what is installed and what is missing")
    doc.add_argument(
        "--folder",
        default=None,
        help=f"where the supplied files live, default {artifacts.FOLDER_NAME}/",
    )
    doc.add_argument(
        "--source",
        default=None,
        help="only require the files the games in this folder actually need",
    )
    doc.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        if argv is None or not argv:
            return wizard.run(ConsoleIO(), runner=_run_step)
        parser.print_usage()
        return 2
    try:
        return int(args.func(args))
    except PatchFolderMissingError as error:
        print(error)
        return 2
    except SystemExit as exc:
        return int(exc.code or 0)


if __name__ == "__main__":
    raise SystemExit(main())
