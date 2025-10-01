"""Entry point for the ZerodhaCLI Typer application."""

from .cli.app import app


def main() -> None:
    """Run the ZerodhaCLI application."""

    app()


if __name__ == "__main__":  # pragma: no cover
    main()
