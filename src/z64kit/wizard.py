"""The guided flow, for someone who wants their games on a disk.

Running the tool with no arguments lands here instead of printing a usage
message. The shape is a wizard rather than a dashboard because the job is
genuinely linear: find the games, check the small files that make some of them
run, decide folders or images, write them.

Three rules shape every screen. Nobody should have to type a path when the tool
can offer one. Nothing irreversible happens without an explicit yes. And a
problem is always stated together with what to do about it, because "verification
failed" tells the reader nothing they can act on.

Every step takes a console and returns a value, so the flow is driven by scripted
answers in the test suite rather than by a person. The step that actually writes
is injected for the same reason.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import artifacts, packing, prompts, scan
from .compat import Candidate, classify, load_rules, requirement_for
from .fat import image

ACTION_FOLDERS = "folders"
ACTION_IMAGES = "images"
ACTION_REPORT = "report"
ACTION_INVENTORY = "inventory"

GAME_SUFFIXES = (".z64", ".v64", ".n64", ".rom")
LIKELY_FOLDERS = (
    "Mr Backup z64",
    "roms",
    "ROMs",
    "Roms",
    "n64",
    "N64",
    "Documents/roms",
    "Downloads",
)
TOTAL_STEPS = 5
MAX_CANDIDATES = 8


def _holds_games(folder: Path) -> bool:
    try:
        return any(p.suffix.lower() in GAME_SUFFIXES for p in folder.iterdir() if p.is_file())
    except OSError:
        return False


def candidate_folders(home: Path, cwd: Path) -> list[Path]:
    """Folders worth offering, so the first question is a pick rather than typing.

    Beyond the usual places under the home folder, this looks beside the working
    folder: someone who unzipped the tool next to their games should see them
    offered. A folder whose children hold the games counts too, because that is
    what a collection already split into disks looks like.
    """
    found: list[Path] = []

    def remember(folder: Path) -> None:
        if len(found) < MAX_CANDIDATES and folder.is_dir() and folder not in found:
            found.append(folder)

    for name in LIKELY_FOLDERS:
        remember(home / name)

    if cwd.is_dir():
        if _holds_games(cwd):
            remember(cwd)
        try:
            children = sorted(p for p in cwd.iterdir() if p.is_dir())
        except OSError:
            children = []
        for child in children:
            if _holds_games(child) or any(
                _holds_games(grandchild)
                for grandchild in sorted(p for p in child.iterdir() if p.is_dir())
            ):
                remember(child)
    return found


def _inspect(
    folder: Path,
) -> tuple[int, int, list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    """Return the supplied-file state as plain values the steps can render."""
    manifest = artifacts.load_default_manifest()
    report = artifacts.inspect_folder(folder, manifest)
    expected = len(artifacts.folder_entries(manifest))
    return (
        expected,
        len(report.present),
        list(report.missing),
        sorted(report.wrong.items()),
        sorted(report.misnamed.items()),
    )


def step_pick_source(console: prompts.Console, candidates: list[Path]) -> Path:
    """Offer the folders that look right, with typing as the last resort."""
    if not candidates:
        return prompts.ask_folder(console, "Where are your game files?")

    options = [str(folder) for folder in candidates]
    options.append("Somewhere else")
    picked = prompts.choose(console, "Where are your game files?", options, default=0)
    if picked < len(candidates):
        return candidates[picked]
    return prompts.ask_folder(console, "Type or drag the folder here:")


def step_check_supplied(console: prompts.Console, folder: Path) -> bool:
    """Report the small files some games need, and let the person decide."""
    expected, verified, missing, wrong, misnamed = _inspect(folder)

    console.say()
    console.say(f"Checking the extra files in {folder}")
    console.say(f"  {verified} of {expected} verified")

    if misnamed:
        console.say()
        console.say("  These are the right files under the wrong name. Rename them:")
        for found, should_be in misnamed:
            console.say(f"    {found} -> {should_be}")

    if wrong:
        console.say()
        console.say("  These do not match what is expected:")
        for name, reason in wrong:
            console.say(f"    {name}: {reason}")

    if not missing and not wrong and not misnamed:
        console.say("  Everything needed is here.")
        return True

    if missing:
        console.say()
        console.say(f"  Missing {len(missing)} file(s):")
        for name in missing:
            console.say(f"    {name}")
        console.say()
        console.say("  A handful of games will not save, or will not boot, without these.")
        console.say("  Every other game is unaffected. The full list with checksums is in")
        console.say(f"  {folder / 'README.md'}.")

    console.say()
    return prompts.confirm(console, "Carry on without them?", default=True)


def _describe_plan(console: prompts.Console, source: Path) -> int:
    """Scan, then say how many disks this takes and what will not work."""
    found = scan.scan(str(source))
    if not found.games:
        console.say()
        console.say(f"No game files found in {source}.")
        console.say("Expected files ending in .z64, .v64, .n64 or .rom.")
        return 0

    if found.is_curated:
        disks = len(found.disk_names)
    else:
        items = [packing.Item(key=g.filename, size=g.size) for g in found.games]
        disks = len(packing.plan(items, image.usable_capacity()).disks)

    total_mib = sum(g.size for g in found.games) // (1024 * 1024)
    console.say()
    console.say(f"  {len(found.games)} games, {total_mib:,} MiB in total")
    console.say(f"  They fit on {disks} disk(s)")

    rules = load_rules()
    affected = []
    for game in found.games:
        verdict = classify(
            Candidate(key=game.filename, title=game.stem, cic=game.cic, size=game.size),
            rules,
        )
        sentence = requirement_for(verdict, rules)
        if sentence:
            affected.append((game.stem, sentence))

    if affected:
        console.say()
        console.say(f"  {len(affected)} game(s) need something beyond the disk:")
        for title, sentence in affected[:5]:
            console.say(f"    {title}")
            console.say(f"      {sentence}")
        if len(affected) > 5:
            console.say(f"    and {len(affected) - 5} more, listed in the printed catalogue")

    return disks


def step_pick_action(console: prompts.Console) -> str:
    """Folders or images. Both produce the same layout by different routes."""
    picked = prompts.choose(
        console,
        "What should this produce?",
        [
            "Folders, one per disk, so you can copy the files by hand",
            "Disk images, ready to write straight to a Zip disk",
        ],
        default=0,
    )
    return ACTION_FOLDERS if picked == 0 else ACTION_IMAGES


def _default_runner(action: str, source: Path, output: Path, patches: str | None) -> int:
    """Hand the work to the same commands the command line uses."""
    import argparse

    from . import cli

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
    if action == ACTION_FOLDERS:
        return cli.cmd_organise(args)
    if action == ACTION_IMAGES:
        return cli.cmd_build(args)
    if action == ACTION_REPORT:
        return cli.cmd_report(args)
    return cli.cmd_inventory(args)


def run(
    console: prompts.Console,
    *,
    source: Path | None = None,
    supplied: Path | None = None,
    home: Path | None = None,
    cwd: Path | None = None,
    runner: Callable[[str, Path, Path, str | None], int] | None = None,
) -> int:
    """Walk the whole flow. Returns 0 only when something was actually produced."""
    act = runner or _default_runner
    supplied_folder = supplied or Path(artifacts.FOLDER_NAME)

    console.say("This puts your Nintendo 64 games onto Zip disks for a Mr. Backup Z64.")
    console.say("Nothing is written until you say so, and your game files are never changed.")
    console.say("Type q at any question to leave.")

    try:
        console.say()
        console.say(f"Step 1 of {TOTAL_STEPS}: your games")
        chosen_source = source or step_pick_source(
            console, candidate_folders(home or Path.home(), cwd or Path.cwd())
        )

        console.say()
        console.say(f"Step 2 of {TOTAL_STEPS}: the extra files some games need")
        if not step_check_supplied(console, supplied_folder):
            console.say()
            console.say("Stopped. Nothing was written.")
            return 1

        console.say()
        console.say(f"Step 3 of {TOTAL_STEPS}: what this will take")
        disks = _describe_plan(console, chosen_source)
        if disks == 0:
            console.say()
            console.say("Stopped. Nothing was written.")
            return 1

        console.say()
        console.say(f"Step 4 of {TOTAL_STEPS}: what to produce")
        action = step_pick_action(console)
        destination = prompts.ask_folder(console, "Where should it go?", must_exist=False)

        console.say()
        console.say(f"Step 5 of {TOTAL_STEPS}: confirm")
        console.say(f"  from  {chosen_source}")
        console.say(f"  to    {destination}")
        console.say(f"  as    {'folders' if action == ACTION_FOLDERS else 'disk images'}")
        if not prompts.confirm(console, "Go ahead?", default=True):
            console.say()
            console.say("Stopped. Nothing was written.")
            return 1
    except prompts.Cancelled:
        console.say()
        console.say("Cancelled. Nothing was written.")
        return 1

    patch_folder = str(supplied_folder) if supplied_folder.is_dir() else None
    try:
        code = act(action, chosen_source, destination, patch_folder)
    except (OSError, ValueError) as error:
        console.say()
        console.say(f"That did not finish: {error}")
        console.say("Nothing was completed. Your game files are untouched.")
        return 1
    if code != 0:
        console.say()
        console.say("That did not finish. Nothing above this line was rolled back.")
        return code

    console.say()
    console.say("Done.")

    try:
        wants_catalogue = prompts.confirm(
            console, "Write a printable catalogue to keep with the disks?", default=True
        )
        if wants_catalogue and act(ACTION_REPORT, chosen_source, destination, str(supplied_folder)):
            console.say("  The catalogue did not finish. The disks are unaffected.")

        wants_inventory = prompts.confirm(
            console, "Record which cartridges you own, so gaps are reported?", default=True
        )
        if wants_inventory and act(ACTION_INVENTORY, chosen_source, destination, patch_folder):
            console.say("  Recording did not finish. The disks are unaffected.")
    except prompts.Cancelled:
        console.say()

    console.say()
    console.say("What to do next:")
    if action == ACTION_IMAGES:
        console.say("  Write an image to a Zip disk, one image per disk.")
    else:
        console.say("  Copy the contents of each folder onto its own Zip disk.")
    console.say(f"  Everything produced is in {destination}.")
    return 0
