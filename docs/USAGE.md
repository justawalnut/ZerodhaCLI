# ZerodhaCLI Quickstart

ZerodhaCLI now starts in **live** mode. Launch it with `--dry-run` when you want
to simulate order flow without touching the Kite API.

```bash
# Practice session (simulated)
z --dry-run

# One-off market order from your shell (live)
z buy HDFCBANK 1
```

Running `z` with no trailing command opens an interactive shell with ASCII-art
banner, integrity report, and a prompt (`z> `). The same mnemonics work inside
that shell or directly after the `z` binary.

## Core actions

| Action | Description | Example |
| --- | --- | --- |
| `buy SYMBOL QTY [@PRICE]` | Market/limit buy (`@` omitted → market) | `z buy INFY 2 @1540.5` |
| `sell SYMBOL QTY [@PRICE]` | Market/limit sell | `z sell NIFTY24OCTFUT 1` |
| `sl SYMBOL QTY TRIGGER [PRICE]` | Stop-loss; skip PRICE for SL-M | `z sl HDFCBANK 1 1490 1491` |
| `close SYMBOL` | Flatten open position; accepts `NSE:HDFCBANK` or `HDFCBANK` | `z close BANKNIFTY24OCTFUT` |
| `cancel ORDERID` / `cancel all` | Cancel single order or everything open | `z cancel DRY-123abc` |
| `cancel where "expr"` | Predicate cancel using `age`, `role`, `group`, `symbol`, `status`, `protected`, `strategy_id` | `z cancel where "symbol == 'INFY' and age > 30"` |
| `cancel ladder SYMBOL` | Nuke ladders/buckets for a symbol (skips protected legs unless forced) | `z cancel ladder INFY` |
| `cancel nonessential [--strategy ID]` | Cancel all non-protected legs, optionally scoped to a strategy | `z cancel nonessential --strategy swing` |

## Execution algos

| Action | Description | Example |
| --- | --- | --- |
| `scale SYMBOL QTY START END COUNT` | Ladder limit orders across price range | `z scale INFY 15 995 1000 3` |
| `chase SYMBOL QTY PRICE MAX_MOVES TICK` | Place + chase a limit order | `z chase RELIANCE 5 2460 10 0.1` |

## Blotters & utilities

| Command | Description |
| --- | --- |
| `orders` | List open Kite orders (simulated or live) |
| `pos` | Show current positions; simulated fills are tracked during dry-runs |
| `history [N]` | Print the last `N` orders acknowledged in this session (default 10) |
| `help` | Summarise the command set |
| `quit` | Exit the interactive shell |

Each execution emits two log lines in either `SIM` or `LIVE` mode. Example:

```
[2025-10-03 10:21:03] SIM SCALE BUY 15 INFY between 995-1000 (3 legs) -> order_ids=['DRY-aaa', 'DRY-bbb', 'DRY-ccc']
status=dry-run
```

Integrity status is checked every time the CLI launches. If the stored config
hash changes or credentials are missing in live mode, the heading prints a
`WARN` tag so you can resolve issues before trading.

### Reading the blotter

`pos` shows the latest mark price (queried via the Kite quote API in live mode),
the unrealised PnL calculated from the position's average price, and the day's
running PnL from Zerodha. Totals are summarised at the bottom so you can glance
at per-instrument and portfolio PnL without leaving the shell.

A local SQLite index (`~/.config/zerodhacli/state.db`) keeps track of order
roles/groups/strategy tags. Protected roles (stop-loss/take-profit/hedge) are
flagged so `cancel where`, `cancel ladder`, and `cancel nonessential` ignore
them by default. To force-cancel protected legs you must provide both
`--include-protected` and `--confirm` on the relevant command.

Auto-slicing is disabled by default; enable it by setting `"autoslice": true`
in `~/.config/zerodhacli/config.json` if your instrument supports it.
