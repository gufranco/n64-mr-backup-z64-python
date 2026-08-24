"""`python -m z64kit` must reach the same command line the console script does.

The console script is the documented path and it exists only once the package is
installed. A reader working from a checkout reaches for `python -m z64kit` when the
script is not on PATH, and without this module that attempt failed with an error
naming a missing `__main__`, which reads as a broken package rather than as a
missing install.

The subprocess cases are what a reader actually types. The identity case is what
keeps a second copy of the argument parsing from growing behind the module entry
point, where it would drift from the one the script uses.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return run_module("z64kit", *args)


def run_module(module: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC)},
        check=False,
    )


class TestTheModuleRuns:
    def test_it_prints_the_usage_the_script_prints(self):
        result = run("--help")

        assert result.returncode == 0
        assert "usage: z64kit" in result.stdout

    def test_it_names_the_command_rather_than_a_missing_module(self):
        result = run("--help")

        assert "__main__" not in result.stdout
        assert "__main__" not in result.stderr

    def test_it_carries_the_exit_status_of_a_bad_command(self):
        result = run("no-such-command")

        assert result.returncode == 2


class TestItAddsNoSecondCommandLine:
    def test_it_calls_the_entry_point_the_script_calls(self):
        from z64kit import __main__, cli

        assert __main__.main is cli.main


class TestTheDocumentedFormIsTheOneThatRuns:
    """The guide offers a module form for readers whose PATH lacks the script.

    Nothing held that string and the package together, so it named `z64kit.cli`
    for as long as that was the only form the package could execute. A form the
    docs name and the package cannot run reads as a broken install to the one
    reader already having trouble, which is the reader it is written for.
    """

    def documents(self) -> dict[str, str]:
        return {
            name: (ROOT / name).read_text(encoding="utf-8") for name in ("README.md", "GUIDE.md")
        }

    def test_the_documents_name_the_module_form(self):
        for name, text in self.documents().items():
            assert "python3 -m z64kit" in text, name

    def test_every_documented_module_form_is_one_the_package_runs(self):
        forms = {
            found
            for text in self.documents().values()
            for found in re.findall(r"python3 -m ([\w.]+)", text)
        }

        assert forms, "the module form disappeared from the documents"
        for form in forms:
            assert run_module(form, "--help").returncode == 0, form
