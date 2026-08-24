"""The `python -m z64kit` entry point.

The console script named in pyproject.toml is the documented way in, and it exists
only after an install. This module is the same command reached from a checkout, so
a reader who has not installed anything gets the command line rather than an error
about a package that cannot be executed.

It holds no argument parsing of its own. Everything lives in cli.main, which is
what the console script calls.
"""

from __future__ import annotations

from z64kit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
