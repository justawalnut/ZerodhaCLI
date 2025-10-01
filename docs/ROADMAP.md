# ZerodhaCLI Roadmap

## Milestone 0: Skeleton (current)

- [x] Project scaffold with Typer CLI entrypoint.
- [x] Core models mirroring Kite entities (orders, positions, GTT).
- [x] Services for orders, portfolio, GTT, ticker wired to Kite endpoints.
- [x] Async rate limiter placeholder.
- [x] Unit tests covering the order router via mocked Kite responses.

## Milestone 1: Command coverage

- [x] Flesh out cancel filters (all/buys/sells/top/bottom/first N).
- [ ] Implement `close` side-selection with margin awareness.
- [x] Add `stop`, `swarm`, `chase`, `gtt` commands.
- [ ] Add command help examples referencing info.md guardrails.

## Milestone 2: Connectivity & state

- [ ] OAuth handshake helper + credential persistence.
- [ ] Shared asyncio event loop with background ticker session.
- [ ] Order registry with resume-on-restart state sync.
- [ ] Margin calculator integration (`/margins`, `/basketmargin`).

## Milestone 3: Risk & algos

- [ ] Enforce market-protection and LTP band checks pre-trade.
- [ ] Implement chase cadence with modification cap (≤25 mods/order).
- [ ] Add TWAP/VWAP execution utilities.
- [ ] Add simulation harnesses for scale/chase.

## Milestone 4: Testing & packaging

- [ ] Add contract tests against Kite sandbox credentials.
- [ ] Expand unit tests (parsers, limiters, state machine).
- [ ] Provide example configs and onboarding scripts.
- [ ] Harden logging and error reporting (Rich tracebacks, JSON logs).
