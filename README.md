# ZerodhaCLI

Command-driven trading terminal inspired by Insilico Terminal, targeting Zerodha’s Kite Connect APIs.

Launch `z` to drop into an interactive shell that accepts fast trading mnemonics (`buy`, `sell`, `sl`, `scale`, `chase`, …). On every start, ZerodhaCLI runs an integrity check and bootstraps services so you know your config and credentials are sane before you trade.

## Features

- Interactive shell (`z>`) with one-liners and a help summary
- Dry-run mode for safe practice; live mode for real orders
- Market/limit/SL/SL-M entries, position close, selective cancel
- Execution helpers: price laddering (`scale`) and limit chasing (`chase`)
- Blotters: open orders, positions with live marks, local history
- Config persistence under `~/.config/zerodhacli/config.json`
- Lightweight rate limiting and Kite Ticker bootstrap (when creds exist)
- Integrity baseline stored alongside your config to detect drift

## Quickstart

1) Environment
- Python 3.10+ recommended. Create and activate a virtualenv.

2) Install
- Editable dev install: `pip install -e .[dev]`
- Regular install: `pip install .`

3) Credentials
- Add a `.env` next to the repo, or export env vars. Supported keys:
  - `KITE_API_KEY`, `KITE_API_SECRET`, `KITE_ACCESS_TOKEN`
  - Optional: `KITE_PUBLIC_TOKEN`, `KITE_USER_ID`
  - Aliases supported: `ZERODHA_API_KEY`, `ZERODHA_API_SECRET`, `ZERODHA_ACCESS_TOKEN`, `ZERODHA_PUBLIC_TOKEN`, `ZERODHA_USER_ID`
- ZerodhaCLI auto-loads `.env` on startup.

4) Run
- First run (safe): `z --dry-run`
- One-off order from your shell (live): `z buy INFY 1 @1540.5`

By default, the CLI runs in LIVE mode unless `--dry-run` is provided.

## Configuration

ZerodhaCLI keeps a user config at `~/.config/zerodhacli/config.json`. You can override the location with `ZERODHACLI_CONFIG_DIR`.

Config keys and defaults:
- `creds`: populated from environment; persisted only if you save
- `root_url`: `https://api.kite.trade`
- `dry_run`: `false`
- `default_product`: `"MIS"` (use `CNC`/`NRML`/`MIS`/`MTF`)
- `market_protection`: `2.5` (percent guardrail; used by close/market flows)
- `autoslice`: `false` (let Kite auto-slice large orders when supported)
- `throttle_warning_threshold`: `0.8` (warn near rate limits)

Example:

```json
{
  "dry_run": false,
  "default_product": "MIS",
  "market_protection": 2.5,
  "autoslice": false
}
```

Environment helpers:
- Point the loader to a different dotenv: set `ZERODHACLI_ENV_FILE=/path/to/.env`
- Change the config directory: set `ZERODHACLI_CONFIG_DIR=/custom/dir`

## Usage

Interactive usage and command examples are documented in `docs/USAGE.md`. Highlights:

- Entries: `buy SYMBOL QTY [@PRICE]`, `sell SYMBOL QTY [@PRICE]`
- Stop-loss: `sl SYMBOL QTY TRIGGER [PRICE]` (omit PRICE for SL-M)
- Close: `close SYMBOL` (accepts `EXCHANGE:SYMBOL` or `SYMBOL`)
- Cancel: `cancel ORDERID` or `cancel all`
- Ladder: `scale SYMBOL QTY START END COUNT`
- Chase: `chase SYMBOL QTY PRICE MAX_MOVES TICK`
- Blotters: `orders`, `pos`, `history [N]`, plus `help`, `quit`

Each execution prints a timestamped summary, e.g.

```
[2025-10-03 10:20:11] SIM BUY 1 AUBANK @₹850.00 -> order_id=DRY-72e6692350b5
status=dry-run
```

SIM/LIVE denotes mode. Position PnL figures come from Zerodha (day PnL) and local mark/avg calculations (unrealised PnL). In live mode, marks are fetched via Kite quotes; in dry-run, fills update a simulated book.

## Integrity & Safety

- On start, an integrity report is printed. If the stored config hash changed or live creds are missing, you’ll see a WARN banner.
- Integrity state is persisted at `~/.config/zerodhacli/integrity.json` (or a local fallback file if the directory is not writable).
- Market-protection and auto-slice flags are attached to orders when relevant. Some guardrails (e.g., far-from-LTP rejections, modification caps) are enforced by Kite itself; roadmap items add more pre-trade checks.

## Development

- Install dev extras: `pip install -e .[dev]`
- Run tests: `pytest -q`
- Lint/format: `ruff check .` (if installed)
- Entry points: `z` and `zerodhacli` both invoke `zerodhacli.__main__:main`

## Troubleshooting

- HTTP errors: check that your Kite credentials are present and valid in `.env` or the config file. Live mode requires at least `api_key` and `access_token`.
- Quote lookups fail: network/firewall issues can surface as `HTTPError`; positions will still display with average price.
- Permissions: if the config or integrity file can’t be written, the app falls back to a local file and notes the path in the WARN line.
- Live by default: if you prefer safety-first, always use `z --dry-run` while exploring.

## Roadmap & Limitations

- See `docs/ROADMAP.md` for planned features (OAuth helper, richer risk checks, more algos, expanded tests).
- Bracket Orders (BO) are discontinued on Kite; OCO flows are possible via GTT for certain cases but have limitations (limit-only when triggered).
- This tool does not provide trading advice and is not designed for HFT/ultra-low latency strategies.

---

If you’d like, open an issue with your workflow and we can extend the command set or add examples in `docs/USAGE.md`.
