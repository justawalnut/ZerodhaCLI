# ZerodhaCLI Quickstart

ZerodhaCLI defaults to **dry-run** mode so you can explore every workflow without
submitting real orders. Pass `--live` on the root command only when you are ready
to trade against Zerodha Kite.

```bash
# Dry-run session (default)
zerodhacli buy HDFCBANK 1 --exchange NSE

# Live session
zerodhacli --live buy HDFCBANK 1 --exchange NSE
```

Each command prints a single line indicating whether it ran in `SIM` (dry-run)
or `LIVE` mode, followed by the order details and Kite response.

## Core order entry

| Command | Purpose | Example |
| --- | --- | --- |
| `buy SYMBOL QTY [--price P]` | Place market/limit buy | `zerodhacli buy HDFCBANK 1 --exchange NSE` |
| `sell SYMBOL QTY [--price P]` | Place market/limit sell | `zerodhacli sell HDFCBANK 1 --price 1500 --exchange NSE` |
| `stop` | Submit SL / SL-M | `zerodhacli stop HDFCBANK 1 --trigger 1490 --price 1491` |
| `close EXCHANGE:SYMBOL` | Flatten an open position | `zerodhacli close NSE:HDFCBANK` |
| `cancel` | Cancel orders by id or filters | `zerodhacli cancel --id DRY-12345abc`, `zerodhacli cancel --side BUY --count 2 --latest` |

## Execution algos

| Command | Description | Example |
| --- | --- | --- |
| `scale` | Spread limit orders between two prices | `zerodhacli scale HDFCBANK --start-price 1498 --end-price 1500 --count 3 --quantity 1 --exchange NSE` |
| `chase` | Create + optionally chase a limit order | `zerodhacli chase HDFCBANK --price 1500 --quantity 1 --max-moves 5 --tick-size 0.5` |
| `swarm` | Burst multiple child orders | `zerodhacli swarm HDFCBANK --total-quantity 6 --count 3` |

## GTT management (requires `--live`)

GTT operations hit Zerodha servers and are blocked in dry-run mode.

```bash
zerodhacli --live gtt single HDFCBANK --trigger 1500 --limit-price 1495 --quantity 1
zerodhacli --live gtt list
zerodhacli --live gtt delete 123456
```

## Configuration

Use `zerodhacli config` to inspect the active settings. The config is persisted at
`~/.config/zerodhacli/config.json` and mirrors `.env` credentials. Toggle the
mode by relaunching the CLI with `--dry-run` (default) or `--live`.

## Tips

- Order IDs prefixed with `DRY-` are simulations. Live IDs are returned exactly
  as Kite provides them.
- Commands share pacing and rate-limit awareness; even in dry-run they model the
  cadence you will see in production.
- For repeated experiments, consider clearing prior dry-run orders with
  `zerodhacli cancel --all` before running another scenario.
