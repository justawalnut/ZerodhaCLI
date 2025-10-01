# ZerodhaCLI

Command-driven trading terminal inspired by Insilico Terminal, targeting Zerodha's Kite Connect APIs.

This repo currently contains the application skeleton, core module contracts, and CLI scaffolding. Implementation work focuses on respecting Kite Connect's rate limits, product constraints, and workflows outlined in `info.md`.

## Getting started

1. Create a Python 3.10+ virtual environment.
2. Install the package in editable mode: `pip install -e .[dev]`.
3. Populate a local `.env` (or export environment variables) with your Kite credentials: `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_ACCESS_TOKEN`, optionally `KITE_PUBLIC_TOKEN` and `KITE_USER_ID`. The CLI automatically loads these on startup.
4. Review `info.md` for Zerodha-specific guardrails before integrating live credentials.

## Implemented commands

- `buy` / `sell`: market or limit entry with configurable product/variety.
- `stop`: place SL / SL-M orders with trigger + optional limit price.
- `cancel`: cancel by id or filter (`--side`, `--count`, `--latest`, `--all`).
- `close`: flatten an open position retrieved from the portfolio API.
- `scale`: ladder limit orders between two prices.
- `chase`: adjust a limit order toward a target with tick cadence.
- `swarm`: burst child orders splitting total quantity.
- `gtt` subcommands: `single`, `oco`, `list`, `delete` for server-side triggers.

Commands start in dry-run mode, so nothing hits Zerodha until you supply `--live` when launching the CLI. Use `zerodhacli --live ...` only once you are comfortable with the workflows and ready to trade with real funds. See `docs/USAGE.md` for a quick reference covering every command.
