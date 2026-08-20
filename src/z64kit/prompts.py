"""Interactive prompts for people who did not ask for a command line.

The audience for the guided flow is someone who wants their games on a disk, not
someone who enjoys argument parsing. That sets the rules here.

Nothing crashes on a typo; a bad answer explains itself and asks again. Enter
always means the obvious thing, and the obvious thing is visible in the prompt.
Paths arrive the way people actually produce them: dragged from a file manager and
therefore quoted, pasted from a shell and therefore backslash-escaped, or typed
with a stray trailing slash. All of those are the same path and are treated as
such. `q` gets out from anywhere.

Every function takes a console rather than touching stdin, so the whole layer is
exercised by scripted answers in the test suite instead of by a human.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

QUIT_WORDS = ("q", "quit", "exit")
YES_WORDS = ("y", "yes")
NO_WORDS = ("n", "no")
ALL_WORDS = ("a", "all")
NONE_WORDS = ("n", "none")


class Cancelled(KeyboardInterrupt):
    """Raised when the person asks to leave."""


class Console(Protocol):
    def say(self, text: str = "") -> None: ...

    def ask(self, prompt: str) -> str: ...


def _read(console: Console, prompt: str) -> str:
    answer = console.ask(prompt).strip()
    if answer.lower() in QUIT_WORDS:
        raise Cancelled("cancelled")
    return answer


def confirm(console: Console, question: str, default: bool | None = None) -> bool:
    """Ask a yes or no question, showing which answer Enter gives."""
    if default is True:
        hint = "[Y/n]"
    elif default is False:
        hint = "[y/N]"
    else:
        hint = "[y/n]"

    while True:
        answer = _read(console, f"{question} {hint} ").lower()
        if not answer and default is not None:
            return default
        if answer in YES_WORDS:
            return True
        if answer in NO_WORDS:
            return False
        console.say("  Please answer yes or no.")


def choose(console: Console, question: str, options: list[str], default: int | None = None) -> int:
    """Show a numbered list and return the index chosen. Numbering starts at 1."""
    if not options:
        raise ValueError("cannot choose from no options")

    console.say()
    console.say(question)
    for number, option in enumerate(options, start=1):
        marker = " (default)" if default is not None and number - 1 == default else ""
        console.say(f"  {number}) {option}{marker}")

    upper = len(options)
    while True:
        answer = _read(console, f"Choose 1-{upper}: " if upper > 1 else "Choose 1: ")
        if not answer and default is not None:
            return default
        if answer.isdigit():
            picked = int(answer)
            if 1 <= picked <= upper:
                return picked - 1
        console.say(f"  Enter a number between 1 and {upper}.")


def clean_path(text: str) -> str:
    """Turn what a person pasted into a path.

    A folder dragged into a terminal arrives wrapped in quotes on macOS and with
    backslash-escaped spaces from a shell paste. Both mean the same folder as the
    bare text, so both are accepted.
    """
    answer = text.strip()
    for quote in ("'", '"'):
        if len(answer) >= 2 and answer.startswith(quote) and answer.endswith(quote):
            answer = answer[1:-1]
            break
    answer = answer.replace("\\ ", " ").strip()
    if not answer:
        return ""
    if answer.startswith("~"):
        answer = str(Path(answer).expanduser())
    if len(answer) > 1 and answer.endswith("/"):
        answer = answer.rstrip("/") or "/"
    return answer


def ask_folder(
    console: Console,
    question: str,
    default: Path | None = None,
    must_exist: bool = True,
) -> Path:
    """Ask for a folder, and keep asking until the answer is usable."""
    hint = f" [{default}]" if default is not None else ""
    while True:
        raw = _read(console, f"{question}{hint} ")
        if not raw and default is not None:
            return default
        cleaned = clean_path(raw)
        if not cleaned:
            console.say("  Type a folder, or drag one into this window.")
            continue

        candidate = Path(cleaned)
        if not must_exist:
            return candidate
        if candidate.is_dir():
            return candidate
        if candidate.exists():
            console.say(f"  {candidate} is a file. This needs a folder.")
        else:
            console.say(f"  Could not find {candidate}.")


def toggle_list(
    console: Console,
    question: str,
    items: list[str],
    selected: set[int] | None = None,
) -> set[int]:
    """Tick items on and off by number, then press Enter to finish."""
    chosen = set(selected or ())

    while True:
        console.say()
        console.say(question)
        for number, item in enumerate(items, start=1):
            mark = "x" if number - 1 in chosen else " "
            console.say(f"  [{mark}] {number}) {item}")
        console.say("  Type numbers to tick or untick, 'a' for all, 'n' for none.")

        answer = _read(console, "Enter when done: ")
        if not answer:
            return chosen
        lowered = answer.lower()
        if lowered in ALL_WORDS:
            chosen = set(range(len(items)))
            continue
        if lowered in NONE_WORDS:
            chosen = set()
            continue

        for token in answer.replace(",", " ").split():
            if not token.isdigit():
                console.say(f"  '{token}' is not a number.")
                continue
            index = int(token) - 1
            if not 0 <= index < len(items):
                console.say(f"  There is no item {token}.")
                continue
            chosen.symmetric_difference_update({index})
