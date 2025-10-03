# ZerodhaCLI

Command-driven trading terminal inspired by Insilico Terminal, targeting Zerodha's Kite Connect APIs.

Launch `z` to drop into an interactive shell that prints a ZerodhaCLI banner and
accepts trading mnemonics (`buy`, `sell`, `sl`, `scale`, …). Every session runs
an integrity check before bootstrapping Zerodha services so you know whether the
local config has drifted.

## Getting started

1. Create a Python 3.10+ virtual environment.
2. Install the package in editable mode: `pip install -e .[dev]`.
3. Populate a local `.env` (or export environment variables) with your Kite
   credentials: `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_ACCESS_TOKEN`,
   optionally `KITE_PUBLIC_TOKEN` and `KITE_USER_ID`. The CLI automatically
   loads these on startup.
4. Run the shell: `z --dry-run` is recommended for the first run. Without the
   flag the CLI defaults to **live** mode and will reach the Kite APIs. ZerodhaCLI
   persists overrides in `~/.config/zerodhacli/config.json` — for example:

   ```json
   {
     "dry_run": false,
     "default_product": "MIS",
     "market_protection": 2.5,
     "autoslice": false
   }
   ```

## Command palette

Once the shell banner appears you can issue commands exactly as they are
documented below. Prepend `z` from your system shell for one-off calls (e.g.
`z buy INFY 1 @1540`).

| Action | Syntax |
| --- | --- |
| Market / limit entry | `buy SYMBOL QTY [@PRICE]`, `sell SYMBOL QTY [@PRICE]` |
| Stop-loss | `sl SYMBOL QTY TRIGGER [PRICE]` (omit PRICE for SL-M) |
| Flatten | `close SYMBOL` (accepts `EXCHANGE:SYMBOL` or raw tradingsymbol) |
| Cancel | `cancel ORDERID` or `cancel all` |
| Ladder | `scale SYMBOL QTY START END COUNT` |
| Chase | `chase SYMBOL QTY PRICE MAX_MOVES TICK` |
| Blotters | `orders`, `pos`, `history [N]`, `help`, `quit` |

`pos` displays per-instrument mark price, unrealised PnL, and the summed day PnL
using live quotes (or simulated marks in dry-run).

Every execution logs two lines:

```
[2025-10-03 10:20:11] SIM BUY 1 AUBANK @₹850.00 -> order_id=DRY-72e6692350b5
status=dry-run
```

Live mode replaces `SIM` with `LIVE` and surfaces real Kite order ids/statuses.

See `docs/USAGE.md` for a narrative walkthrough of the session flow.
