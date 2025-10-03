"""Entry point for the ZerodhaCLI application."""

from __future__ import annotations

import sys

from .cli.app import run_cli


def main() -> int:
    """Run the ZerodhaCLI command dispatcher."""

    return run_cli()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
